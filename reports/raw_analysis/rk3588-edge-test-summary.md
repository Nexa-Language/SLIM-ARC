# SLIM-ARC 端侧（RK3588）测试数据整理

> **透明声明**: 本报告整理自 haoma 分支新增的 RK3588 端侧测试（2026-08-05 ~ 2026-08-10）。所有数据均可溯源到 [`docs/rk3588_test_notes/`](../docs/rk3588_test_notes/) 与 [`docs/rk3588_improvement/`](../docs/rk3588_improvement/) 的原始日志。测量存在波动，报告呈现全部数据而非挑选；负结果（负优化、中性结果、失败项）均如实记录。

## 实验概述

- **目标**: 在真实端侧设备（RK3588 / Orange Pi 5 Plus，8GB 物理内存，ARM 无 AVX2）上验证 SLIM-ARC 的运行可行性、性能与优化价值，并修复端侧暴露的问题。
- **环境演进**: 存储从 microSD（~68.6MB/s）→ SSD（读 2.1GB/s），解锁 80B 端侧上机；这是端侧测试的关键转折。
- **方法**: llama-bench / llama-cli 实测 + LD_PRELOAD 拦截 madvise 验证 + strace + vmstat + RSS 峰值监控；消融式开发（改一处 → 测一处）。

## 环境快照

| 项 | 值 |
|:---|:---|
| 设备 | Orange Pi 5 Plus（RK3588），8GB RAM，8 核 = 4×A76(2.4GHz) + 4×A55(1.8GHz) |
| CPU 特性 | aarch64；无 AVX2 / 无 SVE / 无 i8mm；有 DOTPROD / FMA / FP16 |
| 系统 | Orange Pi 1.2.0 Jammy（Ubuntu 22.04.5 LTS），内核 5.10.160-rockchip |
| 存储 | 08-05: microSD 29.7GiB（裸读 68.6MB/s）；08-06 起: SSD 234GiB（读 2.1GB/s） |
| Swap | 3.9GiB（zram0） |
| 内存限制 | cgroup v2 内核支持，但**无 root 无法创建子 cgroup 限内存** → 无法做三档，采用原生 8GB |
| 工具链 | llama.cpp master `360e134` + SLIM-ARC 补丁；cmake 3.22 / gcc 11.4 / python 3.10 |

---

## 一、08-05 小模型测试（microSD）—— 编译修复 + 端侧基线

### 1.1 补丁编译修复（里程碑）

3 次构建后 EXIT=0，修复 2 类 bug（均为最小外科手术，未动机制）：
1. `llama-context.cpp`：缺 `<climits>` 致 `INT_MAX` 级联错误（吞掉 `max_layer` 声明）+ patches 中 `slim-arc-prefetch.*` 旧版缺 `compute_phase` 枚举及 `set_phase`/`effective_window`/`get_cached_experts`/`prefetch_experts` 等接口
2. `llama-model-loader.cpp`：`apply-slim-arc.py` prefetch_block 末尾重复大括号

### 1.2 Qwen3-4B llama-bench（`-t 4`，2.32GiB）—— 带 ± 统计

| 配置 | pp (t/s) | tg (t/s) | 原始日志 |
|:---|:---:|:---:|:---|
| 基线 `-p64 -n32`（f16 KV, FA auto） | 8.57 ± 0.01 | 6.90 ± 0.13 | `raw-bench-p64n32.txt` |
| 基线 `-p128 -n64` | 8.50 ± 0.02 | 5.14 ± 0.51 | `raw-bench-p128n64.txt` |
| KV q4_0 `-p64 -n32` | 8.31 ± 0.10 | 5.05 ± 0.29 | `raw-bench-kvq4.txt` |
| KV q4_0 `-p128 -n64` | 7.82 ± 0.04 | 3.79 ± 0.16 | `raw-bench-kvq4.txt` |
| FA off `-p64 -n32` | 7.63 ± 0.04 | 3.49 ± 0.69 | `raw-bench-faoff.txt` |
| FA off `-p128 -n64` | 7.57 ± 0.01 | 2.66 ± 0.31 | `raw-bench-faoff.txt` |

**发现**: FlashAttention 在 ARM 端侧 decode 约 **2×** 提升（tg32 3.49→6.90）；**KV q4_0 在 ARM 上 decode 反而略慢**（6.90→5.05，无 i8mm/SVE 反量化开销>省带宽收益）。

### 1.3 Qwen3-4B 基础推理（llama-cli）冷/热/上下文伸缩

