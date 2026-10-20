# rt-app with competing workers

Keep the basic periodic task: about 1 ms of fixed work every 10 ms for
1,000 periods. Add 1, 2, 4, or 8 busy rt-app threads. All threads use CPU 2,
SCHED_OTHER and nice 0 in one process. Reuse the same numeric calibration.

Generate a config from the project root:

```sh
python3 benchmarks/rt-app/contention_config.py 4 --calibration 19
```

The periodic task starts after 100 ms so the competitors can start first.
Busy workers have no sleeps. They do enough finite work to outlast the
periodic task, then exit normally. This avoids rt-app's timed cancellation,
which can lose buffered logs. Analysis must verify coverage and row counts.

Measure completion latency as `c_period - slack`; negative slack means a
missed 10 ms deadline. Let late jobs finish instead of hiding them at a cutoff.

Measure background throughput in completed fixed-work chunks per second,
using only chunks wholly inside the periodic task's observed interval
(first phase start through last phase end). This interval can exceed 10 s.
Exclude the background-only tail and partially overlapping chunks.

Use three repeats per load for this exploratory matrix. Final results need
at least five repeats and alternating kernel order, as stated in the proposal.
