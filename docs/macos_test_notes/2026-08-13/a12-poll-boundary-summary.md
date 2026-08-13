# A12 worker-poll boundary screening

A12 screened worker-pool polling on the promoted 2 GiB shared-residency stack.
All runs use zero swap, eight prefill threads, six decode threads, 128 KB
readahead, `mq-deadline`, and cold `pp64/tg16`.

| Poll | Samples | Prefill | Decode | Wall | Decision |
| ---: | ---: | ---: | ---: | ---: | --- |
| 25 | 1 | 4.244326 t/s | 0.748560 t/s | 58.69 s | reject |
| 50 | 2 | 4.298078 t/s | 0.834153 t/s | 55.31 s | keep |
| 75 | 1 | 4.071907 t/s | 0.609647 t/s | 64.28 s | reject |

Poll 25 reduced decode throughput and increased end-to-end time. Poll 75 was
substantially worse, showing that extra spinning competes with slow-storage
fault handling rather than hiding it. Neither boundary improved decode and
wall time, so no second screening sample was warranted. The finalist keeps
the upstream poll value of 50.
