# A1 slow-storage diagnostic summary

This note records single-run diagnostics for the A1 slow-storage scheduler. It
is not a statistical promotion result. The runs use the verified
`Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf` model under a 1 or 2 GiB cgroup-v2
memory limit, 4 CPUs, no swap, CPU-only mmap loading, `pp64/tg16`, and one
repetition.

## Identity

- SLIM-ARC commit: `ffd79e202311ffbda8f2430ee60461835bd848d6`
- llama.cpp commit: `360e134`
- patched source SHA-256:
  `4ad6630111d760df5ab301c06dc0a6917768a7444fbb5d298054f4baadf9e4c2`
- runtime image:
  `sha256:5e9b1c4798beb6eb58c84af729777b6760bc12f55266b9c73c6033b9a91fb0df`
- model SHA-256:
  `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`

## Results

| Run | Cache | Configuration | Wall | Prefill | Decode | Device read | Major faults | Outcome |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| A0 aligned | cold | aligned/coalesced advice | 70.46 s | 3.519132 t/s | 0.587988 t/s | 115.563 GB | 397,366 | success |
| A1 latest | cold | slow-storage latest-wins | 61.33 s | 3.912382 t/s | 0.687312 t/s | 114.948 GB | 406,709 | success |
| A1 pressure, 2 GiB | cold | latest-wins + pressure admission, 512 MiB reserve | **57.16 s** | **3.951332 t/s** | **0.799665 t/s** | **102.247 GB** | 409,985 | success |
| A1 pressure, 2 GiB | warm | same as above | 49.49 s | 4.267432 t/s | 1.212909 t/s | 78.100 GB | 261,503 | success |
| A1 pressure, 1 GiB | cold | same policy, 1 GiB memory cap | 59.46 s | 3.544539 t/s | 0.802944 t/s | 102.439 GB | 418,176 | success |
| A1 pressure, 1 GiB | warm | same policy, 1 GiB memory cap | 57.27 s | 3.593174 t/s | 0.802087 t/s | 98.100 GB | 389,402 | success |
| A1 pressure, 4 GiB | cold | same policy, 4 GiB memory cap | 57.92 s | 3.387624 t/s | 1.023154 t/s | 87.055 GB | 298,402 | success |
| A1 latest, 4 GiB | cold | latest-wins weight and expert prefetch | 64.46 s | 3.977736 t/s | 0.649079 t/s | 113.120 GB | 393,082 | success, negative |
| A1 confidence, 4 GiB | cold | latest-wins + expert confidence and budget | 68.26 s | 3.589438 t/s | 0.609960 t/s | 104.001 GB | 392,853 | success, negative |
| A1 decode NORMAL, 2 GiB | cold | pressure policy, decode-only `MADV_NORMAL` | 74.94 s | 3.311175 t/s | 0.546979 t/s | 112.060 GB | 297,675 | success, negative |
| A1 normal | cold | same as A1 pressure, dynamic advice disabled | 64.62 s | 3.499077 t/s | 0.682863 t/s | 117.127 GB | 251,503 | success, negative |
| A1 random | cold | latest-wins + decode `MADV_RANDOM` | >120 s | NA | NA | NA | NA | stopped, negative |
| A2 router-only, 2 GiB | cold | all-router prefetch + no expert prefetch | 68.76 s | 3.638826 t/s | 0.703270 t/s | 102.698 GB | 409,570 | success, negative |
| A3 router mlock, 2 GiB | cold | pin 201.9 MB router path once | 68.64 s | 3.627730 t/s | 0.635464 t/s | 98.436 GB | 387,505 | success, negative |
| A3 router mlock, 4 GiB | cold | pin 201.9 MB router path once | 60.75 s | 3.610230 t/s | 0.825438 t/s | 85.025 GB | 286,475 | success, negative |
| A3 RA128, 2 GiB | cold | pressure policy, 128 KB, mq-deadline | 65.01 s | 3.469338 t/s | 0.671548 t/s | 102.365 GB | 411,047 | success |
| A3 RA256, 2 GiB | cold | pressure policy, 256 KB, mq-deadline | 63.05 s | 4.011215 t/s | 0.639735 t/s | 111.377 GB | 274,984 | success |
| A3 RA512, 2 GiB | cold | pressure policy, 512 KB, mq-deadline | 58.09 s | 4.202231 t/s | 0.674639 t/s | 119.436 GB | 189,763 | success |
| A3 RA512 none, 2 GiB | cold | pressure policy, 512 KB, none | 58.07 s | 4.105445 t/s | 0.668469 t/s | 119.469 GB | 188,969 | success |

The best cold diagnostic reduced wall time by 18.88%, increased prefill by
12.28%, increased decode throughput by 36.00%, and reduced device reads by
11.52% relative to A0. These percentages compare one cold run with one cold
run and therefore describe the observed diagnostic, not a confidence
interval.

The 1 GiB cold diagnostic reached the cgroup limit exactly, used zero swap,
and completed successfully. Relative to A0 it reduced wall time by 15.61%,
increased prefill by 0.72%, increased decode throughput by 36.56%, and reduced
device reads by 11.36%. Relative to the 2 GiB cold candidate, it traded 10.30%
of prefill throughput for half the physical-memory limit while decode was
0.41% higher in the observed run.

At 4 GiB, pressure admission reduced device reads by 23.04% and improved
decode throughput by 57.63% relative to latest-wins weight/expert prefetch.
Confidence plus budget reduced expert advice from 13.80 GB to 3.97 GB and
raised its byte hit rate from 30.72% to 47.67%, but it still lost to issuing no
speculative expert advice. Decode-only `MADV_NORMAL` was also clearly
negative; the initial and decode `SEQUENTIAL` hints remain the candidate.

A2 isolated the deterministic router path: 201.7 MB per graph, 3.43 GB of
successful advice over 17 graphs, and zero expert advice. Reissuing the whole
router path every graph increased wall time by 20.29% and reduced decode by
12.05% relative to the 2 GiB pressure candidate despite nearly identical
device-read bytes. The next experiment therefore changes this path from
repeated `WILLNEED` to a one-time bounded resident set.

A3 successfully locked the complete 201.9 MB router path once with zero lock
failures and zero runtime weight/expert advice. It reduced device reads at 2
and 4 GiB, but reserving page-cache capacity reduced decode throughput; the
router-resident path remains rejected for the extreme-memory tiers.

The block-device scan found a separate prefill trade-off. Raising virtio
`vdb` readahead from 128 to 512 KB cut major faults by 54% and raised observed
prefill from 3.47 to 4.20 t/s, but increased device reads by 16.7 GB. Switching
from `mq-deadline` to `none` at 512 KB was neutral. Every temporary block
setting was restored to `128 KB + mq-deadline` after its run; the readahead
choice must be re-profiled on the target SD/eMMC/NVMe device.

## Interpretation

At a 1--4 GiB physical-memory cap, the active layer/expert `WILLNEED` streams
compete with near-term demand-faulted pages. Pressure admission set both
weight and expert issued bytes to zero and produced the best cold result,
while retaining the initial whole-mapping sequential access hint. Disabling
that hint or using decode `MADV_RANDOM` was negative. The current 2 GiB
candidate is therefore:

```text
SLIM_ARC_SLOW_STORAGE=1
SLIM_ARC_PRESSURE_ADMISSION=1
SLIM_ARC_PRESSURE_RESERVE_MB=512
```

Raw manifests, cgroup snapshots, GNU time output, and benchmark JSONL are kept
in the sibling run directories. Regenerable Docker layers and stopped
containers were pruned; no model or benchmark result was duplicated.
