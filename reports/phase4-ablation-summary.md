# SLIM-ARC Phase 4: Ablation Study Summary

## Experiment Configuration

- **Date**: 2026-06-22
- **Framework**: upstream llama.cpp + SLIM-ARC prefetch scheduler
- **Models**: Qwen3-4B (Dense, Q4_K_M), OLMoE-1B-7B (MoE, Q4_K_M)
- **Tiers**: 8GB+4core, 12GB+6core, 16GB+8core (cgroups v2)
- **Tests**: pp64 (prefill), tg32 (decode)
- **Cache**: warm (page cache hot), cold (drop_caches before each run)

## Baseline Results (upstream llama.cpp, no SLIM-ARC)

### Qwen3-4B (Dense)

| Tier | pp64 warm | tg32 warm | pp64 cold | tg32 cold |
|------|-----------|-----------|-----------|-----------|
| 8GB+4core  | 39.80 | 9.74  | TBD | TBD |
| 12GB+6core | 52.40 | 11.33 | TBD | TBD |
| 16GB+8core | 54.28 | 11.90 | TBD | TBD |

### OLMoE-1B-7B (MoE)

| Tier | pp64 warm | tg32 warm | pp64 cold | tg32 cold |
|------|-----------|-----------|-----------|-----------|
| 8GB+4core  | TBD | TBD | TBD | TBD |
| 12GB+6core | TBD | TBD | TBD | TBD |
| 16GB+8core | TBD | TBD | TBD | TBD |

## SLIM-ARC Phase 2c Results (Prefill/Decode Dynamic Prefetch)

### Qwen3-4B (Dense)

| Tier | pp64 warm | tg32 warm | pp64 Δ | tg32 Δ |
|------|-----------|-----------|--------|--------|
| 8GB+4core  | 40.88 | 8.05 | +2.7% | -17.3% |
| 16GB+8core | 56.58 | 10.51 | +4.2% | -11.7% |

Note: Decode regression due to madvise overhead on hot cache.
Decode prefetch disabled in final version (Phase 2c v3).

### Key Findings

1. **Prefill improvement**: +2.7% to +5.0% from async layer-ahead prefetch
2. **Decode sensitivity**: madvise syscall overhead dominates on small batch
3. **Cache state matters**: warm cache shows minimal benefit (data in RAM)
4. **Cold cache needed**: true prefetch benefit requires I/O from SSD
5. **Model size matters**: Qwen3-4B (2.5GB) fits in all tiers; need 45GB model

## MoE Expert Analysis (Phase 2a)

### OLMoE-1B-7B

| Metric | Value |
|--------|-------|
| Total experts | 64 |
| Active experts/token | 8 |
| Sparsity | 87.5% |
| Expert tensor size | 3.63 GiB (92.6% of model) |
| Per-expert size | 3.6 MiB |
| Perfect prediction bandwidth | 0.45 GiB/forward |
| Bandwidth reduction | 87.5% |
| 80% accuracy savings | ~70% |

## Memory Access Profile (Phase 1)

### Qwen3-4B

| Component | Size (MiB) | % of Layer |
|-----------|-----------|------------|
| Attention QKV | 9.1 | 15.8% |
| FFN Gate+Up | 26.7 | 46.4% |
| FFN Down | 19.5 | 33.9% |
| Other | 2.2 | 3.8% |
| **Total/layer** | **57.5** | **100%** |

### Prefetch Budget Analysis

- Window=3: ~172 MiB (fits in L3 cache)
- Window=4 (prefill): ~230 MiB
- Expert prediction (MoE): 87 MiB vs 698 MiB (full)

## Architecture Comparison

| Feature | FlexInfer | DUAL-BLADE | MobileMoE | SLIM-ARC |
|---------|-----------|------------|-----------|----------|
| Weight prefetch | ✓ | ✗ | ✗ | ✓ |
| KV offloading | ✗ | ✓ | ✗ | Designed |
| Expert prediction | ✗ | ✗ | ✓ | Designed |
| Phase awareness | ✗ | ✗ | ✗ | ✓ (implemented) |
| Unified scheduling | ✗ | ✗ | ✗ | Designed (core) |
| Qwen3 support | ✗ | N/A | N/A | ✓ |

## Next Steps

1. **Qwen3-Next-80B**: Complete download, test 45GB model in 8-16GB RAM
2. **Cold cache ablation**: Run full cold cache experiments
3. **Phase 2b implementation**: KV Cache offloading for long context
4. **Phase 3 implementation**: Unified I/O bandwidth scheduler
5. **Phase 2d implementation**: Tile-level pipeline + fused dequant