| 运行 | Prompt (t/s) | Generation (t/s) | RSS 峰值 |
|:---|:---:|:---:|:---:|
| 冷 `-c1024` | 8.2 | 7.1 | ~2.65GB |
| 热 `-c1024`（紧随） | 8.2 | 6.9 | ~2.65GB |
| `-c512` | 8.2 | 5.7 | ~2.58GB |

冷/热差异极小（模型已在 page cache）；8GB 下无内存压力。

### 1.4 SLIM-ARC 负面验证（4B<6GB，MADV 本不触发）—— 全 EXIT=0

| 开关 | 结果 |
|:---|:---|
| 默认 | 生成正常 7.2 t/s |
| `SLIM_ARC_DISABLE=1` | 生成正常 7.1 t/s |
| `SLIM_ARC_NO_MADV_RANDOM=1` | 无异常（4B 本不触发） |
| `SLIM_ARC_KV_EVICT=1`（c=4096, n=1024） | ENABLED，seq_len>1028 逐 token 驱逐，不崩溃 |
| Dense 无 `_exps` | MoE 调用链空安全 |

### 1.5 OLMoE-1B-7B（MoE，4.21GiB）—— expert 预取链路端侧首验

| 指标 | 值 |
|:---|:---|
| Prompt | 4.3 t/s |
| Generation | 10.7 t/s |
| RSS 峰值 | ~4.2GB |
| expert 调用链 | `register_expert_tensor`/`prefetch_experts`/`cache_router_experts`/`get_cached_experts` 全部正常返回 |

> **80B 判定**: 08-05 因 microSD 仅 17GiB 剩余、装不下 40GB 判定不可行；08-06 SSD 就位后实测可运行（见下节）。

---

## 二、08-06 80B 端侧上机（SSD）—— 首次在 ARM 端侧跑通 80B

### 2.1 llama-bench 矩阵（Qwen3-Next-80B Q4_K_M 45.08GiB，r1, no-warmup）

