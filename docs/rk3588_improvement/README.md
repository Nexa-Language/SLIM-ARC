# RK3588 端侧 SLIM-ARC 改进专题

- 开始日期：2026-08-08
- 项目负责人：欧阳易芃
- 目标：解决 RK3588 端侧 80B 测试中 SLIM-ARC 负优化问题，使框架在真实端侧（ARM 弱算力 + 物理内存 + 快 SSD）体现价值
- 原则：**保留原框架与机制**，在其上做最小外科手术式改进；改一处测一处（消融式）；保持代码规范与镜像同步

---

## 1. 背景：为什么改进

2026-08-06/07 测试发现 RK3588 端侧（8GB 物理内存 + SSD 2.1GB/s + ARM 无 AVX2）上 SLIM-ARC 全开比禁用慢 4-6×（负优化）。根因分析（详见 [`RK3588-SLIMARC-80B性能分析.md`](../rk3588_test_notes/80B-长上下文测试归档/报告/RK3588-SLIMARC-80B性能分析.md)）：

| 根因 | 说明 |
|:---|:---|
| 静态 MADV_RANDOM | 加载时对整个 45GB 一次性设 RANDOM，关闭 prefill 顺序预读 |
| baseline 环境差异 | RK3588 物理内存+快SSD 使上游默认顺序预读高效，RANDOM 反而破坏 |
| ARM 算力瓶颈 | 无 AVX2，I/O 优化收益被计算瓶颈掩盖 |

## 2. 改进方案与结果

### 方案：动态 MADV 阶段切换（保留原机制，最小改动）

实现 `prefill/decode` 阶段的动态 MADV 建议切换，并针对 RK3588 极端内存比例（45GB/8GB）验证出最优策略：

| 阶段 | 建议 | 理由 |
|:---|:---|:---|
| prefill | `MADV_SEQUENTIAL` | 顺序访问，保留内核顺序预读，消除 prefill 负优化 |
| decode | `MADV_SEQUENTIAL`（默认） | 消融证明：45GB/8GB 下 RANDOM 反而拖慢 decode 5.4×，SEQUENTIAL 利用 SSD 顺序带宽 |

> `SLIM_ARC_DECODE_MADV=RANDOM/NORMAL` 可覆盖（供内存相对充足场景）；`SLIM_ARC_DYNAMIC_MADV=0` 可禁用动态切换。

### 测试结果（Qwen3-Next-80B Q4_K_M）

**短上下文（llama-bench -p 32 -n 16 -t 4）**
| 配置 | pp (t/s) | tg (t/s) |
|:---|:---:|:---:|
| 改进前全开（静态 RANDOM） | 0.44 | 0.26 |
| **改进后全开（动态 MADV）** | **2.84** | **1.40** |
| 禁用（上游最优） | 2.74 | 1.41 |

**长上下文（llama-bench -p 512 -n 128 -t 4）**
| 配置 | pp (t/s) | tg (t/s) |
|:---|:---:|:---:|
| 改进前全开 | 2.41 | 0.53 |
| **改进后全开** | **6.09** | **2.08** |
| 禁用 | 6.33 | 2.15 |

**结论**：SLIM-ARC 从 4-6× 负优化转为与禁用持平（差距 ~0-4%），prefill +545%、decode +438%。KV eviction 与动态 MADV 协同正常。

## 3. 代码修改清单（patches 与 src 镜像同步）

| 文件 | 修改 |
|:---|:---|
| [`slim-arc-prefetch.cpp`](../../patches/llama-upstream/slim-arc-prefetch.cpp) | `register_mmap_region` 初始设 SEQUENTIAL；新增 `apply_madvice_to_regions()`、`apply_dynamic_madv()`（阶段切换） |
| [`slim-arc-prefetch.h`](../../patches/llama-upstream/slim-arc-prefetch.h) | `set_phase()` 触发动态切换；`apply_dynamic_madv` 前置声明 |
| [`apply-slim-arc.py`](../../scripts/apply-slim-arc.py) | model-loader 去掉静态 RANDOM 改 dynamic（幂等清理旧块）；context unified 分支补 prefetch set_phase 调用；**阶段 5-7**：router hook 层号 `-<N>` 回退、层扫描回退、幂等标记改 `cache_router_experts`、**预测器 spatial→temporal**（`get_cached_experts(l)`）；**阶段 5 附带**：修复 patches_dir 硬编码相对路径导致镜像同步断裂 |
| [`slim-arc-prefetch.cpp`](../../patches/llama-upstream/slim-arc-prefetch.cpp) | **阶段 5**：`tensor_layer_from_name` 的 `-<N>` 回退、router 缓存逻辑（无 break 全层缓存）；**阶段 11-14**：命中率/浪费指标+dump、2-token 置信度门控、每 step 预算截断、热门专家并集（env 可配置） |
| [`slim-arc-unified-scheduler.cpp`](../../patches/llama-upstream/slim-arc-unified-scheduler.cpp) | **阶段 13**：`tick()` 在 `SLIM_ARC_EXPERT_BUDGET=1` 时下发专家预算并每 step 重置 |

## 4. 文档索引

| 文档 | 内容 |
|:---|:---|
| [`README.md`](README.md) | 本说明 |
| [`改进记录.md`](改进记录.md) | 分阶段改进过程与决策（含阶段 11-14 文献驱动改进） |
| [`测试数据.md`](测试数据.md) | 消融与性能数据明细（含阶段 11-14 命中率/预算数据） |
| [`任务清单-阶段11-14.md`](任务清单-阶段11-14.md) | 基于文献的 4 点改进任务清单 |
| [`moe_cpu_memory_limited_survey.pdf`](moe_cpu_memory_limited_survey.pdf) | 调查文献（改进思路来源） |

## 5. 环境变量速查（新增）

| 变量 | 默认 | 作用 |
|:---|:---|:---|
| `SLIM_ARC_DYNAMIC_MADV` | 启用 | 0 = 禁用动态切换（不设任何建议） |
| `SLIM_ARC_DECODE_MADV` | SEQUENTIAL | decode 阶段建议（SEQUENTIAL/RANDOM/NORMAL） |
| `SLIM_ARC_EXPERT_CONF` | 关闭 | 1 = 置信度门控专家预取（2-token 稳定专家，命中率 +24pp、字节 -56%，**推荐**） |
| `SLIM_ARC_EXPERT_BUDGET` | 关闭 | 1 = 专家预取纳入统一 I/O 预算（per-step 截断，非 I/O 受限时收益有限） |
| `SLIM_ARC_EXPERT_POP` | 0 | K = temporal ∪ top-K 热门专家（**实测负结果**，不建议开启） |
