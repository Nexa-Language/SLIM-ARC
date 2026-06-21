# SLIM-ARC 项目总体计划 v1

## 项目名称

**SLIM-ARC**: Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization for On-Device Agents

## 目标

在纯 CPU、三档受限环境（8G+4核 / 12G+6核 / 16G+8核）下，基于 FlexInfer 框架融合多项端侧推理优化技术（权重卸载、KV Cache 换页、MoE 专家预取、Tile 流水线等），实现统一 I/O 带宽预算调度器，使 Qwen3-4B（Dense）和 Qwen3-Next-A3B（MoE）在受限环境下的推理吞吐量、延迟、内存占用全面优于 FlexInfer baseline，并具备可演示性和可复现性，冲击全国大学生系统能力大赛操作系统设计赛决赛。

## 前置条件

1. WSL2-Ubuntu 环境（i9-13900H, 32GB RAM, RTX 4060 但不使用 GPU）
2. cgroups v2 可用（Ubuntu 22.04 默认满足）
3. GitHub 仓库 https://github.com/Nexa-Language/SLIM-ARC 推送权限
4. FlexInfer 源码已就位（`docs/papers/FlexInfer/`）
5. HuggingFace 模型可访问（需代理 `http://127.0.0.1:7897`）

## 核心 Insight

> **在统一 I/O 带宽预算下，权重卸载、KV 换页、MoE 专家预取三者竞争带宽，需基于运行时阶段（Prefill/Decode/长上下文）动态分配。**

FlexInfer 只调度权重，DUAL-BLADE 只调度 KV，MobileMoE 只调度专家。三者各自最优不等于全局最优，SLIM-ARC 的核心贡献是统一调度。

## 技术路线总览

