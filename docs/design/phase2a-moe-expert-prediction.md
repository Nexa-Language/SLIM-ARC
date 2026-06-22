# Phase 2a: MoE 专家选择性预取 - 设计分析与收益评估

## 1. 背景与动机

MoE（Mixture of Experts）模型是端侧推理的关键场景：Qwen3-Next-80B 有 512 专家，OLMoE-1B-7B 有 64 专家，但每 token 仅激活极少数（10/512 ≈ 2%，8/64 = 12.5%）。传统全量加载浪费 87-98% 带宽。

FlexInfer 论文只调度全量权重，未利用 MoE 稀疏性。SLIM-ARC 的核心创新之一是**专家级选择性预取**。

## 2. 模型架构分析

### OLMoE-1B-7B
- 16 层，每层 64 专家，激活 8 个/token
- 稀疏率：87.5%
- 专家权重组织：**3D 合并 tensor**
  - `blk.{l}.ffn_gate_exps.weight` [2048, 1024, 64] Q4_K
  - `blk.{l}.ffn_up_exps.weight`   [2048, 1024, 64] Q4_K
  - `blk.{l}.ffn_down_exps.weight` [1024, 2048, 64] Q4_K
- 每专家 ~3.9 MiB，每层 249 MiB

### Qwen3-Next-80B-A3B
- 48 层，每层 512 专家，激活 10 个/token
- 稀疏率：98%
- 每专家 1.8 MiB

## 3. 技术方案

### 3.1 挑战：合并 Tensor 的子区域预取

MoE 专家权重在 GGUF 中存储为 3D 合并 tensor（所有专家连续排列）。这意味着：
- 无法对单个专家独立 `mmap`（它们共享一个 tensor）
- 但可以利用 `madvise` 的**地址范围参数**，对 tensor 内的子区域发 `WILLNEED`

### 3.2 设计：层间 Router 预测预取

```
Layer N 计算:
  1. Router(f fn_gate_inp) 输出 → top-8 expert IDs [e1..e8]
  2. 用 expert IDs 计算下一层(N+1)的预测激活专家
  3. 对 layer N+1 的 ffn_*_exps.weight 中
     对应 [e1..e8] 的地址范围发 madvise(WILLNEED)
  4. Layer N+1 计算时，激活专家已预取到 page cache

预测策略:
  - 简单: 上一层 top-8 直接用于下一层（跨层相关性假设）
  - 进阶: 轻量 MLP predictor（上一层 router 输出 → 预测下一层）
```

### 3.3 地址映射

对于 `blk.{l}.ffn_gate_exps.weight` [2048, 1024, 64]：
- 单专家大小 = 2048 × 1024 × sizeof(Q4_K_block) / 64
- 专家 e 的地址范围 = tensor_base + e × per_expert_size, 长度 per_expert_size

## 4. 收益评估（理论分析）

### OLMoE-1B-7B (64 experts, active 8)

| 策略 | 每层预取带宽 | 带宽节省 |
|------|------------|---------|
| 全专家预取（当前） | 249 MiB | 0% |
| 选择性预取（top-8） | 31 MiB | **87.5%** |
| Oracle 预取（完美预测） | 31 MiB | 87.5% |

预测准确率对带宽节省的影响：
| 预测准确率 | 实际带宽 | 相对全预取节省 |
|-----------|---------|--------------|
| 100% (Oracle) | 31 MiB | 87.5% |
| 80% | 31 + 0.2×218 = 74.6 MiB | 70% |
| 60% | 31 + 0.4×218 = 118 MiB | 52.6% |
| 40% | 31 + 0.6×218 = 162 MiB | 34.9% |

即使预测准确率只有 40%，仍能节省 35% 带宽。

### Qwen3-Next-80B (512 experts, active 10)

| 策略 | 每层预取带宽 | 带宽节省 |
|------|------------|---------|
| 全专家预取 | 921 MiB | 0% |
| 选择性预取（top-10） | 18 MiB | **98%** |

## 5. 实现路线图

### 5.1 当前实现（已完成）
- `prefetch_scheduler` 对整个 expert tensor 发 `WILLNEED`（全专家预取）
- 在 8GB cgroup 下 OLMoE 已实现 pp +63.2%, tg +53.1% 的提升

### 5.2 短期实现（选择性预取）
1. 在 `graph_compute` 中 hook router 输出节点
2. 实现 `prefetch_expert_range(layer, expert_ids)` 接口
3. 层间传递 router 预测

### 5.3 进阶实现（统一调度器集成）
- Phase 3 统一调度器中，MoE 专家预取作为一路 I/O 需求
- 与权重预取、KV 换页竞争带宽预算

## 6. 对比 MobileMoE 论文

MobileMoE 用专家缓存 + 预测，但假设每个专家是独立 tensor。SLIM-ARC 的创新在于：
- 利用 `madvise` 地址范围参数，对合并 tensor 子区域预取
- 无需修改 GGUF 格式或拆分 tensor
- 与内核 page cache 协同，无需用户态缓存管理

## 7. 验证计划

1. 实现 router hook + expert range prefetch
2. 消融对比：全专家预取 vs 选择性预取 vs Oracle
3. 测量：带宽节省、吞吐提升、预测准确率

## 8. 结论

Phase 2a 的选择性专家预取在理论上可节省 87-98% 专家带宽。当前的全专家预取已在 8GB 环境实现显著提升（OLMoE +53-63%），选择性预取将进一步降低内存压力，让 45GB 模型在 8GB 下更快完成推理。
