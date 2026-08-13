# A8 always-used shared-expert residency

GGUF header inventory found 46.81 GB of sparse expert tensors, a 201.52 MB
router path, and only 91.62 MB of shared-expert tensors. The A8 policy pins the
page-aligned `_shexp` path because every token uses it; it performs no expert
prediction and no speculative disk read.

All paired runs use the same A8 image, 2 GiB cgroup-v2 memory limit, zero swap,
8/6 phase threads, poll 50, 128 KB block readahead, and cold `pp64/tg16`.

| Configuration | Samples | Prefill median | Decode median | Wall median | Major faults median | Input blocks median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Control | 2 | 4.464416 t/s | 0.859943 t/s | 54.45 s | 488,568.5 | 199,555,204 |
| Shared resident | 2 | 4.639883 t/s | 0.886365 t/s | 51.51 s | 474,053.5 | 196,913,124 |

The resident path improved median prefill by **3.93%**, decode by **3.07%**,
reduced wall time by **5.40%**, major faults by **2.97%**, and input blocks by
**1.32%**. Both candidate runs locked exactly 92,405,760 page-aligned bytes with
zero failures, completed at the 2 GiB peak, used zero swap, and did not OOM.

`SLIM_ARC_SHARED_MLOCK=1` is promoted as the 2 GiB finalist candidate. It remains
opt-in until the remote board is profiled, because pinned pages reduce the
remaining general page-cache capacity.

## 1 GiB boundary

At 1 GiB, the same paired experiment continued to reduce major faults by 5.45%
and input blocks by 1.76%, but median prefill fell 3.27%, decode fell 4.03%, and
wall time increased 0.92%. The second candidate run was especially slow,
showing that reserving 92.4 MB makes the remaining page cache too fragile at
this tier. The finalist policy therefore enables shared residency at 2 GiB and
disables it at 1 GiB.
