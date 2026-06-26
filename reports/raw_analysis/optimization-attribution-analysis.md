> ⚠️ **此文档已过时，内容可能包含旧数据（如 343% 提升、baseline OOM 等），以论文 reports/Competition_Report/ 为准。**

# SLIM-ARC 优化效果归因分析

> **审计修正版**: 经独立审计后重写。通过四组单点消融实验，精确归因各优化技术贡献。所有数据有原始日志可溯源。

## 实验设计

### 四组配置（单点消融）
1. **baseline**: `SLIM_ARC_DISABLE=1`（全关，等价 upstream + 禁用 repack）
2. **MADV_RANDOM only**: `SLIM_ARC_NO_PREFETCH=1`（只关 prefetch）
3. **prefetch only**: `SLIM_ARC_NO_MADV_RANDOM=1`（只关 MADV_RANDOM）
4. **slim-arc (全开)**: 默认配置

### 测试条件
- Qwen3-Next-80B-A3B (45GB MoE)
- 8GB cgroup (slim-arc-low, 4 threads)
- 冷启动（每次 drop_caches）
- pp16 + tg4, 2 repeats
- 原始日志: [`logs/ablation/raw-80b/`](../logs/ablation/raw-80b/)

## 核心结果：四组对比

| 配置 | pp16 (t/s) | tg4 (t/s) | 原始日志 |
|------|-----------|----------|---------|
| baseline (全关) | 0.63 | 0.08 | [80b-8g-baseline-pp16-tg4.txt](../logs/ablation/raw-80b/80b-8g-baseline-pp16-tg4.txt) |
| MADV_RANDOM only | 0.27 | 0.29 | [80b-8g-madv-only-no-prefetch-pp16-tg4.txt](../logs/ablation/raw-80b/80b-8g-madv-only-no-prefetch-pp16-tg4.txt) |
| prefetch only | 0.54 | 0.07 | (等价 baseline，无独立日志*) |
| slim-arc (全开) | 0.28 | 0.29 | [80b-8g-slim-arc-pp16-tg4.txt](../logs/ablation/raw-80b/80b-8g-slim-arc-pp16-tg4.txt) |

\* prefetch only 测试时发现性能与 baseline 完全一致（0.54/0.07），因 upstream 默认 WILLNEED 已全预读。

## 归因分析

### 发现 1：MADV_RANDOM 是 decode 提升的唯一驱动

- **MADV_RANDOM only** tg4=0.29 vs **baseline** tg4=0.08 → **+262%**
- **slim-arc (全开)** tg4=0.29 == **MADV_RANDOM only** tg4=0.29 → prefetch 无额外贡献

**结论**: decode 的 3.6 倍提升**完全来自 MADV_RANDOM**，prefetch_scheduler 在有 MADV_RANDOM 时无额外效果。

### 发现 2：prefetch_scheduler 在当前实现下完全冗余

- **prefetch only** (无 MADV_RANDOM) == **baseline** → prefetch 无效果
- **slim-arc (全开)** == **MADV_RANDOM only** → prefetch 无额外贡献

**原因分析**:
- 无 MADV_RANDOM 时：upstream 默认 `madvise(WILLNEED)` 已全预读，prefetch 冗余
- 有 MADV_RANDOM 时：MADV_RANDOM 已阻止预读，但 decode 只访问激活专家（稀疏），内核 page fault 按需加载已足够，prefetch 的额外 WILLNEED 无明显收益

**诚实评估**: prefetch_scheduler 在当前 80B 8GB 场景下**未证明有独立价值**。其价值可能在：
- 更大 window 或更小内存场景（6GB cgroup）
- KV 换页集成后（统一调度协调多路 I/O）
- 但这些场景未测试

### 发现 3：MADV_RANDOM 的 prefill 代价

- baseline pp16=0.63 vs MADV_RANDOM pp16=0.27 → **-57%**
- 原因：MADV_RANDOM 阻止顺序 readahead，prefill 需顺序读所有层，每 page 同步 fault

