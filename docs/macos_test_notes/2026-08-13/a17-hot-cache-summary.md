# A17 stable expert hot-cache ablation

A17 evaluates the survey-inspired resident hot-expert set on the 80B-A3B
model. Both cold runs use the same image and model, a 2 GiB cgroup-v2 limit,
zero swap, 8 CPUs, `pp64/tg64`, 256 KiB readahead, `mq-deadline`, pressure
admission with a 512 MiB reserve, and the already promoted shared-expert lock.

| Configuration | Prefill | Decode | Wall | Major faults | Input blocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 5.261280 t/s | 1.019083 t/s | 92.37 s | 1,028,236 | 453,055,720 |
| Hot cache, 128 MiB | 5.300603 t/s | 0.997965 t/s | 92.87 s | 1,045,031 | 458,595,280 |
| Relative | +0.75% | -2.07% | +0.54% | +1.63% | +1.22% |

The 128 MiB policy admitted 265 expert entries and recorded 367 cache hits,
but retained only 38,973,440 bytes (37.17 MiB). At the point where router
results became visible it observed 21,339,844,608 nonresident bytes and 11,302
failed admission attempts. The current hook runs after whole-graph compute, so
the 2 GiB page cache has already evicted most early-layer expert pages. This is
too late to create a useful resident set without faulting pages back in.

Decision: reject this configuration and keep `SLIM_ARC_EXPERT_HOT_MB` unset in
the finalist profile. A useful implementation requires a layer-local execution
hook or a trained pre-compute prediction path; the current post-graph hook is
retained only as an opt-in research prototype and is not a performance claim.
