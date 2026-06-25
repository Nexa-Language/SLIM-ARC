# Tile 级微流水线设计文档（未实现）

> 状态：**设计草案**，初赛未实现，列为决赛方向。

## 动机

当前 SLIM-ARC 依赖内核 page cache 的隐式 Tile 机制：page fault 以 4KB 页粒度加载。但 4KB 对于 L2/L3 cache 行（64B-128B）而言过大，且内核的预读窗口（default 128KB）可能不匹配 MoE 的稀疏访问模式。

显式 Tile 级控制可以：
1. 将权重张量切分为对齐 L2 cache（256KB-1MB）的 Tile
2. I/O 线程读 Tile-N 时，计算线程处理 Tile-N-1（软件流水线）
3. 预计带来 20-40% 的 cache 命中率提升

## 设计

### 数据结构
```cpp
struct weight_tile {
    void *  mmap_addr;      // Tile 在 mmap 中的地址
    size_t  size;           // Tile 大小（对齐 L2 cache，如 512KB）
    int     layer;
    int     tile_idx;       // 层内 Tile 序号
};
```

### 流水线调度
```
I/O Thread:  [读 Tile 0] [读 Tile 1] [读 Tile 2] ...
Compute:                [算 Tile 0] [算 Tile 1] [算 Tile 2] ...
                         ↑ I/O 与计算重叠
```

### 接口草案
```cpp
class tile_pipeline {
public:
    void register_tiles(const char * tensor_name, void * base, size_t total,
                        size_t tile_size, int layer);
    void start_pipeline(int layer);  // 启动 I/O 线程
    void * acquire_tile(int tile_idx);  // 计算线程获取已加载的 Tile
    void release_tile(int tile_idx);    // 释放供下一轮复用
};
```

## 未实现原因

1. 需要修改 llama.cpp 的 GEMM kernel 以支持 Tile 粒度输入（而非整层张量）
2. 线程同步开销可能抵消 cache 命中率提升
3. MADV_RANDOM 已将 RSS 降至 2GB，cache 压力不大

## 决赛规划

- 先实现权重张量的 Tile 切分（不改 kernel，仅切分 mmap 区域）
- 用 `posix_madvise(WILLNEED)` 对下一 Tile 预取
- 对比 cache miss 率（用 `perf stat -e cache-misses`）
- 若有效，再改 kernel 支持 Tile 输入
