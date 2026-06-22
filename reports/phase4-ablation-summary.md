# SLIM-ARC 消融实验报告

## 实验概述

**目标**: 验证 SLIM-ARC 优化系统（mmap + MADV_RANDOM + prefetch_scheduler）在三档受限环境下相对 baseline 的性能提升。

**环境**: WSL2-Ubuntu, Intel i9-13900H (32GB RAM), NVMe SSD, cgroups v2 隔离

**日期**: 2026-06-23

## 实验配置

### 三档环境
| Tier | 内存 | CPU | 模拟场景 |
|------|------|-----|---------|
| low  | 8GB  | 4核 | 端侧设备（Raspberry Pi 级） |
| mid  | 12GB | 6核 | 中端设备（手机/平板） |
| high | 16GB | 8核 | 高端设备（迷你主机） |

### 模型
| 模型 | 类型 | 大小 | 参数量 |
|------|------|------|--------|
| Qwen3-4B-Q4_K_M | Dense | 2.4GB | 4.02B |
| OLMoE-1B-7B-Q4_K_M | MoE | 3.9GB | 6.92B (64 experts, active 8) |
| Qwen3-Next-80B-A3B-Q4_K_M | MoE | 45GB | 80B (512 experts, active 10) |

### 对比模式
- **baseline**: `SLIM_ARC_DISABLE=1`（禁用所有 SLIM-ARC 优化，等价 upstream llama.cpp）
- **slim-arc**: 启用 MADV_RANDOM + prefetch_scheduler + phase 感知

### Benchmark 参数
- prompt: pp64（prefill 64 token）
- generate: tg16（decode 16 token）
- threads: 随 tier 变化（4/6/8）
- mmap: 开启（`-mmp 1`）
- repeats: 2

## 核心结果

### OLMoE-1B-7B（MoE 模型）— 主要成果

| Tier | Mode | pp64 (t/s) | tg16 (t/s) | pp 提升 | tg 提升 |
|------|------|-----------|----------|--------|--------|
| low (8G) | baseline | 59.26 | 26.34 | - | - |
| low (8G) | **slim-arc** | **96.75** | **40.32** | **+63.2%** | **+53.1%** |
| mid (12G) | baseline | 100.09 | 31.01 | - | - |
| mid (12G) | slim-arc | 91.25 | 26.88 | -8.8% | -13.3% |
| high (16G) | baseline | 136.85 | 38.25 | - | - |
| high (16G) | slim-arc | 135.63 | 38.99 | -0.9% | +1.9% |

### Qwen3-4B（Dense 模型）

| Tier | Mode | pp64 (t/s) | tg16 (t/s) | pp 提升 | tg 提升 |
|------|------|-----------|----------|--------|--------|
| low (8G) | baseline | 24.41 | 12.84 | - | - |
| low (8G) | **slim-arc** | **28.69** | **13.57** | **+17.5%** | **+5.7%** |
| mid (12G) | baseline | 35.31 | 11.94 | - | - |
| mid (12G) | slim-arc | 33.22 | 10.39 | -5.9% | -13.0% |
| high (16G) | baseline | 40.91 | 12.21 | - | - |
| high (16G) | slim-arc | 42.56 | 13.29 | +4.0% | +8.8% |

### Qwen3-Next-80B（超大 MoE 模型）

| Tier | Mode | 结果 |
|------|------|------|
| low (8G) | baseline | **OOM (killed)** |
| low (8G) | slim-arc | **能运行，不 OOM**（RSS=8.1GB, 36+ 分钟稳定） |

## 分析

### 1. 8GB 环境：最大提升

**OLMoE +63.2%（pp）/ +53.1%（tg）** 是最有价值的对比数据：
- MoE 模型在内存压力下，baseline 的内核 readahead 策略导致 page cache 频繁回收
- SLIM-ARC 的 MADV_RANDOM + 按需 WILLNEED 预取，只加载需要的层
- MoE 专家的稀疏性（8/64 激活）让 prefetch 更精准

### 2. 12GB 环境：异常下降

mid tier 出现性能下降（-8.8%/-13%），可能原因：
- 12GB cgroup 下模型（4GB）能基本全缓存，MADV_RANDOM 反而阻止了 readahead
- memory.peak 读取异常（显示 3073MB，应为 12GB）
- **改进方向**: MADV_RANDOM 的阈值应动态化（基于 model_size / cgroup_memory 比例）

### 3. 16GB 环境：持平

模型完全在 RAM，优化无额外收益，符合预期。

### 4. 80B 模型：从 OOM 到能跑

baseline 在 8GB 直接 OOM kill，SLIM-ARC 能启动并稳定运行。这是**最核心的卖点**：让不可能变为可能。

## 优化技术总结

### 已实现
1. **mmap + MADV_RANDOM**: 关闭内核 readahead，按需分页
2. **禁用 GGML_CPU_REPACK**: 避免 Q4_K 权重匿名内存翻倍
3. **prefetch_scheduler**: 层感知的 WILLNEED 异步预取
4. **phase 感知**: Prefill 大 window，Decode 小 window
5. **expert tensor 注册**: 3D 合并 expert tensor 的逐专家地址映射
6. **evict_layer API**: madvise(DONTNEED) 主动换出（待集成到 graph_compute）

### 设计完成（接口已实现，router hook 待集成）
7. **MoE 专家选择性预取**: `prefetch_experts(layer, expert_ids, n)` 接口
8. **统一 I/O 调度器**: `unified_io_scheduler` 原型，phase 感知的 budget 分配表

## 比赛价值

1. **"能跑 vs OOM"**: 80B 在 8GB 从 OOM 到可运行 — 最强卖点
2. **"高出一大截"**: OLMoE 8GB 环境 +63%/+53% — 量化对比数据
3. **系统级创新**: 统一 I/O 调度器架构（权重+KV+expert 协同）
4. **可复现**: 三档 cgroup 脚本 + CSV 数据 + SLIM_ARC_DISABLE 开关

## 数据文件

- CSV: [`logs/ablation/ablation-20260623-014809.csv`](../logs/ablation/ablation-20260623-014809.csv)
- 原始日志: [`logs/ablation/raw-20260623-014809/`](../logs/ablation/raw-20260623-014809/)
- Benchmark 脚本: [`scripts/bench/run-quick-ablation.sh`](../scripts/bench/run-quick-ablation.sh)
