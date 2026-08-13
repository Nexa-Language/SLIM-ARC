# A4 phase-specific CPU thread scan

This diagnostic keeps the prefill graph at eight CPU threads and reduces only
the decode graph thread count. Every run uses the same A4 image, verified 80A3B
Q4_K_M model, 2 GiB cgroup-v2 memory limit, zero swap, CPU-only mmap loading,
`pp64/tg16`, cold cache, slow-storage mode, and pressure admission with a 512
MiB reserve.

## Paired result

| Configuration | Samples | Prefill median | Decode median | Wall median | Major faults median |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 prefill / 8 decode | 2 | 3.810514 t/s | 0.593447 t/s | 67.145 s | 499,949.5 |
| 8 prefill / 6 decode | 2 | 3.823594 t/s | 0.713499 t/s | 63.180 s | 473,289.0 |

The 8/6 candidate improved observed median decode throughput by **20.23%**,
kept prefill effectively flat at **+0.34%**, reduced wall time by **5.91%**,
reduced major faults by **5.33%**, and reduced filesystem input blocks by
**1.12%**. Both candidate runs completed at the 2 GiB limit with zero swap and
no OOM.

The exploratory 8/4 run reached 0.660411 decode t/s. The 8/2 run fell to
0.582453 decode t/s, showing that over-reducing decode parallelism crosses the
compute/I/O balance point. The selected finalist candidate is therefore:

```text
SLIM_ARC_SLOW_STORAGE=1
SLIM_ARC_PRESSURE_ADMISSION=1
SLIM_ARC_PRESSURE_RESERVE_MB=512
SLIM_ARC_PREFILL_THREADS=8
SLIM_ARC_DECODE_THREADS=6
```

This is a two-sample local Colima diagnostic, not a cross-device performance
claim. The phase split remains opt-in until it is re-profiled on the remote
slow-storage board.

## Storage readahead combination

Two single-run combinations expose a device-policy Pareto frontier. At 256 KB
readahead, 8/6 reached the highest observed prefill throughput of 4.219298 t/s,
0.647837 decode t/s, and 60.27 seconds wall time. At 512 KB it reached 3.938531
prefill t/s, 0.634405 decode t/s, and the shortest observed wall time of 59.63
seconds. The larger window reduced major faults but increased filesystem input
blocks and lost decode throughput relative to the 128 KB 8/6 candidate.

Readahead is therefore not hard-coded: 128 KB is the decode-oriented default,
256 KB is the prefill-oriented local candidate, and 512 KB is a latency-oriented
diagnostic that must be re-profiled on the target storage device. Every temporary
setting was restored to `128 KB + mq-deadline` after its run.
