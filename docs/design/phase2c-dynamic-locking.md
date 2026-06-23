# Phase 2c: Prefill/Decode 动态锁定策略

## 1. 背景

FlexInfer 的"均衡内存锁定"是静态的：FFN 和 Attention 权重的保留比例固定。但实际推理中：
- **Prefill 阶段**：计算密集，batch 大，I/O 可隐藏 → 少保留权重即可
- **Decode 阶段**：访存密集，batch=1，I/O 延迟关键 → 多保留权重减少 page fault
- **长上下文**：KV Cache 增长，需让渡 FFN 内存给 KV

SLIM-ARC 将静态锁定升级为运行时动态策略。

## 2. 设计方案

### 2.1 阶段检测器

```cpp
enum class compute_phase { PREFILL, DECODE, UNKNOWN };

// 在 graph_compute 中根据 batched 参数判断
void prefetch_scheduler::set_phase(compute_phase phase) {
    phase_.store(phase);
    effective_window_.store(compute_effective_window());
}
```

- `batched = true` → PREFILL（大 window，激进预取）
- `batched = false` → DECODE（小 window，精准预取）

### 2.2 动态 Window 策略

| 阶段 | Window | 策略 |
|------|--------|------|
| PREFILL | window+1 (默认4) | 计算可隐藏 I/O，多预取 |
| DECODE | 1 | 精准预取，避免内存浪费 |

### 2.3 cgroup 自适应

```cpp
// 在 init_mappings 中读取 cgroup memory.max
size_t cgroup_mem_limit = read_cgroup_memory_max();
bool model_fits_in_ram = total_weight < cgroup_mem * 60%;
// 模型能全缓存时跳过 prefetch（避免 madvise 开销）
```

### 2.4 MADV_RANDOM 的 prefill/decode tradeoff

通过三组对比实验（详见 [`reports/optimization-attribution-analysis.md`](../optimization-attribution-analysis.md)）发现：
- **MADV_RANDOM 对 decode 极有利**（+262% ~ +437%）
- **MADV_RANDOM 对 prefill 有害**（-56%）

提供环境变量切换：
- 默认：MADV_RANDOM 开启（优化 decode，交互式场景）
- `SLIM_ARC_NO_MADV_RANDOM=1`：关闭（优化 prefill，批量处理场景）

## 3. 实现状态

| 组件 | 状态 | 位置 |
|------|------|------|
| 阶段检测器 | ✅ | `prefetch_scheduler::set_phase` |
| 动态 window | ✅ | `compute_effective_window()` |
| cgroup 自适应 | ✅ | `init_mappings` 读取 memory.max |
| MADV_RANDOM 开关 | ✅ | `SLIM_ARC_NO_MADV_RANDOM` 环境变量 |
| 内存锁定(mlock) | ❌ 未实现 | upstream 已有 use_mlock 参数 |

## 4. 与原计划的差异

原计划"动态锁定"指 mlock（物理内存锁定防换出）。实际实现中：
- upstream llama.cpp 已有 `use_mlock` 参数，无需额外实现
- SLIM-ARC 的"动态"体现在 phase 感知的 prefetch window 和 cgroup 自适应
- mlock 在内存受限环境下反而有害（会强制保留内存），故未启用

## 5. 实验数据

Phase 2c 的效果体现在消融数据中（详见 [`reports/phase4-ablation-summary.md`](../phase4-ablation-summary.md)）：
- 80B 8GB decode +262% ~ +437%（MADV_RANDOM + phase 感知 prefetch）
- 小模型自动跳过（cgroup 自适应）

## 6. 结论

Phase 2c 的"动态锁定"被重新诠释为"phase 感知的 prefetch 策略 + cgroup 自适应"，已完整实现。相比静态锁定，能根据运行时阶段和内存压力动态调整，在受限环境下效果显著。
