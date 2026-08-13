# A7 threadpool polling diagnostic

This paired 2 GiB cold-cache diagnostic changes only llama.cpp threadpool
polling from the upstream value of 50 to 100. Both runs use the same A7 image,
8/6 phase split, 128 KB block readahead, zero swap, and `pp64/tg16`.

| Poll | Prefill | Decode | Wall | Major faults | Filesystem input blocks |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 4.451482 t/s | 0.861519 t/s | 53.39 s | 488,742 | 199,342,224 |
| 100 | 4.335867 t/s | 0.741505 t/s | 58.42 s | 489,088 | 200,111,440 |

Poll 100 reduced prefill by 2.60%, reduced decode by 13.93%, and increased wall
time by 9.42% in the structured pair. An earlier direct screening run showed
the opposite direction, which demonstrates large cold-page-cache variance and
is insufficient for promotion. The harness keeps `SLIM_ARC_POLL=0..100` for
per-device scans, while the finalist default remains the upstream value 50.
