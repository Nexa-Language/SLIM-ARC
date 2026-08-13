# A6 adaptive expert access-advice diagnostic

This 2 GiB cold-cache diagnostic changes only merged expert tensor advice from
decode `SEQUENTIAL` to `NORMAL`. Shared weights remain sequential, the phase
split remains 8/6, block readahead remains 128 KB, and swap remains disabled.

| Configuration | Prefill | Decode | Wall | Major faults | Filesystem input blocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sequential control | 4.169861 t/s | 0.800984 t/s | 55.90 s | 487,853 | 199,690,872 |
| Expert NORMAL | 4.232109 t/s | 0.657144 t/s | 61.08 s | 432,226 | 202,879,960 |

Adaptive expert advice reduced major faults by 11.40% but increased input blocks
by 1.60%, reduced decode throughput by 17.96%, and increased wall time by 9.27%.
All 2,304 calls succeeded. Together with the A5 RANDOM result, this shows that
the current slow-storage path benefits from retaining sequential expert
readahead despite its read amplification.

The mode remains strictly opt-in and is rejected for the finalist default.
