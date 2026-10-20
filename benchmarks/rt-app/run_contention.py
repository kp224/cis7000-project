#!/usr/bin/env python3
"""Run the contention matrix on the currently booted Linux test kernel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from contention_config import make_config

ROOT = Path(__file__).resolve().parents[2]


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def threads(pid, count):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        found = []
        try:
            for task in Path(f'/proc/{pid}/task').iterdir():
                name = (task / 'comm').read_text().strip()
                if not name.startswith(('periodic-', 'background-')):
                    continue
                tid = int(task.name)
                found.append(dict(name=name, affinity=sorted(os.sched_getaffinity(tid)),
                                  policy=os.sched_getscheduler(tid),
                                  nice=os.getpriority(os.PRIO_PROCESS, tid),
                                  cgroup=(task / 'cgroup').read_text().strip(),
                                  autogroup=Path(f'/proc/{pid}/autogroup').read_text().strip()))
            if len(found) == count and all(t['affinity'] == [2] and t['policy'] == 0
                                           and t['nice'] == 0 for t in found):
                if len({(t['cgroup'], t['autogroup']) for t in found}) != 1:
                    raise RuntimeError('Workers are in different scheduling groups.')
                return found
        except (FileNotFoundError, ProcessLookupError):
            pass
        time.sleep(.1)
    raise RuntimeError('Could not verify all workload threads on CPU 2 at normal priority.')


def run_one(binary, path, config, metadata):
    path.mkdir(parents=True)
    save(path / 'workload.json', config)
    metadata['config_sha256'] = hashlib.sha256((path / 'workload.json').read_bytes()).hexdigest()
    metadata['started_unix'] = time.time()
    with (path / 'console.log').open('w') as log:
        process = subprocess.Popen([str(binary), 'workload.json'], cwd=path,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            metadata['threads'] = threads(process.pid, metadata['workers'] + 1)
            process.wait(timeout=120)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            metadata.update(returncode=process.returncode, finished_unix=time.time())
            save(path / 'metadata.json', metadata)
    if process.returncode:
        raise RuntimeError(f'rt-app failed in {path}; inspect console.log.')
    print(f"{metadata['variant']} workers={metadata['workers']} {path.name}: finished", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--calibration', type=int, required=True)
    parser.add_argument('--workers', type=int, choices=(1, 2, 4, 8), nargs='+', default=[1, 2, 4, 8])
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.calibration <= 0 or args.repeats <= 0 or len(set(args.workers)) != len(args.workers):
        parser.error('Use positive calibration/repeats and distinct worker counts.')
    kernel = os.uname().release
    if kernel not in ('6.6.0-cis7000-cfs', '6.6.0-cis7000-eevdf'):
        parser.error('Boot one of the two test kernels first.')
    variant = kernel.rsplit('-', 1)[1]
    allowed = sorted(os.sched_getaffinity(0))
    if not {0, 2}.issubset(allowed) or os.sched_getscheduler(0) != 0 or os.getpriority(os.PRIO_PROCESS, 0) != 0:
        parser.error('Run with CPUs 0/2 available, SCHED_OTHER, and nice 0.')
    pin = dict(line.split('=', 1) for line in (ROOT / 'configs/rt-app-source.env').read_text().splitlines())
    source = ROOT / 'work/rt-app'
    if command('git', '-C', str(source), 'rev-parse', 'HEAD') != pin['RT_APP_COMMIT']:
        parser.error('rt-app source differs from the pinned revision.')
    if command('git', '-C', str(source), 'status', '--porcelain'):
        parser.error('rt-app source has local changes.')
    binary = ROOT / 'work/build-rt-app/src/rt-app'
    settings = {'allowed_cpus': allowed}
    paths = [Path('/sys/devices/system/cpu/cpu2/cpufreq') / key for key in
             ('scaling_driver', 'scaling_governor', 'scaling_min_freq', 'scaling_max_freq')]
    paths += [Path('/sys/devices/system/cpu/smt/control'),
              Path('/sys/devices/system/cpu/cpu2/topology/thread_siblings_list')]
    settings.update({str(p): p.read_text().strip() for p in paths if p.exists()})
    common = dict(kernel=kernel, variant=variant, calibration=args.calibration,
                  project_commit=command('git', '-C', str(ROOT), 'rev-parse', 'HEAD'),
                  rt_app_commit=pin['RT_APP_COMMIT'], settings=settings,
                  binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    out = args.output.resolve() / variant
    out.mkdir(parents=True)
    before = command('sudo', '-n', 'dmesg')
    (out / 'dmesg-before.txt').write_text(before + '\n')
    (out / 'boot-id.txt').write_text(Path('/proc/sys/kernel/random/boot_id').read_text())
    (out / 'cmdline.txt').write_text(Path('/proc/cmdline').read_text())
    os.sched_setaffinity(0, {0})  # Keep the runner and rt-app controller off CPU 2.
    try:
        for count in args.workers:
            case = out / f'workers-{count}'
            for repeat in range(args.repeats + 1):
                warmup = repeat == 0
                name = 'warmup' if warmup else f'run-{repeat}'
                metadata = dict(common, workers=count, repeat=repeat, stage=name)
                run_one(binary, case / name, make_config(count, args.calibration, warmup=warmup), metadata)
    finally:
        os.sched_setaffinity(0, allowed)
        after = command('sudo', '-n', 'dmesg')
        (out / 'dmesg-after.txt').write_text(after + '\n')
        (out / 'taint.txt').write_text(Path('/proc/sys/kernel/tainted').read_text())
    if before != after or (out / 'taint.txt').read_text().strip() != '0':
        raise RuntimeError('Kernel logs or taint need inspection.')


if __name__ == '__main__':
    main()
