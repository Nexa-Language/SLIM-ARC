# A13 small always-used tensor residency

GGUF header analysis found 325 non-expert, non-router tensors no larger than
1 MiB, totaling 23,997,440 bytes. They are primarily layer norms, SSM state
parameters, small conv1d weights, and GQA K/V weights. A13 locks this path only
when `SLIM_ARC_SMALL_MLOCK=1`; the measured page-aligned resident set is
25,313,280 bytes with zero failures.

All 2 GiB runs use the same A13 image, zero swap, eager shared-expert residency,
eight/six phase threads, poll 50, 128 KB readahead, and cold `pp64/tg16`.

| 2 GiB configuration | Samples | Prefill median | Decode median | Wall median | Major faults median | Input blocks median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Shared only | 2 | 4.688924 t/s | 0.917174 t/s | 50.60 s | 473,491 | 196,730,580 |
| Shared + small | 2 | 4.721195 t/s | 0.918171 t/s | 50.42 s | 459,014 | 195,180,964 |

The small resident path improved median prefill by 0.69%, decode by 0.11%,
wall time by 0.37%, major faults by 3.06%, and input blocks by 0.79%. The TPS
gain is modest, but every median metric moves in the desired direction and the
resident footprint is only about 24 MiB. This was the short-workload candidate;
the later A14 `tg64` result supersedes its promotion decision.

## 1 GiB boundary

At 1 GiB, A13 was tested without the already-rejected 92 MB shared resident
set. The 24 MB small path reduced major faults by 2.13% and input blocks by
0.41%, but reduced prefill by 5.78%, reduced decode by 3.08%, and increased wall
time by 2.92%. Even this smaller locked set displaces more valuable dynamic
pages at the 1 GiB tier, so both resident policies remain disabled there.

The result supports a tiered resident-set policy rather than indiscriminate
hot-page pinning. A14 showed that the small set also regresses sustained decode
at 2 GiB, so the finalist enables no pinned set at 1 GiB and only the shared
resident path at 2/4 GiB. `SLIM_ARC_SMALL_MLOCK` remains an experimental,
strictly opt-in switch for workload-specific profiling.
