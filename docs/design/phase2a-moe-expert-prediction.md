# Phase 2a: MoE Expert Prediction Prefetch Design

## Overview

SLIM-ARC Phase 2a implements expert prediction prefetch for MoE models,
reducing I/O bandwidth by only loading activated experts instead of all.

Inspired by MobileMoE and MoE-Prism.

## Motivation

MoE models have sparse expert activation:
- OLMoE-1B-7B: 64 experts, only 8 activated per token (12.5%)
- Full expert weights: 3.92 GB
- Activated expert weights: ~490 MB (87.5% reduction potential)

Without prediction, all expert weights must be prefetched.
With prediction, only the ~8 needed experts are loaded.

## Design

### Router Predictor

```
Layer N:   Router output → top-k experts selected
           ↓ (predict layer N+1's experts)
Layer N+1: Predictor forecasts expert selection
           ↓ (async prefetch only predicted experts)
Layer N+1: Actual router runs, uses prefetched experts
```

### Prediction Strategy

1. **Naive (baseline)**: Use layer N's expert selection as predictor for N+1
   - Accuracy: ~60-70% (experts have temporal locality)
   - Zero additional compute

2. **Lightweight MLP predictor**:
   - Input: hidden state at layer N
   - Output: probability distribution over experts for N+1
   - Size: n_experts × 256 params (negligible)
   - Accuracy: ~80-85%

3. **Oracle (upper bound)**:
   - Use actual router output from layer N+1
   - Requires look-ahead, not practical but sets ceiling

### Prefetch Integration

```cpp
// In graph_compute, before MoE layer:
if (model.is_moe && prefetch_enabled) {
    auto predicted_experts = predict_experts(hidden_state, layer);
    scheduler.prefetch_experts(layer + 1, predicted_experts);
}
```

### Bandwidth Savings

For OLMoE-1B-7B (64 experts, 8 active):
- Without prediction: prefetch all 64 experts → 3.92 GB/layer
- With perfect prediction: prefetch 8 experts → 490 MB/layer
- Bandwidth reduction: 87.5%

For Qwen3-Next-80B-A3B (128 experts, 8 active):
- Without prediction: prefetch all → ~40 GB/layer
- With perfect prediction: 8/128 = 6.25% → ~2.5 GB/layer
- Bandwidth reduction: 93.75%

## Implementation Plan

### Step 1: Expert Activation Profiling
- Run OLMoE on test prompts
- Log which experts are activated per token per layer
- Analyze temporal locality and prediction accuracy

### Step 2: Naive Predictor
- Implement layer-N-to-N+1 expert prediction
- Measure prediction accuracy on test set

### Step 3: Prefetch Integration
- Extend prefetch_scheduler with expert-level granularity
- Only madvise predicted expert tensors

### Step 4: Lightweight MLP Predictor (optional)
- Train small predictor network
- Integrate into inference pipeline

## Evaluation Metrics

1. **Prediction accuracy**: % of correctly predicted experts
2. **Bandwidth reduction**: actual bytes prefetched vs full
3. **Throughput improvement**: tok/s with vs without prediction
4. **Latency impact**: additional predictor compute time

## References

- MobileMoE: On-device MoE with expert caching
- MoE-Prism: Expert disentanglement for elastic services
- Distributed MoE: Latency-optimized expert placement