```
┌─────────────────────────────────────────────────────────────┐
│                    SLIM-ARC 统一调度层                       │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐         │
│  │ 权重卸载  │  │ KV 换页    │  │ MoE 专家预测预取  │         │
│  │(FlexInfer)│  │(DUAL-BLADE)│  │  (MobileMoE)    │         │
│  └─────┬────┘  └─────┬─────┘  └────────┬────────┘         │
│        └──────────────┼──────────────────┘                  │
│               ┌───────▼───────┐                             │
│               │ 统一 I/O 调度器│ ← 核心创新点                 │
│               │ (带宽预算分配) │                             │
│               └───────┬───────┘                             │
│        ┌──────────────┼──────────────────┐                 │
│   ┌────▼────┐  ┌─────▼─────┐  ┌────────▼─────┐             │
│   │Tile流水线│  │动态锁定    │  │投机解码       │             │
│   │+融合反量化│ │(Prefill/   │  │(Draft-Verify) │             │
│   │         │  │ Decode)    │  │              │             │
│   └─────────┘  └───────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## 阶段拆解

### Phase 0: 环境搭建与基线复现

**目标**: 跑通三档环境，拿到 llama.cpp 和 FlexInfer 两个 baseline 的完整数据。

**步骤**:
1. 创建 cgroups v2 三档隔离配置脚本（`scripts/env/`）
2. 将 `docs/papers/FlexInfer/` 移入 `src/flexinfer/`
3. 下载 Qwen3-4B 和 Qwen3-Next-A3B 的 HF 模型，用 FlexInfer 自带 `convert-hf-models.sh` 转换为 4096 对齐 Q4_K_M GGUF
4. 验证 FlexInfer 对 Qwen3/Qwen3-Next 架构的支持；若不支持，从最新 llama.cpp backport 架构定义
5. 编译 FlexInfer host 二进制（`flexinfer-cli`, `flexinfer-bench`）
6. 跑通 llama.cpp 标准 baseline（三档 × 两模型 × 多 benchmark）
7. 跑通 FlexInfer 复现 baseline（同矩阵）
8. 搭建 benchmark 框架（`scripts/bench/`），统一管理 prompt 集、上下文长度、结果收集

**验收标准**:
- 三档环境下 FlexInfer 能正常推理 Qwen3-4B 和 Qwen3-Next-A3B
- baseline 数据表完整（tok/s, TTFT, TPOT, peak RSS, PPL）
- benchmark 一键运行脚本可用

**风险**:
- FlexInfer fork 版本旧，Qwen3-Next 架构可能不支持 → 需 backport
- GGUF 4096 对齐转换可能失败 → 需调试 convert 脚本

### Phase 1: 访存行为分析

**目标**: 用 profiling 工具量化权重/KV/专家激活的访存特征，为后续优化提供数据支撑。

**步骤**:
1. 集成 `perf` / `strace` / 自定义 profiler 到 FlexInfer
2. 分阶段 profiling：Prefill vs Decode
3. 分张量类型 profiling：Attention 权重、FFN 权重、KV Cache、MoE 专家
4. 不同上下文长度（512/4K/16K/32K）下的访存分布
5. 产出访存行为分析报告（`reports/phase1-memory-profile.md`）

**验收标准**:
- 能回答"在 16K 上下文 + 8G 内存下，权重 vs KV 谁是瓶颈？"
- 能回答"MoE 模型每 token 实际激活几个专家？带宽浪费多少？"

### Phase 2: 单点优化（P0 三方向并行）

每个方向遵循"复现论文思路 → 验证有效 → 记录消融"的闭环。

#### Phase 2a: MoE 专家预测预取

**参考论文**: MobileMoE、MoE-Prism、Distributed MoE Expert Placement

**思路**: 引入轻量级 Router Predictor，提前 1-2 层预测激活专家，仅预取所需权重。

**步骤**:
1. 在 Qwen3-Next-A3B 上分析 Router 决策的可预测性
2. 实现简易 Predictor（可用上一层 Router 输出 + 轻量 MLP）
3. 改造 FlexInfer 预取线程，按预测结果选择性加载
4. 消融：全专家预取 vs 预测预取 vs 理想预取（Oracle）

#### Phase 2b: KV Cache 异步换页

**参考论文**: DUAL-BLADE、HillInfer、ScoutAttention

**思路**: 将 FlexInfer 的权重卸载框架泛化到 KV Cache，基于注意力分数驱逐冷 KV block 到 SSD。

**步骤**:
1. 实现 KV Block 级别的注意力分数追踪
2. 设计冷热分级策略（基于 StreamingLLM 的 sink token + sliding window）
3. 实现异步换出/换入流水线（复用 FlexInfer 的 prefetch 线程池）
4. 消融：全内存 KV vs 全换出 vs 自适应换出

#### Phase 2c: Prefill/Decode 动态锁定

**参考论文**: FlexInfer Algorithm 1（升级）

**思路**: 将静态的 FFN/Attention 保留决策升级为运行时动态策略，按阶段切换。

**步骤**:
1. 实现阶段检测器（基于 batch size 和序列长度）
2. 设计 Prefill 模式（重算密集，少保留）vs Decode 模式（访存密集，多保留）的锁定策略
3. 长上下文模式下将 FFN 内存配额让渡给 KV Cache
4. 消融：静态锁定 vs 动态锁定

#### Phase 2d: Tile 级微流水线 + 融合反量化

**参考论文**: flexinfer-optimize.md（自主论证）

**思路**: 张量切分为 Tile，I/O 线程读 Tile-N 时计算线程处理 Tile-N-1；反量化与 MatMul 融合。

**步骤**:
1. 设计 Tile 切分策略（对齐 CPU L2/L3 Cache 行）
2. 改造 FlexInfer 预取流水线为 Tile 级
3. 实现融合反量化 kernel（参考 ggml-quants.c）
4. 消融：张量级 vs Tile 级，分离反量化 vs 融合反量化

### Phase 3: 统一 I/O 带宽预算调度器（核心创新）

**目标**: 将 Phase 2 的各单点优化统一到一个调度器下，解决带宽竞争。

**思路**:
- 运行时监控三路 I/O 需求：权重预取、KV 换入、MoE 专家预取
- 基于阶段（Prefill/Decode/长上下文）动态分配带宽预算
- 短上下文 Decode：权重优先（KV 小）
- 长上下文 Decode：KV 优先（权重可复用）
- MoE 模型：专家预取优先（稀疏性）

**步骤**:
1. 设计带宽预算分配算法（基于 Phase 1 的 profiling 数据建模）
2. 实现统一调度器（替换 FlexInfer 的 prefetch 线程管理）
3. 端到端集成测试
4. 与各单点优化对比，验证"协同 > 单点之和"

### Phase 4: 消融与组合实验

**目标**: 全矩阵测试，产出对比数据表。

**矩阵**:
- 3 档环境 × 2 模型 × {baseline, +2a, +2b, +2c, +2d, +2a+2b, 全组合, Phase3 统一} × 多 benchmark
- 量化精度对比：Q4_K_M vs Q8_0（验证精度损失可接受）

### Phase 5: 文档与展示（后期）

- 设计方案文档
- 对比分析报告
- 演示视频脚本
- 答辩 PPT

## Git 提交策略

不设固定里程碑，按日常开发节奏提交：
- 每完成一个子模块/修复/阶段即提交
- Conventional Commits + gitmoji
- 确保初赛阶段不少于 8 次提交，每次间隔 3-7 天
- 代码推送到 https://github.com/Nexa-Language/SLIM-ARC

## 验收标准（初赛）

1. 三档环境下 FlexInfer baseline 可复现，数据与论文量级吻合
2. 至少 2 个单点优化方向（P0）实现并验证正向收益
3. Phase 3 统一调度器实现，端到端优于任意单点优化
4. 完整的访存行为分析报告
5. 全矩阵消融实验数据
6. 设计方案文档 + 源码分析 + 进度汇报

## 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| FlexInfer 不支持 Qwen3-Next | 中 | 高 | 从最新 llama.cpp backport 架构定义 |
| GGUF 4096 对齐转换失败 | 低 | 中 | 调试 convert 脚本，或用 llama.cpp 转换后重对齐 |
| MoE 专家预测准确率低 | 中 | 中 | 退化为保守预取 + 延迟容忍 |
| KV 换页导致精度下降 | 中 | 高 | 限制换出范围到低注意力分数 block，加保护阈值 |
| Phase 3 统一调度器复杂度超预期 | 高 | 中 | 降级为启发式规则集，不做最优求解 |
| 工作量超预期 | 高 | 高 | P0 必做，P1 视进度，P2 选做 |

## ROADMAP 变更记录

- 2026-06-21: v1 初版，基于与用户两轮问答确定边界
