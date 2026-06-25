# KV Cache Eviction API 文档

> 源码：`src/llama-upstream/src/slim-arc-kv-eviction.h` / `.cpp`

## 概述

`kv_eviction_manager` 实现 StreamingLLM 式的分层 KV Cache 管理：
- **Hot（sink）**：前 N 个 token 永久驻留 RAM，稳定 softmax 分母
- **Warm（window）**：最近 W 个 token 滑动窗口
- **Cold**：被驱逐的中间 token，可选 offload 到 SSD mmap 文件

## 配置结构

```cpp
struct kv_eviction_config {
    size_t sink_tokens   = 4;       // 永久热 token 数
    size_t window_tokens = 4096;    // 滑动窗口大小
    size_t budget_bytes  = 0;       // 内存预算（0=无限）
    double evict_threshold = 0.01;  // attention 分数驱逐阈值
    bool   enable_offload = false;  // 是否 offload 到 SSD
    std::string offload_path;       // mmap 临时文件路径
};
```

## 类接口

```cpp
class kv_eviction_manager {
public:
    explicit kv_eviction_manager(const kv_eviction_config & config);
    ~kv_eviction_manager();

    // === Block 注册 ===
    void register_block(int32_t token_pos, int32_t layer,
                        void * ram_addr, size_t size);

    // === Attention 分数更新 ===
    void update_attention_scores(int32_t layer,
                                 const std::vector<double> & scores);

    // === 驱逐与预取 ===
    int run_eviction();  // 返回驱逐的 block 数
    int prefetch_cold_blocks(int32_t current_layer, int32_t lookahead);

    // === 统计 ===
    size_t total_ram_usage() const;
    size_t total_ssd_usage() const;
    int    total_evictions() const;
    int    total_prefetches() const;
};
```

## 关键方法

### `register_block`
注册一个 KV block 的位置和大小，初始化 `is_hot`（pos < sink_tokens）或 `is_warm`。

### `run_eviction`
当 `ram_usage > budget_bytes` 时，按 attention 分数升序驱逐非 hot block：
1. 收集所有 `!is_hot && !is_cold` 的 block
2. 按 `avg_attn_score` 升序排序
3. 对超出窗口或低分 block 调用 `evict_block()`

### `evict_block`
- 若 `enable_offload`：`memcpy` 到 mmap 文件，记录 `offload_offset`
- 标记 `is_cold=true`，更新 `ram_usage -= size`

### `prefetch_cold_blocks`
对 `[current_layer, current_layer + lookahead]` 范围的 cold block，若 attention 分数高于阈值，发 `madvise(WILLNEED)` 提示内核预读。

## 当前集成状态

接口已完整实现，但与推理流程的深度集成（hook KV cache allocation/access 路径）**尚未完成**。当前实际使用的是 `llama-context.cpp` 中的简化版 eviction（直接调用 `memory->seq_rm`），详见环境变量 `SLIM_ARC_KV_EVICT`。

## 简化版 eviction（已集成）

在 `llama-context.cpp` 的 `graph_compute` 末尾：
```cpp
if (getenv("SLIM_ARC_KV_EVICT")) {
    int sink = getenv("SLIM_ARC_KV_SINK") ? atoi(...) : 4;
    int window = getenv("SLIM_ARC_KV_WINDOW") ? atoi(...) : 1024;
    int seq_len = memory->seq_pos_max(0) + 1;
    if (seq_len > sink + window) {
        int p0 = max(last_evicted, sink);
        int p1 = seq_len - window;
        memory->seq_rm(0, p0, p1);  // 逻辑删除
    }
}
```

## 实验数据

- Qwen3-4B 32GB：eviction 开销 -2.9%，64 次驱逐，文本连贯
- 80B IQ4_XS 32GB：decode **+9.6%**（KV 内存释放给权重缓存）

详见 `reports/Competition_Report/sections/05_evaluation.tex`。
