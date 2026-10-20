#!/usr/bin/env python3
"""Validate the contention matrix and summarize per-run metrics, without pooling."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

COUNTS = (1, 2, 4, 8)
FIELDS = 'idx perf run period start end rel_st slack c_duration c_period wu_lat'.split()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def load_rows(path, count, period, calibration):
    lines = path.read_text().splitlines()
    check(bool(lines) and lines[0].lstrip('#').split() == FIELDS, f'{path}: unexpected header')
    rows = []
    for line in lines[1:]:
        values = [int(value) for value in line.split()]
        check(len(values) == len(FIELDS), f'{path}: malformed row')
        rows.append(dict(zip(FIELDS, values)))
    check(len(rows) == count, f'{path}: expected {count} rows, got {len(rows)}')
    check(all(r['c_duration'] == 1000 and r['c_period'] == period and r['perf'] == 1000 // calibration
              and r['end'] >= r['start'] for r in rows), f'{path}: unexpected work or timing')
    check(all(b['start'] >= a['end'] for a, b in zip(rows, rows[1:])), f'{path}: unordered rows')
    return rows


def phase(task):
    if 'phases' in task:
        check(len(task['phases']) == 1, 'Expected one phase per task')
        return next(iter(task['phases'].values()))
    return {key: task[key] for key in ('run', 'runtime', 'timer', 'sleep') if key in task}


def analyze_run(path, variant, workers, repeat):
    config_bytes = (path / 'workload.json').read_bytes()
    config = json.loads(config_bytes)
    meta = json.loads((path / 'metadata.json').read_text())
    check(meta['config_sha256'] == hashlib.sha256(config_bytes).hexdigest(), 'Workload checksum mismatch')
    check(meta['returncode'] == 0 and meta['kernel'] == f'6.6.0-cis7000-{variant}', 'Run failed or wrong kernel')
    check((meta['variant'], meta['workers']) == (variant, workers), 'Wrong run metadata')
    check(meta['repeat'] == repeat and meta['stage'] == f'run-{repeat}', 'Wrong repeat/stage metadata')
    glob, tasks = config['global'], config['tasks']
    calibration = meta['calibration']
    check(type(calibration) is int and calibration > 0 and glob['calibration'] == calibration, 'Invalid calibration')
    check(glob['duration'] == -1 and glob['log_size'] == 8, 'Wrong global settings')
    check(glob.get('ftrace', 'none') == 'none' and set(tasks) == {'periodic', 'background'}, 'Unexpected tracing/tasks')
    periodic, background = tasks['periodic'], tasks['background']
    for task in tasks.values():
        check(task['policy'] == 'SCHED_OTHER' and task['priority'] == 0 and task['cpus'] == [2], 'Wrong task scheduling')
    check(periodic['loop'] == 1000 and periodic['delay'] == 100000, 'Wrong periodic count/delay')
    check(phase(periodic) == {'run': 1000, 'timer': {'ref': 'unique', 'period': 10000, 'mode': 'absolute'}}, 'Wrong periodic phase')
    check(background['instance'] == workers and background['loop'] == 32000 // workers
          and phase(background) == {'run': 1000}, 'Wrong background workload')
    console = (path / 'console.log').read_text()
    check(f'pLoad = {calibration}ns' in console and 'Calibrate ns per loop' not in console, 'Calibration was not fixed')
    names = {'periodic-0'} | {f'background-{i}' for i in range(1, workers + 1)}
    threads = meta['threads']
    check(len(threads) == workers + 1 and {t['name'] for t in threads} == names, 'Missing/extra workload threads')
    for thread in threads:
        check(thread['affinity'] == [2] and thread['policy'] == 0 and thread['nice'] == 0, 'Wrong observed scheduling')
        check(all(thread[key] == threads[0][key] for key in ('cgroup', 'autogroup')), 'Workers used different groups')
    check({p.name for p in path.glob('rt-app-*.log')} == {f'rt-app-{name}.log' for name in names}, 'Missing/extra logs')
    rows = load_rows(path / 'rt-app-periodic-0.log', 1000, 10000, calibration)
    start, end = rows[0]['start'], rows[-1]['end']
    interval = (end - start) / 1_000_000
    check(interval > 0, 'Empty observation interval')
    chunks = 0
    for name in sorted(names - {'periodic-0'}):
        busy = load_rows(path / f'rt-app-{name}.log', 32000 // workers, 0, calibration)
        check(busy[0]['start'] <= start and busy[-1]['end'] >= end, f'{name}: competition ended early or started late')
        chunks += sum(r['start'] >= start and r['end'] <= end for r in busy)
    latency = sorted(r['c_period'] - r['slack'] for r in rows)
    check(latency[0] >= 0, 'Negative completion latency')
    metrics = {'median_us': statistics.median(latency), 'p99_us': latency[math.ceil(.99 * len(latency)) - 1],
               'max_us': max(latency), 'missed_deadlines': sum(r['slack'] < 0 for r in rows),
               'completed': len(rows), 'unfinished': 1000 - len(rows), 'periodic_interval_s': interval,
               'background_chunks_per_s': chunks / interval}
    return {'variant': variant, 'workers': workers, 'repeat': repeat, **metrics}, config, meta


def summarize(root, repeats):
    runs, configs, identities = [], {}, []
    for variant in ('cfs', 'eevdf'):
        folder = root / variant
        check((folder / 'dmesg-before.txt').read_bytes() == (folder / 'dmesg-after.txt').read_bytes(),
              f'{folder}: kernel log changed')
        check((folder / 'taint.txt').read_text().strip() == '0', f'{folder}: kernel is tainted')
        check({p.name for p in folder.glob('workers-*')} == {f'workers-{n}' for n in COUNTS}, f'{folder}: incomplete worker matrix')
        for workers in COUNTS:
            case = folder / f'workers-{workers}'
            check({p.name for p in case.glob('run-*')} == {f'run-{i}' for i in range(1, repeats + 1)}, f'{case}: incomplete repeat set')
            for repeat in range(1, repeats + 1):
                path = case / f'run-{repeat}'
                try:
                    run, config, meta = analyze_run(path, variant, workers, repeat)
                    check(config == configs.setdefault(workers, config), 'Workload config changed between runs')
                    identity = {key: meta[key] for key in ('project_commit', 'rt_app_commit', 'binary_sha256', 'calibration', 'settings')}
                    check(not identities or identity == identities[0], 'Binary/source/recorded settings changed')
                    identities.append(identity)
                    runs.append(run)
                except (KeyError, OSError, ValueError) as error:
                    raise ValueError(f'{path}: {error}') from error
    groups = []
    metrics = [key for key in runs[0] if key not in ('variant', 'workers', 'repeat')]
    for variant in ('cfs', 'eevdf'):
        for workers in COUNTS:
            selected = [r for r in runs if (r['variant'], r['workers']) == (variant, workers)]
            values = {key: [r[key] for r in selected] for key in metrics}
            groups.append({'variant': variant, 'workers': workers, 'repeats': repeats,
                           'metrics': {key: {'median': statistics.median(v), 'min': min(v), 'max': max(v)}
                                       for key, v in values.items()}})
    return {'calibration_ns_per_loop': identities[0]['calibration'], 'repeats': repeats, 'runs': runs, 'groups': groups,
            'method': {'latency': 'c_period - slack, microseconds; all 1000 measured jobs',
                       'p99': 'nearest rank per run; jobs are not pooled across runs',
                       'background': 'whole fixed-work chunks inside the observed periodic interval, per second',
                       'range': 'minimum and maximum across runs, not a confidence interval'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    try:
        check(args.repeats > 0, 'repeats must be positive')
        output = summarize(args.root, args.repeats)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Invalid benchmark data: {error}\n')
    target = args.root / 'summary.json'
    target.write_text(json.dumps(output, indent=2) + '\n')
    print(f'Validated {len(output["runs"])} runs; wrote {target}')


if __name__ == '__main__':
    main()
