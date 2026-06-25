# unified_io_scheduler API 文档

> 源码：`src/llama-upstream/src/slim-arc-unified-scheduler.h` / `.cpp`

## 概述

`unified_io_scheduler` 协调权重预取、KV Cache 换页、专家预取三路 I/O 竞争，根据运行时阶段动态分配带宽预算。

## 运行时阶段

```cpp
enum class runtime_phase {
    PREFILL_SHORT,   // 短 prompt prefill（<512 tokens）
    PREFILL_LONG,    // 长 prompt prefill（>=512 tokens）
    DECODE_SHORT,    // 短上下文 decode（<1024 tokens）
    DECODE_LONG,     // 长上下文 decode（>=1024 tokens）
    MOE_DECODE,      // MoE 模型 decode（专家预取主导）
};
```

## 带宽分配比例

| 阶段 | 权重 | KV Cache | 专家 |
|------|------|----------|------|
| PREFILL_SHORT | 60% | 10% | 30% |
| PREFILL_LONG  | 50% | 20% | 30% |
| DECODE_SHORT  | 70% | 20% | 10% |
| DECODE_LONG   | 30% | 60% | 10% |
| MOE_DECODE    | 40% | 10% | 50% |

设计依据：prefill 阶段顺序读取权重为主，KV 压力小；decode 阶段访存稀疏但 KV 随上下文增长；MoE decode 需要专家预测预取。

## 类接口

```cpp
class unified_io_scheduler {
public:
    unified_io_scheduler(size_t total_bandwidth,
                         prefetch_scheduler * prefetch,
                         kv_eviction_manager * kv);
    ~unified_io_scheduler();

    void set_phase(runtime_phase phase);
    void tick(int current_layer, int lookahead);

    // 带宽分配查询
    size_t weight_budget() const;
    size_t kv_budget() const;
    size_t expert_budget() const;
};
```

## 全局单例

```cpp
unified_io_scheduler * get_global_unified_scheduler();
void set_global_unified_scheduler(unified_io_scheduler * s);
```

## 调用流程

在 `llama-context.cpp` 的 `graph_compute` 中：
```cpp
if (auto * u = get_global_unified_scheduler()) {
    u->set_phase(batched ? PREFILL_SHORT : MOE_DECODE);
    u->tick(min_layer, 3);  // 预取后续 3 层
    // tick 内部调用 prefetch_scheduler 和 kv_eviction_manager
}
```

## 当前实现状态

接口完整，`tick()` 会调用 `prefetch_scheduler->notify_layer_compute()` 和 `kv_eviction_manager->run_eviction()`。但由于 prefetch 在当前场景冗余（MADV_RANDOM 已足够），且 KV eviction 深度集成未完成，统一调度器的"协同 > 单点之和"效果尚未验证。设计为决赛阶段的三路竞争场景预留。
