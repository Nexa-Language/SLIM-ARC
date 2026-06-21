# 参考论文与源码

本目录存放 SLIM-ARC 项目参考的论文和开源代码。由于体积较大，PDF 和源码树不纳入 git，仅在此记录清单与来源。

## 核心论文

| 论文 | 角色 |
|------|------|
| FlexInfer: Breaking Memory Constraint via Flexible and Efficient Offloading for On-Device LLM Inference (EuroMLSys 2025) | **核心 baseline**，源码在 `FlexInfer/` 子目录 |
| On-Device Large Language Models: A Survey of Model Compression and System Optimization | 综述，技术方向参考 |

## KV Cache Offloading 方向

| 论文 | 关键贡献 |
|------|---------|
| DUAL-BLADE: Dual-Path NVMe-Direct KV-Cache Offloading for Edge LLM Inference | NVMe-direct 双路 KV 换页 |
| HillInfer: Efficient Long-Context LLM Inference on the Edge with Hierarchical KV Eviction using SmartSSD | 分层 KV 驱逐 |
| ScoutAttention: Efficient KV Cache Offloading via Layer-Ahead CPU Pre-computation for LLM Inference | 层前 CPU 预计算 |

## MoE 端侧推理方向

| 论文 | 关键贡献 |
|------|---------|
| MobileMoE: Scaling On-Device Mixture of Experts | 端侧 MoE 扩展 |
| MoE-Prism: Disentangling Monolithic Experts for Elastic MoE Services via Model-System Co-Designs | 专家解耦 |
| Accelerating Edge Inference for Distributed MoE Models with Latency-Optimized Expert Placement | 专家放置 |

## 端侧推理框架（竞品）

| 论文 | 关键贡献 |
|------|---------|
| PowerInfer-2: Fast Large Language Model Inference on a Smartphone | 手机端混合推理 |

## FlexInfer 源码

- **位置**: `FlexInfer/`（本地参考，不纳入 git）
- **来源**: https://github.com/FlexInfer/FlexInfer
- **协议**: MIT
- **用途**: 作为 SLIM-ARC 的基础框架，运行前需复制到 `src/flexinfer/`

## llama.cpp 源码

- **位置**: `llama.cpp/`（本地参考，不纳入 git）
- **来源**: https://github.com/ggml-org/llama.cpp
- **协议**: MIT
- **用途**: 标准 baseline，以及 backport Qwen3 架构定义的来源

## 优化方向调研

- [`flexinfer-optimize.md`](flexinfer-optimize.md): 基于 FlexInfer 和综述的优化方向分析
