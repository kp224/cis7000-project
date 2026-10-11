# Scheduler smoke checks

Run on the test node after selecting a kernel:

```sh
python3 tests/smoke_scheduler.py --cpu 2 > results/smoke.json
```

The five checks cover equal CPU shares, nice weights, sleep/wake progress,
fork/exit, and migration. Fairness checks run for 15 seconds each, with a
10 percentage-point tolerance. They are basic checks, not benchmarks.

On 2026-10-11, all five passed on the same CloudLab m510 under:

- `6.6.0-cis7000-eevdf`
- `6.6.0-cis7000-cfs`

Both gave roughly 50/50 CPU shares at equal priority and 75/25 at nice 0/5.
Neither produced new kernel log messages during the checks.

The installer preserves Ubuntu as the normal boot default. To select a
test kernel for one reboot, use `sudo grub-reboot cis7000-eevdf` or
`sudo grub-reboot cis7000-cfs`, then `sudo reboot`. Check `uname -r` after
reconnecting. Save results before the CloudLab experiment expires.
