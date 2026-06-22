# Phase 2d: Tile 级微流水线 + 融合反量化

## 1. 背景与动机

传统张量级加载：整个权重 tensor 加载完才开始计算。对于大 tensor（如 4096×4096 权重），需要等整个 tensor 在 RAM 才能开始 GEMM。

Tile 级流水线：把 tensor 切分成 Tile（对齐 CPU L2/L3 cache 行），I/O 线程读 Tile-N 时计算线程处理 Tile-N-1，实现 I/O-计算重叠。

## 2. 当前方案的 Tile 特性

SLIM-ARC 的 mmap + MADV_RANDOM 方案**天然具备 Tile 级特性**：
- 内核 page fault 按 4KB page 粒度（类似 Tile）
- `madvise(WILLNEED)` 触发异步预读，内核在后台读 page
- 计算线程访问已加载的 page 时，I/O 线程在加载后续 page
- 这就是隐式的 Tile 级流水线（Tile = 4KB page）

## 3. 显式 Tile 流水线设计（待实现）

### 3.1 Tile 切分策略

```
权重 tensor [M, N] 切分为 Tile [T_M, T_N]:
- T_M = 64 (对齐 AVX-512 行)
- T_N = 256 (对齐 L2 cache 行)
- 每 Tile: 64 × 256 × sizeof(Q4_K_block) = 2MB (L3 cache 友好)

切分后:
| Tile[0,0] | Tile[0,1] | ... | Tile[0, N/T_N-1] |
| Tile[1,0] | Tile[1,1] | ... | ...              |
| ...                                                |
```

### 3.2 流水线调度

```
时间轴:
  I/O线程:  [读 Tile 0] [读 Tile 1] [读 Tile 2] ...
  计算线程:              [算 Tile 0] [算 Tile 1] [算 Tile 2] ...

overlap = min(I/O_time, compute_time) / max(I/O_time, compute_time)
```

### 3.3 融合反量化

Q4_K 权重计算时需要先反量化成 F32 再做 GEMM。传统方式：反量化整个 tensor → GEMM。融合方式：逐 Tile 反量化 → GEMM → 丢弃。

```cpp
for (tile_i = 0; tile_i < n_tiles; ++tile_i) {
    // 异步预取下一个 Tile
    if (tile_i + 1 < n_tiles)
        madvise(tile_addr[tile_i+1], tile_size, WILLNEED);

    // 反量化 + GEMM 当前 Tile
    dequantize_q4_k(tile_data, temp_f32, tile_m, tile_n);
    gemm_f32(temp_f32, activation, output);

    // 释放当前 Tile（mmap 页可被回收）
    madvise(tile_addr[tile_i], tile_size, DONTNEED);
}
```

## 4. 与当前 mmap 方案的关系

当前方案已通过 `madvise(WILLNEED)` 实现了**隐式 Tile 流水线**：
1. `prefetch_scheduler` 在计算 layer N 时预取 layer N+1..N+window（相当于读 Tile-N+1）
2. 内核 page cache 实现 L2/L3 友好的 4KB page 粒度
3. MADV_RANDOM 避免预读过多（精确按需）

显式 Tile 流水线（切分 tensor + 手动双缓冲）的额外收益有限，且需要修改 ggml GEMM 内核，复杂度高。

## 5. 实现路线图

### 5.1 已实现（隐式 Tile 流水线）
- mmap + MADV_RANDOM: 4KB page 粒度按需加载
- prefetch_scheduler: WILLNEED 预取后续层
- evict_layer: DONTNEED 释放已完成层

### 5.2 待实现（显式 Tile 流水线）
- 修改 ggml GEMM kernel 支持逐 Tile 计算
- 实现双缓冲：I/O buffer + compute buffer
- 融合反量化 kernel

### 5.3 预期收益
- L2/L3 cache hit rate 提升 20-40%
- I/O-计算 overlap 提升至 80%+
- 但实现复杂度高，ROI 低于 Phase 2a/2b

## 6. 结论

当前 mmap 方案已通过内核 page cache 实现了隐式 Tile 流水线，满足比赛需求。显式 Tile 流水线作为后续优化方向，预期收益 20-40% 但复杂度高，不在初赛范围内。
