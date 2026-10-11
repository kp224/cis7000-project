#!/usr/bin/env python3
"""Linux scheduler correctness smoke checks; shares are not performance claims."""
import argparse
import json
import multiprocessing as mp
import os
import platform
import time


def groups():
    result = {}
    for name in ("cgroup", "autogroup"):
        try:
            with open("/proc/self/" + name) as source:
                result[name] = source.read().strip()
        except FileNotFoundError:
            result[name] = None
    return result


def worker(pipe, start, stop, cpu, nice, mode, migration_cpus):
    try:
        os.sched_setaffinity(0, {cpu})
        if nice:
            os.nice(nice)
        info = {"pid": os.getpid(), "policy": os.sched_getscheduler(0),
                "nice": os.getpriority(os.PRIO_PROCESS, 0), "groups": groups(),
                "affinity": sorted(os.sched_getaffinity(0))}
        pipe.send({"ready": info})
        if not start.wait(30):
            raise TimeoutError("launch barrier timed out")
        wall_start, cpu_start = time.monotonic(), time.process_time()
        iterations = wakes = forks = migrations = 0
        value = 1
        while not stop.is_set():
            # Enough arithmetic per stop check to avoid lock-dominated workers.
            for _ in range(10000):
                value = (value * 1664525 + 1013904223) & 0xffffffff
            iterations += 1
            if mode == "sleep":
                time.sleep(0.01)
                wakes += 1
            elif mode == "fork":
                pid = os.fork()
                if pid == 0:
                    os._exit(0)
                _, status = os.waitpid(pid, 0)
                if status != 0:
                    raise RuntimeError("forked child failed")
                forks += 1
                time.sleep(0.01)
            elif mode == "migration":
                target = migration_cpus[migrations % len(migration_cpus)]
                os.sched_setaffinity(0, {target})
                if os.sched_getaffinity(0) != {target}:
                    raise RuntimeError("affinity change failed")
                migrations += 1
        pipe.send({"cpu_seconds": time.process_time() - cpu_start,
                   "wall_start": wall_start, "wall_stop": time.monotonic(),
                   "iterations": iterations, "wakes": wakes,
                   "forks": forks, "migrations": migrations})
    except BaseException as error:
        pipe.send({"error": str(error)})
    finally:
        pipe.close()


def receive(pipe, deadline):
    if not pipe.poll(max(0, deadline - time.monotonic())):
        raise TimeoutError("worker response timed out")
    result = pipe.recv()
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def run_test(name, specs, duration, cpu, migration_cpus, parent_groups,
             expected=None, tolerance=0.10):
    context = mp.get_context("fork")
    start, stop = context.Event(), context.Event()
    processes, pipes = [], []
    result = {"name": name, "duration_seconds": duration, "pass": False}
    try:
        for nice, mode in specs:
            parent, child = context.Pipe(duplex=False)
            process = context.Process(target=worker, args=(
                child, start, stop, cpu, nice, mode, migration_cpus))
            process.start()
            child.close()
            processes.append(process)
            pipes.append(parent)
        deadline = time.monotonic() + 15
        ready = [receive(pipe, deadline)["ready"] for pipe in pipes]
        result["workers"] = ready
        for info, (nice, _) in zip(ready, specs):
            if (info["groups"] != parent_groups or info["nice"] != nice
                    or info["policy"] != os.SCHED_OTHER
                    or info["affinity"] != [cpu]):
                raise RuntimeError("worker scheduling configuration mismatch")
        result["same_cgroup_and_autogroup"] = True
        result["launch_time"] = time.monotonic()
        start.set()
        time.sleep(duration)
        result["stop_time"] = time.monotonic()
        stop.set()
        deadline = time.monotonic() + 10
        measurements = [receive(pipe, deadline) for pipe in pipes]
        for info, measurement, process in zip(ready, measurements, processes):
            info.update(measurement)
            process.join(max(0, deadline - time.monotonic()))
            if process.exitcode != 0:
                raise RuntimeError("worker did not exit successfully")
        total = sum(info["cpu_seconds"] for info in ready)
        result["observed_shares"] = [info["cpu_seconds"] / total for info in ready]
        passed = all(info["iterations"] > 0 for info in ready)
        for info, (_, mode) in zip(ready, specs):
            counter = {"sleep": "wakes", "fork": "forks",
                       "migration": "migrations"}.get(mode)
            if counter:
                passed = passed and info[counter] >= 2
        if expected is not None:
            result.update(expected_shares=expected, tolerance_absolute=tolerance)
            passed = passed and all(abs(actual - wanted) <= tolerance
                                    for actual, wanted in zip(
                                        result["observed_shares"], expected))
        result["pass"] = passed
    except Exception as error:
        result["error"] = str(error)
    finally:
        stop.set()
        start.set()
        # All joins have bounds, including cleanup after errors or interruption.
        for process in processes:
            process.join(0.2)
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
        for pipe in pipes:
            pipe.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=int, help="logical CPU (default: first allowed)")
    parser.add_argument("--duration", type=float, default=15,
                        help="seconds per fairness check (default: 15)")
    args = parser.parse_args()
    report = {"kernel": platform.uname()._asdict(), "tests": [], "pass": False}
    original = None
    try:
        if platform.system() != "Linux":
            raise RuntimeError("this script requires Linux")
        original = os.sched_getaffinity(0)
        allowed = sorted(original)
        cpu = allowed[0] if args.cpu is None else args.cpu
        if cpu not in original or not 0 < args.duration <= 120:
            raise ValueError("CPU must be allowed; duration must be in (0, 120]")
        policy, nice = os.sched_getscheduler(0), os.getpriority(os.PRIO_PROCESS, 0)
        parent_groups = groups()
        report.update(allowed_affinity=allowed, selected_cpu=cpu, policy=policy,
                      nice=nice, groups=parent_groups)
        if policy != os.SCHED_OTHER or nice != 0:
            raise RuntimeError("launch controller with SCHED_OTHER and nice 0")
        other = next((item for item in allowed if item != cpu), None)
        controller_cpu = cpu if other is None else other
        os.sched_setaffinity(0, {controller_cpu})
        report["controller_affinity"] = [controller_cpu]
        cases = [("equal_share", [(0, "busy"), (0, "busy")], args.duration, [0.5, 0.5]),
                 ("nice_weights", [(0, "busy"), (5, "busy")], args.duration,
                  [1024 / 1359, 335 / 1359]),
                 ("sleep_wake", [(0, "sleep"), (0, "busy"), (0, "busy")], 3, None),
                 ("fork_exit", [(0, "fork"), (0, "busy")], 2, None)]
        if other is not None:
            cases.append(("migration", [(0, "migration"), (0, "busy")], 3, None))
        for name, specs, duration, expected in cases:
            report["tests"].append(run_test(name, specs, duration, cpu,
                                           [cpu, other], parent_groups, expected))
        if other is None:
            report["tests"].append({"name": "migration", "pass": False,
                                    "error": "requires two allowed logical CPUs"})
        report["pass"] = all(test["pass"] for test in report["tests"])
    except Exception as error:
        report["error"] = str(error)
    finally:
        if original is not None:
            os.sched_setaffinity(0, original)
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
