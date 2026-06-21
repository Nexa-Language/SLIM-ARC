# SLIM-ARC: Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization for On-Device Agents

> 2026 全国大学生系统能力大赛操作系统设计赛 Proj 59 参赛项目
>
> 中山大学 · 欧阳易芃、马福泉、刘昊 · 指导老师：赵帅

## 项目简介

SLIM-ARC 是一个面向端侧设备的 LLM 推理优化框架，在受限内存环境下通过操作系统级虚拟内存技术（按需加载、数据换出、预取）实现大语言模型的高效推理。

**赛题**: [内存受限环境的大语言模型推理优化问题](docs/official/赛题.txt)（Proj 59，南开大学宫晓利老师维护）

**核心思路**: 基于 [FlexInfer](docs/papers/FlexInfer/) (EuroMLSys 2025) 的权重卸载框架，融合 KV Cache 异步换页、MoE 专家预测预取、Tile 级微流水线等技术，构建统一 I/O 带宽预算调度器，实现"协同 > 单点之和"的性能提升。

## 核心 Insight

> **在统一 I/O 带宽预算下，权重卸载、KV 换页、MoE 专家预取三者竞争带宽，需基于运行时阶段（Prefill/Decode/长上下文）动态分配。**

现有工作各自为政：
- [FlexInfer](docs/papers/FlexInfer%20Breaking%20Memory%20Constraint...pdf) 只调度模型权重
- [DUAL-BLADE](docs/papers/DUAL-BLADE%20Dual-Path%20NVMe-Direct%20KV-Cache%20Offloading...pdf) 只调度 KV Cache
- [MobileMoE](docs/papers/MobileMoE%20Scaling%20On-Device%20Mixture%20of%20Experts.pdf) 只调度 MoE 专家

SLIM-ARC 的核心贡献是**统一调度**这三类 I/O 需求。

## 系统架构

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

详见 [架构设计文档](docs/design/architecture.md)。

## 环境配置

### 受限环境（三档）

| 档位 | 内存 | CPU 核数 | 模拟场景 |
|------|------|---------|---------|
| Low | 8 GB | 4 核 | 中端手机/嵌入式 |
| Mid | 12 GB | 6 核 | 高端手机/轻量 PC |
| High | 16 GB | 8 核 | 现代 PC/端侧服务器 |

使用 cgroups v2 隔离，详见 [环境配置指南](docs/guide/environment.md)。

### 模型

| 类型 | 模型 | 量化 | 权重大小 |
|------|------|------|---------|
| Dense | Qwen3-4B | Q4_K_M | ~2.5 GB |
| MoE | Qwen3-Next-A3B | Q4_K_M | ~1.8 GB（3B 总参/稀疏激活） |

## 快速开始

```bash
# 1. 搭建受限环境
sudo bash scripts/env/setup-cgroups.sh

# 2. 构建 FlexInfer
cd src/flexinfer && bash build-host.sh

# 3. 转换模型（需 4096 对齐）
bash scripts/convert-models.sh

# 4. 运行 baseline
bash scripts/bench/run-baseline.sh

# 5. 运行 SLIM-ARC 优化版
bash scripts/bench/run-slim-arc.sh
```

## 项目结构

```
SLIM-ARC/
├── AGENT.md              # AI 协作规则
├── ROADMAP.md             # 项目进展日志（倒序）
├── README.md              # 本文件
├── plan/                  # 阶段计划文件
│   └── 00-v1-slim-arc-overview.md
├── docs/                  # 文档
│   ├── official/          # 比赛官方资料
│   ├── papers/            # 参考论文与源码
│   ├── others/            # 自主材料
│   ├── design/            # 设计文档
│   │   └── architecture.md
│   └── guide/             # 使用指南
│       └── environment.md
├── src/                   # 源代码
│   └── flexinfer/         # FlexInfer fork（待移入）
├── scripts/               # 脚本
├── config/                # 配置文件
├── data/                   # 数据与模型
├── logs/                   # 运行日志
├── reports/               # 实验报告
└── tests/                  # 测试
```

## 优化方向

| 优先级 | 方向 | 参考论文 | 状态 |
|--------|------|---------|------|
| P0 | KV Cache 异步换页 | DUAL-BLADE, ScoutAttention, HillInfer | 计划中 |
| P0 | MoE 专家预测预取 | MobileMoE, MoE-Prism | 计划中 |
| P0 | Prefill/Decode 动态锁定 | FlexInfer Algorithm 1 升级 | 计划中 |
| P1 | Tile 级微流水线 + 融合反量化 | flexinfer-optimize.md | 计划中 |
| P1 | 统一 I/O 带宽预算调度器 | SLIM-ARC 原创 | 计划中 |
| P2 | 投机解码适配 | PowerInfer-2 | 选做 |
| P2 | 编译级算子融合 | — | 选做 |

## 评估指标

- **吞吐量**: tok/s（Prefill + Decode 分开统计）
- **延迟**: TTFT（首 token 延迟）、TPOT（每 token 延迟）
- **内存**: 峰值物理内存（RSS）
- **精度**: PPL（Wikitext-103）
- **Benchmark**: Wikitext-103, HellaSwag, C4, 长上下文（16K/32K）

## 相关论文

1. FlexInfer: Breaking Memory Constraint via Flexible and Efficient Offloading for On-Device LLM Inference (EuroMLSys 2025) — **核心 baseline**
2. DUAL-BLADE: Dual-Path NVMe-Direct KV-Cache Offloading for Edge LLM Inference
3. HillInfer: Efficient Long-Context LLM Inference on the Edge with Hierarchical KV Eviction using SmartSSD
4. ScoutAttention: Efficient KV Cache Offloading via Layer-Ahead CPU Pre-computation for LLM Inference
5. MobileMoE: Scaling On-Device Mixture of Experts
6. MoE-Prism: Disentangling Monolithic Experts for Elastic MoE Services via Model-System Co-Designs
7. PowerInfer-2: Fast Large Language Model Inference on a Smartphone
8. On-Device Large Language Models: A Survey of Model Compression and System Optimization

## 开源协议

- 源代码: Apache License 2.0
- 文档: CC-BY-SA 4.0（比赛要求）
- 第三方代码: FlexInfer (MIT)、llama.cpp (MIT)，已在对应目录标注来源
