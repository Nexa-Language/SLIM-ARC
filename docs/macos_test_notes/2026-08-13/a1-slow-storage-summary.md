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
| A1 pressure | cold | latest-wins + pressure admission, 512 MiB reserve | **57.16 s** | **3.951332 t/s** | **0.799665 t/s** | **102.247 GB** | 409,985 | success |
| A1 pressure | warm | same as above | 49.49 s | 4.267432 t/s | 1.212909 t/s | 78.100 GB | 261,503 | success |
| A1 pressure, 1 GiB | cold | same policy, 1 GiB memory cap | 59.46 s | 3.544539 t/s | 0.802944 t/s | 102.439 GB | 418,176 | success |
| A1 pressure, 1 GiB | warm | same policy, 1 GiB memory cap | 57.27 s | 3.593174 t/s | 0.802087 t/s | 98.100 GB | 389,402 | success |
| A1 normal | cold | same as A1 pressure, dynamic advice disabled | 64.62 s | 3.499077 t/s | 0.682863 t/s | 117.127 GB | 251,503 | success, negative |
| A1 random | cold | latest-wins + decode `MADV_RANDOM` | >120 s | NA | NA | NA | NA | stopped, negative |

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

## Interpretation

At a 1--2 GiB physical-memory cap, the active layer/expert `WILLNEED` streams
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
