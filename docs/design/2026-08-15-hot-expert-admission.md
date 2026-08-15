# Hot-expert repeated-stability admission

## 问题

Pi 5 的 A36/A37 表明，替换策略可以改善 cache hit/eviction 计数，却仍然降低端到端 TPS。
`update_expert_hot_cache()` 对每个首次出现的稳定候选执行 page-plan、`mincore` resident 扫描和
`mlock`；短暂稳定一次的 expert 即使很快不再使用，也会进入 512 MiB 池并触发后续淘汰。

## 设计

增加 `SLIM_ARC_EXPERT_HOT_ADMIT_HITS=N`，取值为 `[1,64]`，默认 `1`：

- cache 低于 99% 占用时保持原有即时准入，用于建立初始热池；
- cache 达到 99% 占用后才启用过滤，不依赖 recurrent microbatch 的 phase 标记；
- 饱和阶段的计数键为 `(layer, expert_id)`，只在候选属于连续 token 稳定集合时递增；
- 候选达到第 `N` 次稳定观察前，不执行 page-plan、resident 扫描、`mlock` 或 LRU 淘汰；
- 已在 cache 中的条目仍按原路径计 hit 和刷新 LRU/LFRU 状态；
- 计数使用饱和 `uint32_t`，不会回绕；
- 无变量、非法变量或 `N=1` 时保持已有行为。

这是 near-capacity admission filter，不修改替换策略。A38 的全阶段阈值筛选使 prefill 明显退化；
A39 又证明 `batched` 无法在 Qwen3-Next recurrent microbatch 上可靠区分 prefill/decode。因此实现
收敛为占用率门控。Pi 后续比较 `N=1` 与 near-capacity `N=2`，保持 512 MiB LRU、
cold cache、no-swap、pp16/tg16 及其余环境完全一致。

## 指标与决策

`[SLIM-ARC-HOT]` 新增：

- `admission_skips`：尚未达到阈值而跳过的首次候选数；
- `admission_threshold`：本次运行解析后的阈值。

只有 wall time 和 TPS 改善才允许推广。admission、eviction 或扫描字节下降但端到端退化时，
保留默认 `N=1`。该机制不主动 fault-in 冷页，也不增加模型或镜像副本。
