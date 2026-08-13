# A5 selective expert access-advice diagnostic

This cold-cache 2 GiB diagnostic isolates decode-only `MADV_RANDOM` on merged
MoE expert tensors while shared attention and router weights retain sequential
advice. Both runs use the same A5 image, 8 prefill threads, 6 decode threads,
128 KB block readahead, zero swap, and `pp64/tg16`.

| Configuration | Prefill | Decode | Wall | Major faults | Filesystem input blocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 4.169861 t/s | 0.800984 t/s | 55.90 s | 487,853 | 199,690,872 |
| Expert RANDOM | 4.447359 t/s | 0.261757 t/s | 96.42 s | 3,866,199 | 195,199,384 |

Selective random advice reduced input blocks by only 2.25%, but increased major
faults by 692.49%, reduced decode throughput by 67.32%, and increased wall time
by 72.49%. All 2,304 expert advice calls succeeded, so the regression is the
expected cost of disabling readahead rather than an advice failure.

The option remains strictly opt-in and is rejected for the finalist default.
The result establishes that sparse expert access still benefits from bounded
kernel readahead; the next diagnostic should use adaptive `MADV_NORMAL` rather
than fully random access.
