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

Keep the generic augmented-rbtree helper and unrelated fixes. Resolve
conflicts explicitly; do not replace whole files with Linux 6.5 copies.

## Status

Restoration in progress. Intermediate patches can leave EEVDF incomplete
and must not be used for benchmarks. The final series still needs a clean
replay, source review, compilation, and CloudLab smoke tests.
