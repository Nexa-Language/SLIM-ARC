# Memory Access Profile: Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf

## Model Architecture

- Architecture: `qwen3next`
- Layers: 48
- Embedding dim: 2048
- FFN dim: 5120
- Attention heads: 16 (KV: 2)
- Experts: 512 (MoE)
- Total tensors: 807
- Total tensor size: 45.08 GiB
- File size: 45.09 GiB

## Tensor Size by Quantization Type

| Type | Size (MiB) | % |
|------|-----------|---|
| Q4_K | 35617.1 | 77.2% |
| Q6_K | 10348.0 | 22.4% |
| F32 | 197.3 | 0.4% |
| F16 | 0.2 | 0.0% |

## Per-Layer Tensor Size Breakdown

| Layer | Total (MiB) | Attn QKV (MiB) | FFN Gate/Up (MiB) | FFN Down (MiB) |
|-------|------------|----------------|-------------------|----------------|
| 0 | 1020.2 | 0.0 | 581.1 | 420.8 |
| 1 | 1020.2 | 0.0 | 581.1 | 420.8 |
| 2 | 1020.2 | 0.0 | 581.1 | 420.8 |
| 3 | 1016.8 | 10.4 | 581.1 | 420.8 |
| 4 | 1020.2 | 0.0 | 581.1 | 420.8 |
| 5 | 1020.2 | 0.0 | 581.1 | 420.8 |
| 6 | 887.9 | 0.0 | 581.1 | 288.6 |
| 7 | 884.3 | 10.1 | 581.1 | 288.6 |
| 8 | 1020.2 | 0.0 | 581.1 | 420.8 |
| 9 | 887.9 | 0.0 | 581.1 | 288.6 |
| ... | ... | ... | ... | ... |

- Average layer size: 953.2 MiB
- Non-layer tensors: 410.4 MiB

## Prefetch Scheduling Insights

- Each layer is ~953 MiB
- With window=3, prefetch budget: ~2860 MiB
- FFN dominates: 44919.4 MiB total
- MoE model: expert prediction can reduce I/O by ~(1-1/512)*100%
