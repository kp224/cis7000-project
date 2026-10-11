# CFS restoration

Base: upstream `v6.6`, commit `ffc253263a1375a65fa6c9f62a893e9767fbebfa`.
Restore classic CFS while preserving unrelated Linux 6.6 changes.

## Reversal order

Each patch records its upstream source commit. Follow-up fixes must be
removed before removing the EEVDF code they modify.

| Upstream commit | Change to reverse |
| --- | --- |
| `d2929762cc3f` | Deadline heap follow-up fix |
| `b01db23d5923` | EEVDF selection fix |
| `8dafa9d0eb1a` | Deadline heap update |
| `650cad561cce` | Average virtual runtime rounding |
| `2f2fc17bab00` | Slice update on placement |
| `c958ca2013e2` | Static lag helper |
| `63304558ba5d` | Run-to-parity preemption rule |
| `d07f09a1f99c` | Placement flags |
| `e4ec3318a17f` | Base-slice tunable rename |
| `5e963f2bd465` | Removal of CFS selection and preemption |
| `e8f331bcc270` | Lag-based migration placement |
| `76cae9dbe185` | Removal of old placement |
| `147f3efaa241` | EEVDF selection and deadline machinery |
| `86bfbb7ce4f6` | Lag-based placement |
| `e0c2ff903c32` | Removal of the initial CFS debit |
| `af4cf40470c2` | Average virtual runtime accounting |
| `2f88c8e802c8` | Documentation's base-slice setting name |

Keep the generic augmented-rbtree helper and unrelated fixes. Resolve
conflicts explicitly; do not replace whole files with Linux 6.5 copies.

## Apply

From a fresh project checkout:

```sh
bash scripts/prepare-kernels.sh
bash scripts/apply-cfs-patches.sh
```

The second command applies `series` to `work/linux-cfs`. It refuses local
changes, an incorrect base, or an unfinished Git operation. The EEVDF
checkout remains unchanged. These sparse checkouts are for source work;
building requires the full tree on a case-sensitive Linux filesystem.

## Validation

- All 17 patches replay cleanly onto the pinned base.
- Replayed tree: `2519def936d64df42abe40b623249424845e5e6c`.
- Source review found classic CFS behavior restored with unrelated 6.6
  changes retained. Manual conflict fixes are recorded in patches 10 and 13.
- `kernel/sched/` compiled for both variants with x86-64 GCC 12.2.0,
  with SMP enabled and disabled. Scheduler debugging, fair task groups,
  and CFS bandwidth control were enabled. Paired configs were identical.
- Both full kernels built with GCC 11.4.0 and booted on a CloudLab m510
  on 2026-10-11. Configs matched apart from their release names.
- Both passed equal-share, nice-weight, sleep/wake, fork/exit, and migration
  smoke checks. No new kernel log messages appeared during either run.
- Function tracing observed `__pick_eevdf` on EEVDF and `sched_slice` on CFS.
  Tracing was restored to `nop` afterward.

Local logs and configs are in `results/local-compile/`
and `results/cloudlab-ms0906/` (ignored). These checks establish basic
operation; performance comparisons and broader correctness testing remain.

Intermediate patches leave EEVDF incomplete. Test only the full series.
