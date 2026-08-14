# A15 shared-expert sustained-decode validation

A15 adds the missing no-residency `tg64` control to the A14 shared-only run.
Both runs use the same A13 image and model, 2 GiB cgroup-v2 memory, zero swap,
eight/six phase threads, poll 50, 128 KB readahead, and cold `pp64/tg64`.

| Configuration | Prefill | Sustained decode | Wall | Major faults | Input blocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| No resident set | 4.567939 t/s | 0.937357 t/s | 101.87 s | 1,461,500 | 431,568,392 |
| Shared resident | 4.609123 t/s | 1.024886 t/s | 96.36 s | 1,387,876 | 418,189,296 |

Eager residency for the 92.4 MB always-used shared-expert path improved
prefill by 0.90%, sustained decode by 9.34%, reduced wall time by 5.41%, major
faults by 5.04%, and input blocks by 3.10%. This agrees with the paired `tg16`
direction from A8 and shows a larger benefit over sustained decode.

Shared-expert residency remains the finalist resident path at 2/4 GiB. It is
disabled at 1 GiB, where A8 showed that the locked footprint makes the dynamic
page cache too fragile. The small-tensor resident path remains disabled after
A14's sustained-decode regression.
