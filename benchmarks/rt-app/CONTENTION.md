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

After setting up rt-app, run the matrix on each kernel:

```sh
python3 benchmarks/rt-app/run_contention.py results/rt-app-contention --calibration 19
```

Each kernel gets its own directory; existing data is never overwritten.
The runner checks worker settings and records commands' output and metadata.

After both matrices finish, validate and summarize the saved data:

```sh
python3 benchmarks/rt-app/analyze_contention.py results/rt-app-contention
```

The summary keeps per-run metrics and shows their median/min/max. It rejects
missing samples, mismatched settings, or competitors that finish too early.

With Matplotlib installed locally, create the PNG and SVG graphs:

```sh
python3 benchmarks/rt-app/plot_contention.py results/rt-app-contention
```

Graph bars show the observed run range, not a confidence interval.
