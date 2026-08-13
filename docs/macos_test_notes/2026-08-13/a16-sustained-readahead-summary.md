# A16 sustained-decode readahead validation

A16 validates the 256 KB block-device readahead profile on sustained decode.
All runs use the same A13 image and model, 2 GiB cgroup-v2 memory, zero swap,
shared-expert residency, eight/six phase threads, poll 50, `mq-deadline`, and
cold `pp64/tg64`.

| Readahead | Samples | Prefill | Sustained decode | Wall | Major faults | Input blocks |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 KB | 1 | 4.609123 t/s | 1.024886 t/s | 96.36 s | 1,387,876 | 418,189,296 |
| 256 KB | 2 | 5.226161 t/s | 1.046367 t/s | 90.20 s | 1,027,391.5 | 451,921,532 |

Both 256 KB runs reproduced the direction. Relative to the same-stack 128 KB
reference, the 256 KB median improved prefill by 13.39%, sustained decode by
2.10%, reduced wall time by 6.39%, and reduced major faults by 25.97%. The
trade-off is 8.07% more input blocks, which is acceptable for the local
latency/TPS objective but remains storage-device dependent.

The local 2 GiB finalist profile uses pressure admission with a 512 MiB
reserve, eight prefill threads, six decode threads, poll 50, eager
shared-expert residency, and 256 KB readahead. The block parameter is not
hard-coded: it must be re-profiled on the target SD/eMMC/NVMe device. Every A16
run restored Colima to `128 KB + mq-deadline` after completion.
