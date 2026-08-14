# A10 decode-thread boundary screening

This screening closes the gap between the earlier 8/6/4/2 phase-thread scan.
It reuses the promoted eager shared-expert image, 2 GiB cgroup-v2 limit, zero
swap, eight prefill threads, poll 50, 128 KB readahead, and cold `pp64/tg16`.

| Decode threads | Samples | Prefill | Decode | Wall | Decision |
| ---: | ---: | ---: | ---: | ---: | --- |
| 5 | 1 | 4.296201 t/s | 0.816189 t/s | 55.40 s | reject |
| 6 | 2 | 4.298078 t/s | 0.834153 t/s | 55.31 s | keep |
| 7 | 1 | 4.167850 t/s | 0.847838 t/s | 55.89 s | reject |

Seven decode threads raised decode throughput by about 1.64% relative to the
six-thread reference median, but reduced prefill by about 3.03% and increased
wall time. Five threads reduced decode throughput without a wall-time gain.
Neither screening point improved both decode and end-to-end latency, so no
second sample was warranted. The finalist remains eight prefill threads and
six decode threads.
