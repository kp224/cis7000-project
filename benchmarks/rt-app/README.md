# Basic rt-app workload

One normal-priority thread on CPU 2 runs calibrated work of about 1 ms every
10 ms, for 1,000 periods (about 10 seconds after calibration). No background
workers. The absolute timer keeps the schedule fixed when work runs late.

From the project root on the Ubuntu test node:

```sh
sudo apt-get update
sudo apt-get install -y build-essential autoconf automake libtool pkg-config libjson-c-dev libnuma-dev
bash scripts/setup-rt-app.sh
project_root=$PWD
mkdir -p results
run_dir=$(mktemp -d "$project_root/results/rt-app-basic.XXXXXX")
cp benchmarks/rt-app/periodic.json "$run_dir/workload.json"
uname -a > "$run_dir/kernel.txt"
cd "$run_dir"
timeout --kill-after=5s 60s "$project_root/work/build-rt-app/src/rt-app" workload.json > console.log 2>&1
```

Run as your normal user with CPU 2 available. Expect exit status 0 and
1,000 data rows in the thread log.
Logs are buffered in memory, then saved in the new results directory.

This is a setup check. It calibrates on CPU 2 each time; for comparisons,
save the numeric `pLoad` from `console.log` and reuse it as `calibration`
under both kernels. Analysis and competing workloads come later.

[Upstream configuration guide](https://github.com/scheduler-tools/rt-app/blob/d6f8be41107642fd6ab41bc1ab3bb01a486fd00e/doc/tutorial.txt).
