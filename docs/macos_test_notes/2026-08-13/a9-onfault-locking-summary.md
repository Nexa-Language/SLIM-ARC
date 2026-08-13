# A9 shared-expert on-fault locking

A9 tested Linux `mlock2(MLOCK_ONFAULT)` for the 92.4 MB always-used shared
expert path. The hypothesis was that deferring page locking until first access
would remove eager shared-weight I/O from model registration while preserving
the pages for decode.

The direct comparison alternated immutable A8 eager and A9 on-fault images.
Both configurations used the same model, 2 GiB cgroup-v2 limit, zero swap,
8/6 phase threads, poll 50, 128 KB readahead, and cold `pp64/tg16` workloads.

| Lock mode | Samples | Prefill median | Decode median | Wall median | Major faults median | Input blocks median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Eager `mlock` | 2 | 4.298078 t/s | 0.834153 t/s | 55.31 s | 467,453 | 195,971,980 |
| `MLOCK_ONFAULT` | 2 | 4.345860 t/s | 0.805874 t/s | 55.64 s | 473,968 | 196,986,256 |

On-fault locking improved prefill by 1.11%, but reduced decode by 3.39%, raised
wall time by 0.59%, raised major faults by 1.39%, and raised input blocks by
0.52%. Both A9 runs confirmed `onfault_bytes=92405760` with zero lock failures.

The hypothesis is rejected. Shared experts are all consumed during prefill, so
deferring their faults does not eliminate the reads; it moves some page faults
onto the inference critical path. The finalist keeps eager shared-expert
locking. The A9 feature commit remains in history, followed by an explicit
revert, so the negative result and its mechanism stay auditable.
