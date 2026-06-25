# SLIM-ARC Baseline Results (Upstream llama.cpp, no prefetch)

Date: 2026-06-21
Build: 7c082bc (1)
Model: Qwen3-4B-Q4_K_M (2.32 GiB, 4.02B params)

## Unconstrained Environment (32GB RAM, i9-13900H all cores)

| Test | Threads | Result (tok/s) |
|------|---------|----------------|
| pp64 (prefill) | 4 | 41.77 ± 1.45 |
| tg32 (decode) | 4 | 8.33 ± 0.61 |
| pp64 (prefill) | 4 | 39.40 ± 5.57 (SLIM-ARC build) |
| tg32 (decode) | 4 | 8.12 ± 0.42 (SLIM-ARC build) |

## 8GB + 4-core (slim-arc-low cgroup, warm cache)

| Test | Threads | Result (tok/s) |
|------|---------|----------------|
| pp64 (prefill) | 4 | 39.80 ± 0.81 |
| tg32 (decode) | 4 | 9.74 ± 0.79 |

## OLMoE-1B-7B (MoE model, unconstrained)

| Test | Threads | Result (tok/s) |
|------|---------|----------------|
| pp64 (prefill) | 4 | 97.61 ± 4.74 |
| tg32 (decode) | 4 | 26.45 ± 1.97 |

## Notes

- Qwen3-4B (2.5GB) fits entirely in 8GB RAM, so prefetch has minimal effect
- OLMoE-1B-7B (3.92GB) also fits in 8GB but demonstrates MoE baseline
- Qwen3-Next-80B-A3B (45GB) will require mmap-based offloading to test prefetch benefits
- True prefetch benefits will appear with models exceeding RAM or with cold cache
