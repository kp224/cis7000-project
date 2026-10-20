#!/usr/bin/env python3
"""Generate a finite rt-app workload with continuously busy competitors."""
import argparse
import json
from pathlib import Path


def make_config(workers, calibration, *, warmup=False):
    if workers not in (1, 2, 4, 8) or calibration <= 0:
        raise ValueError('Use 1/2/4/8 workers and a positive numeric calibration.')
    config = json.loads(Path(__file__).with_name('periodic.json').read_text())
    config['global'].update(calibration=calibration, log_size=8)
    periodic = config['tasks']['periodic']
    periodic.update(delay=100000, loop=200 if warmup else 1000)
    config['tasks']['background'] = {
        'instance': workers, 'policy': 'SCHED_OTHER', 'priority': 0,
        'cpus': [2], 'loop': (8000 if warmup else 32000) // workers,
        'phases': {'busy': {'run': 1000}},
    }
    return config


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workers', type=int, choices=(1, 2, 4, 8))
    parser.add_argument('--calibration', type=int, required=True,
                        help='Saved pLoad in ns per loop; never recalibrate between kernels.')
    parser.add_argument('--warmup', action='store_true')
    args = parser.parse_args()
    print(json.dumps(make_config(args.workers, args.calibration,
                                 warmup=args.warmup), indent=2))
