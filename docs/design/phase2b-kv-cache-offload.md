# Phase 2b: KV Cache Asynchronous Offloading Design

## Overview

SLIM-ARC Phase 2b implements KV Cache offloading to extend context length
beyond physical RAM. Inspired by DUAL-BLADE and ScoutAttention.

## Motivation

In long-context inference (16K-32K tokens), KV Cache grows linearly:
- Qwen3-4B: 36 layers × 8 KV heads × 128 head_dim × 2 (K+V) × 32768 tokens
  ≈ 2.3 GB at 32K context (F16)
- This exceeds 8GB budget when combined with model weights (2.5GB)

## Design

### Architecture

```
┌─────────────────────────────────────────────┐
│           KV Cache Manager                  │
│                                             │
│  ┌─────────┐  ┌─────────┐  ┌───────────┐  │
│  │ Hot KV  │  │ Warm KV │  │ Cold KV   │  │
│  │ (RAM)   │  │ (RAM)   │  │ (mmap→SSD)│  │
│  └────┬────┘  └────┬────┘  └─────┬─────┘  │
│       │            │             │         │
│  sink tokens   sliding window  evicted     │
│  (permanent)   (recent N tok)  (old tok)   │
└─────────────────────────────────────────────┘
```

### Tiered KV Cache Strategy

1. **Hot (permanent in RAM)**: First K tokens (sink tokens, ~4 tokens)
   - Always resident, needed for attention stability

2. **Warm (RAM, LRU)**: Recent N tokens (sliding window)
   - Size = min(context_window, memory_budget / 2)
   - Default: 4096 tokens

3. **Cold (mmap to SSD)**: Evicted older tokens
   - Written to temp file via mmap
   - Prefetched back when attention scores indicate importance

### Attention-Score Based Eviction

```python
def should_evict(kv_block, attention_scores):
    if kv_block.is_sink:
        return False  # Never evict sink tokens
    avg_score = mean(attention_scores[kv_block.range])
    return avg_score < threshold  # default: 0.01
```

### Integration Points

1. **llama-kv-cache.cpp**: Add eviction logic in `kv_cache_update()`
2. **llama-context.cpp**: Hook into graph_compute for async prefetch
3. **slim-arc-prefetch.cpp**: Extend scheduler to handle KV blocks

### Async Swap Pipeline

```
Compute Layer N:
  1. Read hot + warm KV for layer N (from RAM)
  2. Async prefetch cold KV for layer N+1 (if needed)
  3. Async evict coldest KV from layer N-2 to SSD
```

## Implementation Plan

### Step 1: KV Cache Profiling
- Measure KV Cache size at different context lengths
- Identify when KV exceeds memory budget

### Step 2: Eviction Policy
- Implement attention score tracking (lightweight)
- StreamingLLM-style sink + sliding window

### Step 3: Async Swap
- Use mmap + madvise for cold KV blocks
- Reuse prefetch_scheduler worker threads

### Step 4: Evaluation
- Compare perplexity (PPL) with/without eviction
- Measure throughput at 16K/32K context

## Risks

- Attention score tracking adds compute overhead
- Eviction may cause PPL degradation
- mmap swap latency may exceed computation time for small models

## References

- DUAL-BLADE: NVMe-direct dual-path KV offloading
- ScoutAttention: Layer-ahead CPU pre-computation
- HillInfer: Hierarchical KV eviction with SmartSSD
- StreamingLLM: Sink token + sliding window attention