| 编号 | 配置 | pp (t/s) | tg (t/s) | 说明 |
|:---|:---|:---:|:---:|:---|
| B1 | 全开 p32/n16/t4 | 0.39 | 0.23 | 默认 SLIM-ARC |
| B2 | `SLIM_ARC_DISABLE` p32/n16/t4 | 2.02 | 0.89 | 上游默认 |
| B3 | `NO_MADV_RANDOM` p32/n16/t4 | 1.41 | 0.65 | 关 MADV |
| B4 | `NO_PREFETCH` p32/n16/t4 | 0.37 | 0.24 | 关预取 |
| B5 | 全开 p64/n32/t4 | 0.55 | 0.30 | 长一点 |
| B6 | 全开 p32/n16/**t8** | 0.89 | 0.48 | 线程8 |
| B7 | 全开 p32/n16/**t2** | 0.23 | 0.17 | 线程2 |

**消融分析（全数据）**：
- 全开 vs DISABLE：pp **-80%**（0.39 vs 2.02）、tg **-74%**（0.23 vs 0.89）→ **负优化（4-6×）**
- `MADV_RANDOM` 为主要开销：B3（禁 MADV）1.41/0.65 显著快于 B1 全开 0.39/0.23
- 预取影响小：B4（禁预取）0.37/0.24 ≈ B1
- 线程扩展：t8 > t4 > t2

### 2.2 冒烟（smoke，llama-cli -p "Hello..." -n 16 -c 256）

| 配置 | Prompt | Gen | RSS峰值 | EXIT |
|:---|:---:|:---:|:---:|:---:|
| 默认全开 | 0.5 | 0.5 | 6.29GiB | 0 |
| `SLIM_ARC_DISABLE` | 1.7 | 1.9 | 6.26GiB | 0 |
| `NO_MADV_RANDOM` | 1.4 | 1.8 | 6.50GiB | 0 |

**关键证据**: 80B 在 8GB 端侧**可运行不 OOM**；mmap 虚拟 46.6GiB，驻留内存仅 ~6.3GiB（按需分页生效证据）。

### 2.3 madvise 系统调用验证（LD_PRELOAD 拦截）—— 核心创新端侧首次确认

| 配置 | 拦截到的 madvise |
|:---|:---|
| 默认 | `MADV_RANDOM(45.1GiB)` ×1（SLIM-ARC 按需分页触发!）、`WILLNEED(45.1GiB)` ×1（初始预取）、`DONTNEED(6MiB)` ×3（KV 释放） |
| `NO_MADV_RANDOM` | RANDOM 调用消失，WILLNEED 保留 → 开关有效 |

**TTFT**: 121.1s（含模型加载 ~60s），RSS 峰值 6.38GiB。**80B 触发 MADV_RANDOM 首次在端侧确认**（此前 Pi5 4GB 上因 <6GB 模型从未触发）。

---

## 三、08-07 长上下文测试（SSD）—— 45GB/8GB 极端比例

### 3.1 llama-bench（-p512, r1, no-warmup）

| 编号 | -c等效 | -n | -t | 开关 | pp | tg |
|:---|:---:|:---:|:---:|:---|:---:|:---:|
| LC1 | 1024 | 64 | 4 | 默认 | 2.43 | 0.43 |
| LC2 | 1024 | 64 | 4 | DISABLE | 6.35 | 1.96 |
| LC3 | 1024 | 64 | 4 | NO_MADV | 6.33 | 1.97 |
| LC5 | 4096 | 128 | 4 | 默认 | 2.41 | 0.53 |
| LC6 | 4096 | 128 | 4 | DISABLE | 6.35 | 2.13 |
| LC9 | 4096 | 128 | 8 | 默认 | 3.89 | 0.90 |
| LC10 | 4096 | 128 | 8 | DISABLE | 6.72 | 1.37 |
| LC14 | 8192 | 128 | 4 | 默认 | 2.44 | 0.53 |
| LC15 | 8192 | 128 | 4 | DISABLE | 6.34 | 2.15 |
| LC17 | 8192 | 256 | 4 | 默认 | 2.43 | 0.57 |
| LC21 | 16384 | 128 | 4 | 默认 | 2.36 | 0.53 |
| LC22 | 16384 | 128 | 4 | DISABLE | 5.54 | 1.64 |

> 本阶段仍是**静态 MADV_RANDOM**，负优化显著（默认 tg 0.43-0.57 vs DISABLE 1.96-2.15）。

### 3.2 cli 端到端

| 编号 | -c | -n | 开关 | Prompt | Gen | RSS(GiB) |
|:---|:---:|:---:|:---|:---:|:---:|:---:|
| LC11 | 4096 | 128 | 默认 | 0.4 | 0.4 | - |
| LC12 | 4096 | 128 | DISABLE | 2.3 | 2.0 | - |
| LC19 | 8192 | 256 | 默认 | 0.5 | 0.5 | 6.50 |
| LC20 | 8192 | 256 | DISABLE | 2.1 | 1.0 | 6.50 |

### 3.3 KV eviction 专项（cli, -c 8192, 长 prompt ~1360, n256）

| 编号 | 开关 | 驱逐日志条数 | RSS峰值(GiB) | EXIT |
|:---|:---|:---:|:---:|:---:|
| LC24 | KV_EVICT W256 | 105 | 6.34 | 0 |
| LC25 | KV_EVICT W1024 | 255 | 6.44 | 0 |
| LC26 | 无 eviction | 0 | 6.49 | 0 |

**结论**: KV eviction 使 45GB/8GB 极端比例下长上下文运行**不 OOM**（能力收益）；驱逐机制正常且不崩溃。

---

## 四、08-08 动态 MADV 改进（阶段 0-8）—— 消除负优化

### 4.1 各阶段数据（Qwen3-Next-80B Q4_K_M，-t 4）

| 阶段 | 配置 | pp | tg | 说明 |
|:---|:---|:---:|:---:|:---|
| 阶段0 基线 | 全开（静态 RANDOM）p32n16 | 0.44 | 0.26 | 负优化基线 |
| 阶段0 | 禁用 p32n16 | 2.74 | 1.41 | 上游最优 |
| 阶段1 | 全开 + KV q4_0 | 0.43 | 0.26 | KV 量化不解决瓶颈 |
| 阶段2a | 动态（prefill=SEQ, decode=RANDOM） | 2.82 | 0.25 | prefill 修复，decode 仍差 |
| 阶段2b | decode=**SEQUENTIAL** | 2.81 | **1.35** | 关键修复 |
| 阶段2b | decode=NORMAL | 2.57 | 1.41 | tg 最优 |
| **最终** | 全开（动态 MADV 全 SEQUENTIAL）p32n16 | **2.84** | **1.40** | 追平禁用 |
| 最终 | 禁用 p32n16 | 2.74 | 1.41 | 参考 |
| 长上下文 | 全开 p512n128 | **6.09** | **2.08** | |
| 长上下文 | 禁用 p512n128 | 6.33 | 2.15 | |

**消融发现**: decode 阶段 MADV_RANDOM 在 45GB/8GB 极端比例下拖慢 5.4×（0.25 vs 1.40）——工作集完全放不下，RANDOM 随机读远慢于 SEQUENTIAL 顺序预读。

**最终提升**（对比改进前全开）: 短上下文 pp **+545%**、tg **+438%**；长上下文 pp **+153%**、tg **+292%**；全开 vs 禁用差距缩至 **~0-4%**。

### 4.2 专家预取机制触发验证（临时调试计数，n=16）

| 观测点 | 修复前 | 修复后 |
|:---|:---:|:---:|
| `register_expert_tensor` | 144 | 144（48 层 × 3 张量） |
| `cache_router_experts` | 0 → 回归 0 | 912 |
| `get_cached_experts` | 0 | 846 |
| `issue_expert_willneed` | **0** | **846** |

> 修 3 个 bug 后机制确认真正触发（846 次 WILLNEED）。

### 4.3 预测精度诊断（n=64，累计 3200 采样）

| 预测器 | 精度 | 相对随机(≈2%) |
|:---|:---:|:---:|
| temporal（同层上一 token → 本 token） | **34.9%** | 17.5× |
| spatial（原 l-1→l） | 4.5% | 2.25× |

### 4.4 temporal A/B（干净代码）

**llama-bench p32n32 交错**：ON 平均 2.76/1.69；OFF 平均 2.73/1.72 → **解码中性（噪声内）**
**llama-cli n128 长生成**：生成 ON 1.9 / OFF 1.9（持平）；**prefill ON 2.2-2.3 vs OFF 2.0（+10-15%）**

### 4.5 瓶颈根因证据（阶段 8）

| 实验 | 数据 | 结论 |
|:---|:---|:---|
| 线程消融（n64） | t4: 1.9 / t6: 1.8 / t8: 1.3 | 加线程反而慢 → 非计算受限 |
| vmstat（n128 解码期） | SSD 读 ~500-560MB/s（容量 2.1GB/s 未饱和）；wa 9-13%；CPU 空闲 40-45% | **非 SSD I/O 受限** |

**诚实结论**: RK3588 80B 解码受**计算吞吐/并行度/内存带宽**共同限制，I/O 预取类机制（层预取+专家预取+WILLNEED）对解码提速存在物理上限。SLIM-ARC 端侧真实价值 = 消除负优化 + prefill +10-15% + 长上下文不 OOM 能力。

---

## 五、08-09 阶段 11-14 文献驱动 4 点改进（专家预取）

### 5.1 可观测性指标（改进1，n=64 基线）

`[SLIM-ARC-METRICS] samples=3216 issued=27836.7MB hit=12163.3MB waste=27008.3MB hit_rate=31.05% consistent=yes`

### 5.2 置信度门控（改进2，`SLIM_ARC_EXPERT_CONF=1`）—— WIN

| 配置 | issued(MB) | hit_rate | tg |
|:---|:---:|:---:|:---:|
| baseline | 27836.7 | 31.05% | 1.9 |
| **CONF=1** | **12123.6** | **55.35%** | 1.9 |

llama-bench A/B：base 平均 2.81/1.75；conf 平均 **2.89/1.77**（pp +3% / tg +1%）
→ **命中率 +24pp、下发字节 -56%、速度无损失**，明确收益，推荐开启

### 5.3 统一 I/O 预算（改进3，`SLIM_ARC_EXPERT_BUDGET=1`）

| 配置 | issued(MB) | hit_rate | tg |
|:---|:---:|:---:|:---:|
| baseline | 27836.7 | 31.05% | 1.9 |
| BUDGET=1（per-step 600MB） | 25848.9 | 28.78% | 1.9 |
| CONF+BUDGET | 12073.5 | 54.00% | 2.1 |

→ 机制正确（能截断突发，-7% I/O），但 RK3588 非 I/O 受限，速度中性

### 5.4 temporal+热门专家（改进4，`SLIM_ARC_EXPERT_POP=16`）—— 诚实负结果

| 配置 | issued(MB) | hit_rate | tg |
|:---|:---:|:---:|:---:|
| baseline | 27836.7 | 31.05% | 1.9 |
| POP=16 | **72634.4** | **19.31%** | 2.0 |

→ 热门并集稀释命中率（31→19%）、字节 +161%；**默认关闭**；ReMoE 式 locality 需训练 router（出框架范围）

### 5.5 改进后专家预取开关 bench（80B, p32n16t4）

| 配置 | pp | tg |
|:---|:---:|:---:|
| expert ON | 2.59 ± 0.00 | 1.41 ± 0.00 |
| expert OFF | 2.64 ± 0.00 | 1.44 ± 0.00 |

---

## 六、08-10 demo-ui 修复（非性能，稳定性/可用性）

- 3 文件 10 处修复（`index.html` 8 处 / `start-demo.sh` 1 / `llama_cli_server.py` 1），全部 `SLIM-ARC FIX 2026-08-10` 标注
- **长文本生成**：输出长度 96→918 字（约 9.6×），finish_reason "length"→"stop"（根因：80 字系统提示 + max_tokens 200）
- **聊天滚动**：2 轮修复（`.chat-messages`/`.chat` 加 min-height:0、`.main` 加 grid-template-rows:minmax(0,1fr)、auto-scroll 底部容差）
- 附带：HTTP r.ok 检查、escapeHtml 转义修复、llama-server/llama-cli 路径自动探测
- **未实施**：MoE 真实数据可视化（前端仍为假数据，因红线"不新增功能"约束）

---

## 七、汇总统计（关键指标一览）

| 指标 | 数值 | 来源 |
|:---|:---|:---|
| 80B 端侧首次可运行 | ✅ 8GB RK3588 + SSD，RSS ~6.3GB（45GB 模型按需分页） | §2 |
| MADV_RANDOM 端侧首次触发 | ✅ 45.1GiB RANDOM ×1（LD_PRELOAD 确认） | §2.3 |
| 负优化修复 | 全开 vs 禁用 4-6× → ~0-4% 持平 | §4 |
| 短上下文提升（改进后 vs 改进前全开） | pp **+545%**、tg **+438%** | §4 |
| 长上下文提升 | pp **+153%**、tg **+292%** | §4 |
| prefill（temporal A/B） | +10-15% | §4.4 |
| 专家预取置信度门控 | 命中率 31→55%、下发 -56%、速度无损 | §5.2 |
| 长上下文不 OOM 能力 | -c 8192~16384，KV eviction 正常 | §3 |
| 小模型端侧基线 | Qwen3-4B pp 8.57/tg 6.90；OLMoE tg 10.7 | §1 |

### 与初赛 WSL 测试的定位差异

| 维度 | 初赛 WSL（i9-13900H, x86, 8-32GB cgroup） | 端侧 RK3588（ARM, 8GB 物理） |
|:---|:---|:---|
| 核心结论 | 80B decode +3.6-5.4×（MADV_RANDOM 核心驱动） | 静态 RANDOM 反而负优化 4-6× → 动态 MADV 追平 |
| 瓶颈 | I/O（冷启动）+ MADV 收益大 | 计算/内存带宽（非 I/O） |
| 价值 | 让 45GB 模型在 8GB cgroup 可运行且加速 | 消除负优化 + prefill +10-15% + 长上下文能力 |

---

## 八、剩余限制

1. **无 cgroup 限内存**（无 root）→ 无法复现初赛三档对比，为原生 8GB 单档
2. **无严格冷缓存**（无 root 无法 `drop_caches`）→ 冷/热基于连续两次近似
3. **MADV 适用域**：端侧 8GB 物理内存下 RANDOM 负优化，核心价值转为"消除负优化 + 能力收益"，与 WSL 场景相反——反映 SLIM-ARC 需按"内存比例"而非"是否 MoE"选择策略
4. **demo-ui MoE 真实数据展示未实施**（红线约束）

## 数据文件索引

- 小模型/首测: [`docs/rk3588_test_notes/2026-08-05-昨日实验归档/`](../docs/rk3588_test_notes/2026-08-05-昨日实验归档/)
- 80B 矩阵/冒烟/长上下文: [`docs/rk3588_test_notes/80B-长上下文测试归档/`](../docs/rk3588_test_notes/80B-长上下文测试归档/)
- 动态 MADV/专家预取改进: [`docs/rk3588_improvement/改进记录.md`](../docs/rk3588_improvement/改进记录.md)、[`docs/rk3588_improvement/测试数据.md`](../docs/rk3588_improvement/测试数据.md)
- 专家预取 bench/指标: [`docs/rk3588_test_notes/bench-expert-*.txt`](../docs/rk3588_test_notes/bench-expert-on-r1.txt)、[`docs/rk3588_test_notes/raw-80b-metrics.txt`](../docs/rk3588_test_notes/raw-80b-metrics.txt)
- demo-ui: [`docs/rk3588_test_notes/demo-ui-summary-2026-08-10.md`](../docs/rk3588_test_notes/demo-ui-summary-2026-08-10.md)
