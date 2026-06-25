# prefetch_scheduler API 文档

> 源码：`src/llama-upstream/src/slim-arc-prefetch.h` / `.cpp`

## 概述

`prefetch_scheduler` 是 SLIM-ARC 的核心运行时组件，负责：
1. 注册所有权重张量的 mmap 地址和层级信息
2. 在每次 `graph_compute` 时，对后续层发 `madvise(WILLNEED)` 异步预取
3. 通过 MoE Router Hook 提取激活专家 ID，选择性预取 3D 合并张量的子区域
4. 管理动态 MADV 切换（prefill↔decode）

## 类接口

```cpp
class prefetch_scheduler {
public:
    explicit prefetch_scheduler(int n_threads = 2, int window = 3);
    ~prefetch_scheduler();

    // === 张量注册 ===
    void register_tensor(const char * name, void * addr, size_t size, int layer);
    void register_expert_tensor(const char * name, void * addr, size_t total_size,
                                int layer, int n_experts);

    // === MoE Router 预测 ===
    void cache_router_experts(int layer, const int * expert_ids, int n_experts);
    const int * get_cached_experts(int layer, int * out_n) const;
    void prefetch_experts(int layer, const int * expert_ids, int n_experts);

    // === 运行时调度 ===
    void notify_layer_compute(int current_layer);
    void evict_layer(int layer);
    void set_phase(compute_phase phase);  // PREFILL / DECODE
    void set_memory_budget(size_t budget_bytes);
    void set_enabled(bool enabled);

    // === 统计 ===
    size_t total_prefetched_bytes() const;
    int    total_prefetch_calls() const;
    int    effective_window() const;
};
```

## 全局单例

```cpp
prefetch_scheduler * get_global_prefetch_scheduler();
void set_global_prefetch_scheduler(prefetch_scheduler * s);
```

在 `llama-model-loader.cpp` 的 `init_mappings` 末尾创建并设置：
```cpp
static slim_arc::prefetch_scheduler s_scheduler(2, 3);
slim_arc::set_global_prefetch_scheduler(&s_scheduler);
```

## 关键方法详解

### `register_expert_tensor`
注册 MoE 3D 合并张量，计算每专家偏移：
```
per_expert_size = total_size / n_experts
expert_addr(i) = base_addr + i * per_expert_size
```
后续 `prefetch_experts` 对指定 expert_id 的子区域发 `madvise(WILLNEED)`。

### `cache_router_experts` / `get_cached_experts`
缓存 layer N 的 Router 输出（top-k expert IDs），供 layer N+1 预测使用。
- **调用时机**：`graph_compute` 完成后，从 `ffn_moe_topk` 张量提取
- **参数**：`expert_ids` 数组，`n_experts` 长度
- **返回**：`get_cached_experts` 返回指针，`out_n` 输出长度；无缓存返回 nullptr

### `prefetch_experts`
对指定层级的专家子区域发 `madvise(WILLNEED)`：
```cpp
for each expert_id in expert_ids:
    addr = base + expert_id * per_expert_size
    posix_madvise(addr, per_expert_size, POSIX_MADV_WILLNEED)
```
仅预取激活的 10/512 专家，节省 98% I/O。

### `notify_layer_compute`
触发当前层 + 窗口内后续层的异步预取。内部用独立线程池避免阻塞计算。

### `set_phase`
- `PREFILL`：窗口=4（计算密集，I/O 可隐藏）
- `DECODE`：窗口=1（访存密集，精确预取）

## 辅助函数

### `tensor_layer_from_name`
```cpp
int tensor_layer_from_name(const char * name);
```
从张量名 `blk.{N}.ffn_*` 解析层级 N，非层张量返回 -1。

### `register_mmap_region` / `switch_madvise_all`
```cpp
void register_mmap_region(void * addr, size_t size);
void switch_madvise_all(int advice);  // 0=WILLNEED, 1=RANDOM, 2=DONTNEED
```
注册 mmap 区域供动态 MADV 切换。`switch_madvise_all` 对所有注册区域批量发 madvise。

## 调用流程（graph_compute 中）

```cpp
// llama-context.cpp graph_compute 开头
int min_layer, max_layer = extract_layer_range(graph);
if (auto * s = get_global_prefetch_scheduler()) {
    s->set_phase(batched ? PREFILL : DECODE);
    s->notify_layer_compute(min_layer);
    // 预取窗口内后续层
    for (int l = min_layer + s->effective_window() + 1; l <= max_layer; l++)
        s->notify_layer_compute(l);
    // 用上一层 router 输出预测当前层专家
    for (int l = min_layer; l <= max_layer; l++) {
        int nc; const int * ce = s->get_cached_experts(l - 1, &nc);
        if (ce) s->prefetch_experts(l, ce, nc);
    }
}
// ... ggml_backend_sched_graph_compute_async ...
// graph_compute 结尾：提取 ffn_moe_topk
if (auto * s = get_global_prefetch_scheduler()) {
    for each tensor t in graph:
        if (t->name contains "ffn_moe_topk"):
            s->cache_router_experts(layer, t->data, t->ne[0]);
            break;
}
```

## 实验验证

四组单点消融实验表明，在有 MADV_RANDOM 时 prefetch 无额外贡献（内核 page fault 已足够），在无 MADV_RANDOM 时等价 baseline。详见 `reports/Competition_Report/sections/05_evaluation.tex` 消融实验部分。
