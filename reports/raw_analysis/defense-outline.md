# SLIM-ARC 答辩提纲

## Slide 1: 项目概述

**SLIM-ARC**: Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization for On-Device Agents

- 2026 全国大学生系统能力大赛操作系统设计赛 Proj 59
- 中山大学 · 欧阳易芃、马福泉、刘昊 · 指导老师赵帅
- 赛题: 内存受限环境的大语言模型推理优化

**核心目标**: 让 45GB MoE 模型在 8-16GB RAM 下高效运行

## Slide 2: 问题背景

- 端侧设备内存有限（8-16GB），但 LLM 模型巨大（4B-80B 参数）
- Qwen3-Next-80B (45GB) 在 8GB 设备上**直接 OOM**（启用 repack 时）
- 现有工作各自为政:
  - FlexInfer 只调度权重
  - DUAL-BLADE 只调度 KV Cache  
  - MobileMoE 只调度专家

**核心 Insight**: 利用 MoE 稀疏性 + 内核虚拟内存机制，按需加载

## Slide 3: 核心技术方案

### mmap + MADV_RANDOM 按需加载

```
模型文件 (45GB) ──mmap──→ 虚拟地址空间 (45GB VSZ)
                              │
                    posix_madvise(MADV_RANDOM)
                              │
                    只有访问的页面进 RAM (8GB)
```

- `MADV_RANDOM`: 关闭内核顺序 readahead，按需分页
- MoE 稀疏性（98%）：未激活专家权重不进 RAM
- 禁用 `GGML_CPU_REPACK`: 避免 Q4_K 权重匿名内存翻倍

## Slide 4: 核心实验结果

### Qwen3-Next-80B (45GB) 在 8GB cgroup

**四组单点消融（pp16+tg4）**:

| 配置 | pp16 | tg4 | 说明 |
|------|------|-----|------|
| baseline | 0.63 | 0.08 | 全关 |
| MADV_RANDOM only | 0.27 | **0.29** | decode +262% |
| prefetch only | 0.54 | 0.07 | 等价 baseline |
| slim-arc (全开) | 0.28 | 0.29 | = MADV only |

**小负载（pp4+tg1）**: tg1 从 0.08 → 0.43 (**+437%**)

所有数据有原始日志可溯源: [`logs/ablation/raw-80b/`](../logs/ablation/raw-80b/)

## Slide 5: 关键技术发现

### MADV_RANDOM 是 decode 提升的核心驱动

四组消融证明:
- MADV_RANDOM only (0.29) == 全开 (0.29)
- prefetch_scheduler 无额外贡献

### 为什么 MADV_RANDOM 对 MoE 有效？

1. MoE 每token仅激活 10/512 专家（98% 稀疏）
2. MADV_RANDOM 阻止内核预读未激活专家权重
3. 内核 page fault 只加载实际访问的页面
4. 减少内存压力，避免 thrashing

### Tradeoff

- prefill -57%（MADV_RANDOM 阻止顺序预读）
- decode +262%（按需加载，内存压力小）
- 交互式场景（decode 为主）极其有利

## Slide 6: 系统架构

```
┌─────────────────────────────────────────────┐
│           SLIM-ARC 统一调度层                │
│  ┌─────────┐ ┌─────────┐ ┌──────────────┐  │
│  │权重卸载  │ │KV 换页   │ │MoE专家预取    │  │
│  │(mmap)   │ │(接口)   │ │(router hook) │  │
│  └────┬────┘ └────┬────┘ └──────┬───────┘  │
│       └──────┬──────────────────┘          │
│        ┌─────▼─────┐                       │
│        │统一I/O调度器│ ← 核心创新            │
│        └─────┬─────┘                       │
└──────────────┼────────────────────────────┘
               ▼
┌─────────────────────────────────────────────┐
│       mmap + madvise 内核协同层              │
│  (MADV_RANDOM · WILLNEED · DONTNEED)        │
└─────────────────────────────────────────────┘
```

## Slide 7: 模块完成度（诚实版）

| 模块 | 状态 | 说明 |
|------|------|------|
| mmap + MADV_RANDOM | ✅ 真集成 | decode +262% |
| 禁用 repack | ✅ | 无此则 OOM |
| prefetch_scheduler | ✅ 集成 | 80B 场景冗余（已验证） |
| Phase 2a router hook | ✅ 集成 | expert 选择性预取 |
| Phase 2b KV 换页 | ⚠️ 接口 only | 未集成推理流程 |
| Phase 2d Tile | ⚠️ 隐式 | 依赖 page cache |
| Phase 3 统一调度 | ✅ tick() 运行 | KV=nullptr |

## Slide 8: 可复现性

### 环境变量开关

```bash
SLIM_ARC_DISABLE=1          # 全关（baseline）
SLIM_ARC_NO_MADV_RANDOM=1   # 只关 MADV_RANDOM
SLIM_ARC_NO_PREFETCH=1      # 只关 prefetch
（默认）                      # 全开
```

### 一键复现

```bash
# 1. 设置 cgroups
sudo bash scripts/env/setup-cgroups.sh

# 2. 编译（禁用 repack）
cd src/llama-upstream/build
cmake -DGGML_CPU_REPACK=OFF ..
cmake --build . -j

# 3. 跑 80B 四组消融
bash scripts/bench/run-80b-bench.sh
```

原始日志: `logs/ablation/raw-80b/`

## Slide 9: 核心卖点

1. **80B 在 8GB decode +262~437%** — 四组消融可溯源
2. **MADV_RANDOM + MoE 稀疏性** — 机制被精确归因
3. **诚实的技术评估** — prefetch 冗余被承认
4. **可复现** — 环境变量 + 脚本 + 原始日志

## Slide 10: 后续工作

1. **Phase 2b KV 换页深度集成**: 让 prefetch 产生独立价值
2. **prefill/decode 动态切换**: 消除 prefill 57% 下降
3. **Q8_0 精度对比**: 验证精度损失可接受
4. **更大上下文测试**: 32K/128K context

## Slide 11: 总结

- **核心成果**: 45GB MoE 模型在 8GB decode 提升 262-437%
- **核心机制**: mmap + MADV_RANDOM 利用 MoE 稀疏性
- **诚实评估**: prefetch 冗余被四组消融证实
- **可复现**: 全部数据有原始日志，环境变量开关支持

**这不是"所有模块都有效"的完美故事，而是"MADV_RANDOM + MoE 稀疏性"的精确归因。**
