# Memory Access Profile: olmoe-1b-7b-0924-instruct-q4_k_m.gguf

## Model Architecture

- Architecture: `olmoe`
- Layers: 16
- Embedding dim: 2048
- FFN dim: 1024
- Attention heads: 16 (KV: 16)
- Experts: 64 (MoE)
- Total tensors: 195
- Total tensor size: 3.92 GiB
- File size: 3.92 GiB

## Tensor Size by Quantization Type

| Type | Size (MiB) | % |
|------|-----------|---|
| Q4_K | 3061.3 | 76.2% |
| Q6_K | 946.8 | 23.6% |
| F32 | 8.5 | 0.2% |

## Per-Layer Tensor Size Breakdown

| Layer | Total (MiB) | Attn QKV (MiB) | FFN Gate/Up (MiB) | FFN Down (MiB) |
|-------|------------|----------------|-------------------|----------------|
| 0 | 259.6 | 7.8 | 144.5 | 105.0 |
| 1 | 259.6 | 7.8 | 144.5 | 105.0 |
| 2 | 225.5 | 6.8 | 144.5 | 72.0 |
| 3 | 225.5 | 6.8 | 144.5 | 72.0 |
| 4 | 259.6 | 7.8 | 144.5 | 105.0 |
| 5 | 225.5 | 6.8 | 144.5 | 72.0 |
| 6 | 225.5 | 6.8 | 144.5 | 72.0 |
| 7 | 258.5 | 6.8 | 144.5 | 105.0 |
| 8 | 226.6 | 7.8 | 144.5 | 72.0 |
| 9 | 225.5 | 6.8 | 144.5 | 72.0 |
| ... | ... | ... | ... | ... |

- Average layer size: 242.5 MiB
- Non-layer tensors: 135.9 MiB

## Prefetch Scheduling Insights

- Each layer is ~243 MiB
- With window=3, prefetch budget: ~728 MiB
- FFN dominates: 3728.0 MiB total
- MoE model: expert prediction can reduce I/O by ~(1-1/64)*100%
