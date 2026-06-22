# Phase 2d: Tile-Level Pipeline + Fused Dequantization

## Overview

SLIM-ARC Phase 2d implements tile-level pipelining and fused
dequantization to improve CPU cache hit rates and reduce memory
bandwidth consumption during computation.

## Motivation

Current tensor-level prefetch loads entire weight tensors (e.g., 60 MiB
per layer for Qwen3-4B) before computation begins. This causes:
1. **Cache flushing**: Large tensors evict useful data from L2/L3 cache
2. **Memory bandwidth waste**: Dequantized tensors written back to RAM
3. **Pipeline stalls**: Compute waits for entire tensor to load

## Design

### Tile-Level Pipeline

```
Traditional (tensor-level):
  Load W_Q (60 MiB) → Compute Q → Load W_K (60 MiB) → Compute K → ...

Tile-level (block pipeline):
  Load Tile[0] of W_Q → Compute Tile[0]
       Load Tile[1] of W_Q → Compute Tile[1]    (overlap)
            Load Tile[2] of W_Q → Compute Tile[2] (overlap)
  ...
```

### Tile Size Selection

```python
def select_tile_size(cpu_cache, tensor_shape, dtype):
    L2_size = cpu_cache.l2  # e.g., 2 MiB for i9-13900H
    element_size = dtype.element_size  # e.g., 0.5 bytes for Q4_K

    # Target: tile fits in L2 with room for input/output
    target_tile = L2_size * 0.5  # use 50% of L2
    tile_elements = target_tile / element_size

    # Align to block boundary (Q4_K: 256 elements)
    tile_elements = (tile_elements // 256) * 256

    return tile_elements
```

For i9-13900H (L2=2MiB, Q4_K):
- Tile size: ~1 MiB = 2M elements
- Tensor split: 60 MiB / 1 MiB = 60 tiles

### Fused Dequantization

```
Traditional:
  SSD → [Load Q4_K tile] → RAM → [Dequant to F16] → RAM → [MatMul] → Output

Fused:
  SSD → [Load Q4_K tile] → L2 Cache → [Dequant + MatMul fused] → Output
```

The dequantization happens in-register, never writing the F16 intermediate
to memory. This eliminates the "double bandwidth" problem.

### Implementation

```cpp
void tiled_compute(const ggml_tensor * weight, const ggml_tensor * input,
                   ggml_tensor * output, int tile_size) {
    int n_tiles = weight->ne[0] / tile_size;

    for (int t = 0; t < n_tiles; ++t) {
        // 1. Prefetch next tile (async I/O)
        if (t + 1 < n_tiles) {
            prefetch_scheduler.notify_tile(weight, t + 1, tile_size);
        }

        // 2. Dequantize + compute current tile (fused)
        fused_dequant_matmul(
            get_tile_ptr(weight, t, tile_size),  // Q4_K data in L2
            input,
            get_output_tile_ptr(output, t),
            tile_size
        );
    }
}
```

### Expected Benefits

| Metric | Tensor-level | Tile-level | Improvement |
|--------|-------------|-----------|------------|
| L2 hit rate | ~20% | ~80% | +300% |
| Memory bandwidth | 2x (dequant+compute) | 1x (fused) | -50% |
| Pipeline overlap | None (load all → compute all) | Full (load t+1 while compute t) | Yes |

## Risks

- Tile size tuning is CPU-specific (L2/L3 cache size varies)
- Fused dequant kernel requires custom ggml ops
- Small tiles increase loop overhead

## Evaluation

1. Measure L2 cache misses with `perf stat -e cache-misses`
2. Compare tile-level vs tensor-level throughput
3. Test different tile sizes (128K, 256K, 512K, 1M, 2M)
4. Profile fused vs separate dequant+matmul
