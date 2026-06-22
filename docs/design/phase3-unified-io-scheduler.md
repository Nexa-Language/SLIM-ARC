# Phase 3: Unified I/O Bandwidth Budget Scheduler

## SLIM-ARC Core Innovation

### Problem Statement

Existing approaches optimize I/O for individual data types independently:
- FlexInfer: prefetches model weights only
- DUAL-BLADE: offloads KV Cache only
- MobileMoE: predicts expert activation only

When these techniques coexist, they **compete** for the same I/O bandwidth
without coordination, leading to:
1. Bandwidth oversubscription (all three prefetch simultaneously)
2. Priority inversion (low-priority I/O blocks critical path)
3. Suboptimal global throughput (locally optimal ≠ globally optimal)

### Core Insight

> **In a memory-constrained edge device, weight offloading, KV cache
> paging, and MoE expert prefetch all share the same NVMe bandwidth.
> Optimal performance requires a unified scheduler that allocates bandwidth
> based on runtime phase (Prefill/Decode), context length, and model
> architecture.**

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Unified I/O Bandwidth Scheduler                 │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Bandwidth Budget Allocator                │   │
│  │                                                      │   │
│  │  Phase     │ Weight │ KV Cache │ MoE Expert │ Total│   │
│  │  ─────────┼────────┼──────────┼────────────┼──────│   │
│  │  Prefill  │  60%   │   10%    │    30%     │ 100% │   │
│  │  Decode-S │  70%   │   20%    │    10%     │ 100% │   │
│  │  Decode-L │  30%   │   60%    │    10%     │ 100% │   │
│  │  MoE-Dec  │  20%   │   20%    │    60%     │ 100% │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐         │
│  │ Weight    │  │ KV Cache  │  │ MoE Expert       │         │
│  │ Prefetch  │  │ Swap Mgr  │  │ Predictor         │         │
│  │ Module    │  │ Module    │  │ Module            │         │
│  └─────┬────┘  └─────┬─────┘  └────────┬────────┘         │
│        └──────────────┼──────────────────┘                  │
│               ┌───────▼───────┐                             │
│               │  Async I/O    │                             │
│               │  Thread Pool   │                             │
│               └───────┬───────┘                             │
│                       │                                     │
│               ┌───────▼───────┐                             │
│               │  NVMe SSD      │                             │
│               └───────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

### Bandwidth Allocation Algorithm

```python
def allocate_bandwidth(phase, context_len, is_moe, budget):
    """Allocate I/O bandwidth across weight, KV, and expert prefetch."""
    weights = {
        "prefill_short":  (0.60, 0.10, 0.30),  # compute-bound
        "prefill_long":   (0.50, 0.20, 0.30),  # KV growing
        "decode_short":   (0.70, 0.20, 0.10),  # weight-bound
        "decode_long":    (0.30, 0.60, 0.10),  # KV-bound
        "moe_decode":     (0.20, 0.20, 0.60),  # expert-bound
    }

    if is_moe and phase == "decode":
        key = "moe_decode"
    elif phase == "prefill":
        key = "prefill_long" if context_len > 4096 else "prefill_short"
    else:  # decode
        key = "decode_long" if context_len > 4096 else "decode_short"

    w_weight, w_kv, w_expert = weights[key]
    return {
        "weight":  budget * w_weight,
        "kv":      budget * w_kv,
        "expert":  budget * w_expert,
    }
```

### Dynamic Adaptation

The scheduler monitors real-time I/O latency and adjusts allocation:

```
 every 100ms:
   1. Measure actual bandwidth consumed per category
   2. If weight prefetch is stalling compute → increase weight budget
   3. If KV swap-in is causing page faults → increase KV budget
   4. If MoE expert miss rate > 20% → increase expert budget
   5. Rebalance to fill total budget (avoid idle bandwidth)
```

### Implementation

#### Data Structures

```cpp
struct io_budget {
    size_t weight_bytes;   // weight prefetch budget
    size_t kv_bytes;       // KV cache swap budget
    size_t expert_bytes;   // expert prefetch budget
    size_t total_bytes;    // total I/O budget per cycle
};

struct io_stats {
    double weight_latency;     // avg weight prefetch latency
    double kv_latency;         // avg KV swap latency
    double expert_miss_rate;   // expert prediction miss rate
    double bandwidth_utilization;  // actual / budget
};
```

#### Scheduler Loop

```cpp
void unified_scheduler::tick() {
    auto budget = allocate_budget(phase_, context_len_, is_moe_);

    // Issue prefetch requests within budget
    weight_prefetcher_.prefetch_within(budget.weight_bytes);
    kv_swapper_.swap_within(budget.kv_bytes);
    expert_predictor_.prefetch_within(budget.expert_bytes);

    // Monitor and adapt
    if (++tick_count_ % 10 == 0) {
        adapt_allocation();
    }
}
```

### Expected Benefits

| Scenario | Without Scheduler | With Scheduler | Improvement |
|----------|------------------|----------------|------------|
| Dense, short context | Weight-only prefetch | Weight-prioritized | +5-10% |
| Dense, long context | Weight + KV contention | KV-prioritized decode | +20-30% |
| MoE, short context | All experts loaded | Expert prediction | +40-60% |
| MoE, long context | Triple contention | Balanced allocation | +50-80% |

### Evaluation Plan

1. **Microbenchmark**: Each module in isolation vs unified
2. **Ablation**: Remove one module at a time
3. **End-to-end**: Full pipeline with all modules + unified scheduler
4. **Adaptation**: Measure convergence speed of dynamic allocation

### Novelty vs Prior Work

| Feature | FlexInfer | DUAL-BLADE | MobileMoE | **SLIM-ARC** |
|---------|-----------|------------|-----------|--------------|
| Weight prefetch | ✓ | ✗ | ✗ | ✓ |
| KV offloading | ✗ | ✓ | ✗ | ✓ |
| Expert prediction | ✗ | ✗ | ✓ | ✓ |
| Unified scheduling | ✗ | ✗ | ✗ | **✓** |
| Dynamic adaptation | ✗ | ✗ | ✗ | **✓** |
| Phase awareness | ✗ | ✗ | ✗ | **✓** |

## References

- FlexInfer: Weight-only prefetch (EuroMLSys 2025)
- DUAL-BLADE: KV-only NVMe-direct offloading
- MobileMoE: Expert-only prediction
- PowerInfer-2: Smartphone hybrid inference (closest competitor)
