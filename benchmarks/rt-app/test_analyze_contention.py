"""Local regression checks with synthetic logs; no rt-app or CloudLab needed."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from analyze_contention import FIELDS, summarize
from contention_config import make_config


class EventOrderTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        header = '# ' + ' '.join(FIELDS) + '\n'
        periodic = header + ''.join(
            f'{i} 52 1000 10000 {100000 + i * 10000} {110000 + i * 10000} '
            f'{i * 10000} 9000 1000 10000 0\n' for i in range(1000))
        background = header + ''.join(
            f'{i} 52 1000 1000 {i * 1000} {(i + 1) * 1000} '
            f'{i * 1000} 0 1000 0 0\n' for i in range(32000))
        for variant in ('cfs', 'eevdf'):
            folder = self.root / variant
            run = folder / 'workers-1/run-1'
            run.mkdir(parents=True)
            for name in ('dmesg-before.txt', 'dmesg-after.txt'):
                (folder / name).write_text('')
            (folder / 'taint.txt').write_text('0\n')
            (run / 'console.log').write_text('pLoad = 19ns\n')
            (run / 'rt-app-periodic-0.log').write_text(periodic)
            (run / 'rt-app-background-1.log').write_text(background)
            self.write_config(variant)

    def write_config(self, variant, *, direct=False, reverse=False):
        config = make_config(1, 19)
        task = config['tasks']['periodic']
        events = task['phases']['work']
        if reverse:
            events = dict(reversed(list(events.items())))
        if direct:
            del task['phases']
            task.update(events)
        else:
            task['phases']['work'] = events
        raw = json.dumps(config).encode()
        run = self.root / variant / 'workers-1/run-1'
        (run / 'workload.json').write_bytes(raw)
        metadata = dict(
            config_sha256=hashlib.sha256(raw).hexdigest(), returncode=0,
            kernel=f'6.6.0-cis7000-{variant}', variant=variant, workers=1,
            repeat=1, stage='run-1', calibration=19, project_commit='test-project',
            rt_app_commit='test-source', binary_sha256='test-binary', settings={},
            threads=[dict(name=name, affinity=[2], policy=0, nice=0,
                          cgroup='test-group', autogroup='test-autogroup')
                     for name in ('periodic-0', 'background-1')])
        (run / 'metadata.json').write_text(json.dumps(metadata))

    def test_accepts_work_before_timer(self):
        for direct in (False, True):
            with self.subTest(direct_events=direct):
                for variant in ('cfs', 'eevdf'):
                    self.write_config(variant, direct=direct)
                result = summarize(self.root, 1, (1,))
                self.assertEqual([r['completed'] for r in result['runs']], [1000, 1000])
                self.assertEqual([r['p99_us'] for r in result['runs']], [1000, 1000])

    def test_rejects_timer_before_work_in_other_kernel(self):
        for direct in (False, True):
            with self.subTest(direct_events=direct):
                self.write_config('cfs', direct=direct)
                self.write_config('eevdf', direct=direct, reverse=True)
                with self.assertRaisesRegex(ValueError, 'Periodic events must be run then timer'):
                    summarize(self.root, 1, (1,))


if __name__ == '__main__':
    unittest.main()