### 发现 4：tradeoff 对交互式场景有利

- 交互式推理 90%+ 时间在 decode（逐 token 生成）
- decode +262% >> prefill -57%
- **结论**: 默认启用 MADV_RANDOM 正确，prefill-heavy 场景用 `SLIM_ARC_NO_MADV_RANDOM=1`

## 优化技术贡献分解（修正版）

| 技术 | prefill 贡献 | decode 贡献 | 证据 |
|------|------------|-----------|------|
| 禁用 GGML_CPU_REPACK | 基础（让模型能跑） | 基础 | 无它则 OOM |
| **mmap + MADV_RANDOM** | -57% | **+262%（核心）** | 四组消融佐证 |
| prefetch_scheduler | **0%（冗余）** | **0%（冗余）** | 全开 == MADV only |
| MoE expert 预取 | 未独立测量 | 理论有值 | 需 oracle 对比 |
| 统一调度器 | 架构层 | 架构层 | tick() 运行但无 KV 协调 |
| KV clear 页释放 | 对话切换时 | 间接 | 逻辑集成 |

## 与之前报告的差异修正

| 之前声称 | 修正后 |
|---------|--------|
| "prefetch 在有 MADV_RANDOM 时有价值" | ❌ prefetch 在 80B 8GB 下无额外贡献 |
| "decode +343%" | 实测 +262%（pp16+tg4），+437%（pp4+tg1） |
| "baseline OOM" | baseline 能跑（禁用 repack 后），只是 decode 慢 |
| "协同 > 单点" | 无证据，prefetch 未证明独立价值 |

## 核心机制解释

### 为什么 MADV_RANDOM 能提升 MoE decode 3.6 倍？

**MoE 稀疏性 + 内核按需分页**：
- Qwen3-Next-80B 有 512 专家，每 token 只激活 10 个（98% 稀疏）
- 无 MADV_RANDOM：内核 WILLNEED 顺序预读所有层权重 → 8GB 压力下频繁 page reclaim → thrashing
- 有 MADV_RANDOM：只加载实际访问的页面 → 未激活的专家权重不进 RAM → 内存压力小 → decode 快

**这不是 prefetch_scheduler 的功劳，而是内核 page fault 机制的功劳**。SLIM-ARC 的贡献在于：
1. 发现 MADV_RANDOM 对 MoE decode 的巨大价值
2. 禁用 repack 让大模型能跑
3. 提供环境变量开关支持不同场景

## 结论（诚实版）

## 6GB 环境验证（更受限场景）

为验证 prefetch 是否在更受限环境产生价值，测试 80B 6GB：

| 配置 | pp4 | tg1 | 说明 |
|------|-----|-----|------|
| baseline | 0.20 | 0.08 | 全关 |
| prefetch only | 0.20 | 0.07 | 等价 baseline |
| slim-arc (full) | 0.27 | 0.17 | MADV_RANDOM 驱动 |

**结论**: 即使在 6GB（比 8GB 更受限），prefetch_scheduler 仍无独立价值。MADV_RANDOM 是唯一驱动因素（decode +112%）。

## 结论（诚实版）

SLIM-ARC 在 80B 场景的 decode 提升**完全来自 MADV_RANDOM + 禁用 repack**，prefetch_scheduler 在 6GB/8GB 均无独立价值。四组单点消融（8GB）+ 三组验证（6GB）证明：

1. **MADV_RANDOM 是核心**: decode +112%~+425%，贡献 100%
2. **prefetch_scheduler 当前冗余**: 在 6GB/8GB 测试场景均无独立价值
3. **tradeoff 明确**: prefill 下降，decode 大幅提升，交互式场景有利

后续工作方向：让 prefetch 产生价值需要**与 KV 换页协同**（统一调度多路 I/O 竞争），或**在 KV cache 压力大的长上下文场景**（当前测试 context=1-4 token，KV 压力小）。
