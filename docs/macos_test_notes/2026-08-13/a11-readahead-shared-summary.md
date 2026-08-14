# A11 readahead and shared-residency interaction

A11 re-profiled block-device readahead after enabling eager shared-expert
residency. All runs use the same A8 image and model, 2 GiB cgroup-v2 memory,
zero swap, eight prefill threads, six decode threads, poll 50, cold
`pp64/tg16`, and the `mq-deadline` scheduler.

| Readahead | Samples | Prefill | Decode | Wall | Major faults | Input blocks |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 KB | 2 | 4.298078 t/s | 0.834153 t/s | 55.31 s | 467,453 | 195,971,980 |
| 192 KB | 1 | 4.402117 t/s | 0.813688 t/s | 53.94 s | 398,937 | 205,235,368 |
| 256 KB | 2 | 4.732164 t/s | 0.803479 t/s | 51.77 s | 342,725.5 | 208,376,904 |

Relative to 128 KB, the 256 KB median improved prefill by 10.10%, reduced wall
time by 6.41%, and reduced major faults by 26.68%. It traded 3.68% decode
throughput and 6.33% more input blocks for that latency gain. Both 256 KB runs
reproduced the direction. The 192 KB screening point landed between the two
profiles and did not dominate either endpoint.

The finalist keeps two device-specific profiles: 128 KB for decode-oriented
throughput and 256 KB for prefill/end-to-end latency. Readahead is not
hard-coded because the physical target's SD/eMMC/NVMe behavior can differ from
Colima's virtio block device. Every temporary run restored the local device to
`128 KB + mq-deadline`; the target board must choose between the two profiles.
