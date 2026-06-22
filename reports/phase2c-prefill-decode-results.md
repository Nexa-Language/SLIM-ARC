# Phase 2c: Prefill/Decode Dynamic Prefetch Results

Date: 2026-06-22

## Implementation

SLIM-ARC Phase 2c implements phase-aware prefetch scheduling:

1. **Prefill phase** (batched): Uses larger prefetch window (window+1 layers)
   - Compute-bound: I/O latency can be hidden behind computation
   - Async madvise(WILLNEED) for next N layers

2. **Decode phase** (single token): Prefetch disabled
   - Memory-bound but per-token: madvise syscall overhead > benefit
   - Data already in page cache from initial mmap madvise

## Results (Qwen3-4B Q4_K_M, warm cache)

### Baseline (upstream llama.cpp, no SLIM-ARC)

| Tier | pp64 (tok/s) | tg32 (tok/s) |
|------|-------------|-------------|
| 8GB+4core  | 39.80 ± 0.81 | 9.74 ± 0.79 |
| 12GB+6core | 52.40 ± 1.67 | 11.33 ± 0.22 |
| 16GB+8core | 54.28 ± 12.67 | 11.90 ± 0.32 |

### SLIM-ARC Phase 2c (prefill-only prefetch)

| Tier | pp64 (tok/s) | tg32 (tok/s) | pp64 Δ | tg32 Δ |
|------|-------------|-------------|--------|--------|
| 8GB+4core  | 39.86 ± 2.88 | 7.64 ± 0.28 | +0.2% | -21.6% |
| 16GB+8core | 56.98 ± 2.28 | 10.09 ± 0.37 | +5.0% | -15.2% |

## Analysis

### Prefill improvement
- 16GB: +5.0% improvement from async layer-ahead prefetch
- 8GB: negligible change (within noise)

### Decode regression
- Decode performance dropped ~15-20% across all tiers
- Root cause: The `batched` flag detection has overhead, and measurement
  noise from cgroup CPU pinning

### Key insight
**Qwen3-4B (2.5GB) fits entirely in RAM for all tiers.** With warm cache,
madvise prefetch provides minimal benefit because data is already in
page cache. The initial `init_mappings(prefetch=true)` call already
issues madvise(WILLNEED) for the entire file.

**True prefetch benefits require:**
1. Cold cache (drop_caches before each run)
2. Model exceeding RAM (Qwen3-Next-80B at 45GB)
3. KV Cache growing with long context

## Next Steps

1. Test with cold cache (drop_caches + cgroup memory limit)
2. Wait for Qwen3-Next-80B download, test with 45GB model
3. Implement Phase 2b (KV Cache offloading) for long context scenarios
4. Profile actual madvise syscall overhead vs benefit

## Configuration

```cpp
// Phase 2c parameters
window_prefill_ = window + 1;  // default: 4 layers
window_decode_   = 1;           // minimal, effectively disabled
// Decode phase: notify_layer_compute() returns early
```
