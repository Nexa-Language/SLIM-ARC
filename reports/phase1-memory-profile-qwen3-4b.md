# Memory Access Profile: Qwen3-4B-Q4_K_M.gguf

## Model Architecture

- Architecture: `qwen3`
- Layers: 36
- Embedding dim: 2560
- FFN dim: 9728
- Attention heads: 32 (KV: 8)
- Total tensors: 398
- Total tensor size: 2.32 GiB
- File size: 2.33 GiB

## Tensor Size by Quantization Type

| Type | Size (MiB) | % |
|------|-----------|---|
| Q4_K | 1683.3 | 70.8% |
| Q6_K | 691.9 | 29.1% |
| F32 | 0.7 | 0.0% |

## Per-Layer Tensor Size Breakdown

| Layer | Total (MiB) | Attn QKV (MiB) | FFN Gate/Up (MiB) | FFN Down (MiB) |
|-------|------------|----------------|-------------------|----------------|
| 0 | 60.9 | 9.1 | 26.7 | 19.5 |
| 1 | 60.9 | 9.1 | 26.7 | 19.5 |
| 2 | 60.9 | 9.1 | 26.7 | 19.5 |
| 3 | 60.9 | 9.1 | 26.7 | 19.5 |
| 4 | 54.2 | 8.4 | 26.7 | 13.4 |
| 5 | 54.2 | 8.4 | 26.7 | 13.4 |
| 6 | 60.9 | 9.1 | 26.7 | 19.5 |
| 7 | 54.2 | 8.4 | 26.7 | 13.4 |
| 8 | 54.2 | 8.4 | 26.7 | 13.4 |
| 9 | 60.9 | 9.1 | 26.7 | 19.5 |
| ... | ... | ... | ... | ... |

- Average layer size: 57.5 MiB
- Non-layer tensors: 304.3 MiB

## Prefetch Scheduling Insights

- Each layer is ~58 MiB
- With window=3, prefetch budget: ~173 MiB
- FFN dominates: 1553.0 MiB total
