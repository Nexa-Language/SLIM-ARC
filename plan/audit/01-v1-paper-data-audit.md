# SLIM-ARC 论文数据溯源审计报告（v1）

## 审计元信息

- **审计日期**: 2026-06-26
- **审计人**: Zoo (architect 模式)
- **审计对象**: [`reports/Competition_Report/`](../../reports/Competition_Report/) LaTeX 论文及配套数据
- **审计范围**: 论文 6 个 section + figures + logs/ablation/raw-80b/ + logs/ablation/full-rerun/ + logs/gsm8k_*
- **审计方法**: 从论文出发，逐条数据声明回溯到原始 llama-bench 日志，交叉验证数值、误差、配置一致性
- **对比基准**: [`plan/audit/00-v1-completion-audit.md`](00-v1-completion-audit.md)（2026-06-23 首次审计）
- **总体结论**: 相比首次审计，**数据可信度显著提升**，80B 核心数据已有原始日志支撑，论文诚实记录负面结果。但仍存在 **figures 数据与日志不一致、table 与 figure 环境混淆、个别数据点无溯源** 等中等问题。

---

## 一、与首次审计对比 — 改进项

首次审计（2026-06-23）指出的严重问题，本次核查确认已修复：

| 首次问题 | 当时状态 | 当前状态 | 证据 |
|---------|---------|---------|------|
| 80B 数据无原始日志 | 🔴 严重 | ✅ 已修复 | [`logs/ablation/raw-80b/`](../../logs/ablation/raw-80b/) 16 个原始 txt + [`logs/ablation/full-rerun/`](../../logs/ablation/full-rerun/) 10 个 txt |
| 80B 343% 提升无法溯源 | 🔴 严重 | ✅ 已修正 | 论文不再声称 343%，改为"0.08→5.16 t/s 累计 64.5×"，由 optimization-chain-summary 溯源 |
| baseline OOM 自相矛盾 | 🔴 严重 | ✅ 已修正 | 论文统一表述：baseline 8GB tg1=0.08（能跑但极慢），不再说"OOM" |
| `scripts/env/setup-cgroups.sh` 不存在 | 🔴 虚假 | ✅ 已修复 | 文件现在存在，[`scripts/env/setup-cgroups.sh`](../../scripts/env/setup-cgroups.sh) |
| Phase 2b KV 换页标 ✅ 但未集成 | 🔴 夸大 | ✅ 已诚实 | 论文 04_implementation.tex:45 明确"接口完整但推理流程深度集成为后续工作" |
| 四份 CSV 数据挑选 | 🔴 数据挑选 | ⚠️ 缓解 | old-backup 保留旧 CSV，新数据用 full-rerun 系列，但小模型数据仍挑了 020442 |

**重大进步**: 论文学术诚实度大幅提升——
- 新增 GSM8K 精度验证，诚实记录 IQ4_XS 推理崩溃（0/10=0%）
- 新增 speculative decoding 负面结果（-53.2%）
- 新增数据波动分析（tg8 0.28→1.03，承认波动）
- 新增 FlashAttention 与 eviction 冲突的负面结果
- 不再宣称"全模块 ✅"，明确标注后续工作

---

## 二、论文数据溯源核查

### 2.1 核心实验数据 — ✅ 基本可溯源

#### 表 tab:core_iq4xs（80B IQ4_XS 三档）

| 论文数据 | 原始日志 | 一致性 |
|---------|---------|--------|
| 8GB: 超时 | 无对应日志（合理，超时） | ✅ |
| 16GB: tg64=2.27±0.38 | [`core-iq4xs-16g.txt`](../../logs/ablation/full-rerun/core-iq4xs-16g.txt) tg64=2.27±0.38 | ✅ 完全一致 |
| 32GB: pp64=4.44±1.53, tg48=3.03±0.29 | [`core-iq4xs-32g.txt`](../../logs/ablation/full-rerun/core-iq4xs-32g.txt) pp64=4.44±1.53, tg48=3.03±0.29 | ✅ 完全一致 |

**判定**: 核心三档数据完全可溯源，数值与误差均匹配。

#### 表 tab:eval_flashattn（FlashAttention 加速）

| 论文数据 | 原始日志 | 一致性 |
|---------|---------|--------|
| 无 FA: pp64=5.89, tg48=3.01 | [`optimization-chain-summary.txt`](../../logs/ablation/raw-80b/optimization-chain-summary.txt) baseline pp64=5.89 tg48=3.01 | ✅ 一致 |
| -fa on: pp64=6.64, tg48=3.90 | [`80b-32g-flashattn-on-pp64-tg48.txt`](../../logs/ablation/raw-80b/80b-32g-flashattn-on-pp64-tg48.txt) 6.64±2.37, 3.90±0.25 | ✅ 一致 |
| -fa auto: pp64=12.99, tg48=5.16 | optimization-chain-summary: 12.99, 5.16 | ✅ 一致 |

**问题 ⚠️**: [`80b-32g-flashattn-off-pp64-tg48.txt`](../../logs/ablation/raw-80b/80b-32g-flashattn-off-pp64-tg48.txt) 报错 "failed to create context"，即"无 FA"的原始日志是失败的。论文引用的 5.89/3.01 来自 optimization-chain-summary，但该 summary 未明确标注 FA 状态。**建议补一次成功的 fa-off 实验日志**，否则"无 FA"数据点的溯源链条断裂。

#### 表 tab:ablation_single（单点消融）

| 论文数据 | 原始日志 | 一致性 |
|---------|---------|--------|
| Full: pp64=4.44, tg48=3.77 | [`core-iq4xs-32g.txt`](../../logs/ablation/full-rerun/core-iq4xs-32g.txt) pp64=4.44, tg48=3.03；[`80b-32g-ablation-full.txt`](../../logs/ablation/full-rerun/80b-32g-ablation-full.txt) pp64=4.72, tg48=3.77 | ⚠️ **tg48=3.77 来自 ablation-full，pp64=4.44 来自 core-iq4xs，两个不同日志拼接** |
| -MADV: pp64=3.72, tg48=2.15 | [`80b-32g-ablation-no-madv.txt`](../../logs/ablation/full-rerun/80b-32g-ablation-no-madv.txt) 3.72±0.57, 2.15±0.18 | ✅ 完全一致 |
| -KV q4_0: tg48=3.92 | 无对应原始日志 | 🔴 **数据点无溯源** |
| +Eviction: tg48=3.30 | [`80b-32g-ablation-evict.txt`](../../logs/ablation/full-rerun/80b-32g-ablation-evict.txt)？需核实 | ⚠️ 待核实 |

**问题 🔴**: 
1. Full 行的 pp64 和 tg48 来自**两个不同日志**（core-iq4xs-32g 的 4.44/3.03 与 ablation-full 的 4.72/3.77）。论文取 pp64=4.44（更小值）+ tg48=3.77（更大值），**拼接出了实际不存在的配置组合**。应统一用同一日志的数据。
2. "-KV q4_0 (KV f16)" 行的 tg48=3.92 找不到对应原始日志。可能是从 fig_performance_landscape 的 32GB baseline Q4_K_M 数据 1.24 推算，但 3.92 这个具体值无溯源。

#### 表 tab:eval_kv_quant（KV 量化对比）

| 论文数据 | 原始日志 | 一致性 |
|---------|---------|--------|
| F16: tg48=3.92 | 无对应日志 | 🔴 无溯源 |
| Q8_0: pp64=5.37, tg48=2.91 | [`80b-32g-kv-q8_0-pp64-tg48.txt`](../../logs/ablation/raw-80b/80b-32g-kv-q8_0-pp64-tg48.txt) 5.37±1.59, 2.91±0.17 | ✅ 一致 |
| Q4_0: pp64=4.44, tg48=3.77 | 同 tab:ablation_single Full 行 | ⚠️ 拼接问题同上 |

### 2.2 GSM8K 精度数据 — ✅ 完全可溯源

| 论文数据 | 原始日志 | 一致性 |
|---------|---------|--------|
| Qwen3-4B Q4_K_M: 15/20=75%, 7.8 t/s | [`gsm8k_qwen3_4b_20q_summary.json`](../../logs/gsm8k_qwen3_4b_20q_summary.json) accuracy=0.75, correct=15, total=20, avg_tps=7.78 | ✅ 完全一致 |
| 80B Q4_K_M+KVq4_0: 5/10=50%, 0.7 t/s | [`gsm8k_80b_q4km_10q_summary.json`](../../logs/gsm8k_80b_q4km_10q_summary.json) accuracy=0.5, correct=5, total=10, avg_tps=0.70 | ✅ 完全一致 |
| 80B IQ4_XS+KVq4_0: 0/10=0%, 1.7 t/s | [`gsm8k_80b_10q_summary.json`](../../logs/gsm8k_80b_10q_summary.json) accuracy=0.0, correct=0, total=10, avg_tps=1.67 | ✅ 完全一致 |

**判定**: GSM8K 精度数据完全可溯源，且诚实记录了 IQ4_XS 推理崩溃的负面结果。这是论文的亮点。

### 2.3 80B 8GB 核心卖点数据 — ✅ 可溯源

论文 abstract: "8GB环境下从不可运行变为可运行（0.76 t/s）"

| 论文数据 | 原始日志 | 一致性 |
|---------|---------|--------|
| baseline 8GB tg1=0.08 | [`80b-8g-baseline-pp4-tg1.txt`](../../logs/ablation/raw-80b/80b-8g-baseline-pp4-tg1.txt) tg1=0.08±0.00 | ✅ |
| SLIM-ARC 8GB tg1=0.43 | [`80b-8g-slim-arc-pp4-tg1.txt`](../../logs/ablation/raw-80b/80b-8g-slim-arc-pp4-tg1.txt) tg1=0.43±0.01 | ✅ |
| SLIM-ARC 8GB IQ4_XS tg1=0.76 | [`80b-iq4xs-16g-summary.txt`](../../logs/ablation/raw-80b/80b-iq4xs-16g-summary.txt) 8GB IQ4_XS tg1=0.76±0.13 | ✅ |

**判定**: 80B 8GB 的"0.08→0.76"核心数据有完整原始日志支撑。这是相比首次审计的最大改进。

### 2.4 小模型数据 — ⚠️ 仍存在挑选

论文 fig_small_models 使用的数据（来自 [`generate_figures_v2.py`](../../reports/Competition_Report/figures/generate_figures_v2.py):360-383）:

| 模型 | Tier | baseline pp64 | slim-arc pp64 | 来源 CSV |
|------|------|--------------|--------------|---------|
| Qwen3-4B | 8GB | 22.87 | 24.58 | 020442 ✅ |
| OLMoE | 8GB | 88.27 | 95.99 | 020442 ✅ |
| OLMoE | 12GB | 100.09 | 91.25 | **014809**（不是 020442！） |
| OLMoE | 16GB | 116.97 | 110.77 | 020442 ✅ |

**问题 ⚠️**: 
1. OLMoE 12GB 的 pp64 baseline=100.09 来自 014809 CSV，但 slim-arc=91.25 也来自 014809。**这组数据中 slim-arc 比 baseline 慢 -8.8%**，被画进了 fig_small_models 但论文文字未强调这个负结果
2. OLMoE 12GB tg16 slim-arc=26.88 vs baseline=39.93（**-32.8%**），也是负结果被画进图但未文字说明
3. 四份 CSV 仍同时存在于 [`logs/ablation/`](../../logs/ablation/)，未说明为何挑选 020442 为主数据

**判定**: 小模型数据虽然可溯源到 CSV，但挑选标准不透明，且负结果（OLMoE 12GB slim-arc 更慢）被画进图却未在论文文字中诚实说明，**容易被评委识破为选择性呈现**。

### 2.5 Figures 数据真实性 — ⚠️ 部分模拟

#### fig_performance_landscape

**panel (a) 三档柱状图**: 数据 `tg_8gb=[0.08, 0.42, 0.76, 0.76]`、`tg_16gb=[0.18, 1.03, 2.27, 2.27]`、`tg_32gb=[0.08, 2.68, 3.03, 5.16]`
- 8GB baseline=0.08 ✅，8GB SLIM-ARC=0.42 (日志 0.43，**四舍五入**)，8GB Full=0.76 ✅
- 16GB baseline=0.18 ✅（80b-16g-32g-summary），16GB SLIM-ARC=1.03 ✅，16GB Full=2.27 ✅
- 32GB baseline=0.08 — **可疑**，32GB 无 cgroup warm cache 的 baseline 应该比 8GB 快，但图里 32GB baseline 也是 0.08。可能是笔误或与 8GB 混淆

**panel (b) 优化堆叠瀑布**: `values=[0.08, 0.08, 0.42, 0.76, 0.76]`，Repack OFF 后仍是 0.08 — 合理（repack 只影响内存不直接影响速度）

**panel (c) 量化格式对比**: 16GB Q4_K_M pp32=1.34 tg8=1.03，IQ4_XS pp32=1.71 tg8=1.12
- Q4_K_M 16GB pp32=1.34 ✅（80b-iq4xs-16g-summary 对比行），tg8=1.03 ✅（取上界）
- IQ4_XS 16GB pp32=1.71 ✅，tg8=1.12 ✅
- 32GB Q4_K_M pp32=1.90 tg8=1.24 ✅，IQ4_XS pp32=2.64 tg8=2.45 — **2.64 无对应日志**，可能是估算

**panel (d) 散点图**: 8GB SLIM-ARC 写 (0.27, 0.42)，但日志 pp4=0.25 tg1=0.43 — **pp 不一致**（0.27 vs 0.25）

#### fig_volatility_radar

**panel (a) 波动箱线图**: 脚本注释明确写 "Simulated data based on real observations"，`data_16gb=[0.28, 0.39, 0.39, 0.64, 0.68, 0.73, 0.83, 0.90, 1.03, 1.12]` — **承认是模拟数据**。论文 caption 写"80B 16GB tg8 从 0.28 到 1.03"，但脚本数据包含 1.12，超过 1.03 — **caption 与脚本数据不一致**。

**判定**: 波动图是模拟数据，虽有注释说明，但论文 caption 未标注"示意性数据"，**存在误导风险**。

#### fig_kv_and_threads

**panel (a) KV 量化对比**: 使用 16GB 数据 `pp_mean=[1.26, 1.31, 1.34], tg_mean=[0.90, 0.83, 1.03]`，但论文 tab:eval_kv_quant 给的是 32GB 数据。**figure 和 table 用不同环境的数据，且未在 figure caption 标注环境**，读者会混淆。

**panel (b) 线程扩展**: `threads=[4,6,8,14], tg_vals=[0.76, 0.85, 1.03, 0.77]` — 14 线程比 8 线程慢，论文解释为"memory-bound"，合理。但这些数据无对应原始日志，可能是估算。

### 2.6 论文文字声明的数值核查

#### Abstract

| 声明 | 核查 | 一致性 |
|------|------|--------|
| "8GB环境下从不可运行变为可运行（0.76 t/s）" | baseline 0.08 → SLIM-ARC 0.76 | ✅ 但"不可运行"措辞不准（baseline 0.08 是能跑但极慢） |
| "32GB热缓存环境下达到5.16 t/s" | optimization-chain: 5.16 | ✅ |
| "累计实现64.5×加速" | 0.08→5.16 = 64.5× | ✅ 计算正确 |
| "FlashAttention decode +71.4%" | 3.01→5.16 = +71.4% | ✅ |
| "GSM8K Qwen3-4B 75%精度" | 15/20=75% | ✅ |
| "MADV_RANDOM 贡献 -43%" | 3.77→2.15 = -43% | ✅ 但表述为"贡献"易误解（-43% 是关闭后的下降，即贡献是+74%相对值） |

#### Section 3.2 "prefill 下降 57%"

论文 03_core_design.tex:66: "prefill 速度下降约 57%"
核查: 80b-8g-baseline-pp16-tg4.txt pp16=0.63，80b-8g-slim-arc-v2-pp16-tg4.txt pp16=0.21
计算: (0.63-0.21)/0.63 = 66.7%，不是 57%。**数值不一致**，57% 可能来自其他配置。

#### Section 3.2 "decode 提升 200-850%"

核查: 8GB tg1 baseline 0.08 → slim-arc 0.43 = +437%；8GB IQ4_XS tg1 0.76 = +850%。**850% 一致，200% 偏低**（最低也是 +437%）。可能是旧数据残留。

#### Section 5 "8GB 累计提升 9.5×（0.08→0.76）"

计算: 0.76/0.08 = 9.5× ✅

#### Section 5 "16GB 和 32GB 环境下分别提升 12.6× 和 64.5×"

- 16GB: baseline tg8=0.18 → Full tg8=2.27 = 12.6× ✅
- 32GB: 0.08 → 5.16 = 64.5× — **但 32GB baseline 用 0.08 与 8GB 相同，可疑**

---

## 三、仍存在的问题

### 🔴 严重问题（需修复）

1. **tab:ablation_single Full 行数据拼接**: pp64=4.44（core-iq4xs-32g）和 tg48=3.77（ablation-full）来自两个不同日志，拼接出了不存在的配置组合。**建议统一用同一日志的数据**。

2. **"-KV q4_0" 和 "F16" 行无原始日志**: tab:ablation_single 和 tab:eval_kv_quant 中的 F16 tg48=3.92 和 -KV q4_0 tg48=3.92 找不到对应原始日志。**需补跑或标注来源**。

3. **32GB baseline=0.08 可疑**: fig_performance_landscape panel (a) 和 Section 5 都把 32GB baseline 标为 0.08，与 8GB 相同。但 32GB warm cache 的 baseline 应该明显快于 8GB cold。**需核实是笔误还是实测**。

### ⚠️ 中等问题（建议修复）

4. **fa-off 原始日志失败**: `80b-32g-flashattn-off-pp64-tg48.txt` 报错 "failed to create context"，论文引用的 5.89/3.01 来自 optimization-chain-summary 但该 summary 未标 FA 状态。**建议补一次成功的 fa-off 实验**。

5. **fig_volatility_radar 是模拟数据**: 脚本注释"Simulated data based on real observations"，但论文 caption 未标注。**建议在 caption 加"示意性数据，基于实测观察"**。

6. **fig_kv_and_threads 与 tab:eval_kv_quant 环境不一致**: figure 用 16GB 数据，table 用 32GB 数据，figure caption 虽标了 16GB 但读者仍易混淆。**建议统一或明确标注差异原因**。

7. **小模型数据挑选不透明**: 四份 CSV 同时存在，论文选 020442 为主但 OLMoE 12GB 又用 014809。**建议在论文说明挑选标准（如"取中位数"或"取最优"）**。

8. **OLMoE 12GB 负结果未文字说明**: fig_small_models 画出 OLMoE 12GB slim-arc 比 baseline 慢 -8.8%/-32.8%，但论文文字未诚实说明。**建议在图注或文字中标注此负结果**。

9. **fig_performance_landscape panel (d) 8GB SLIM-ARC pp=0.27 与日志 0.25 不一致**: 小问题但影响可复现性。

10. **Section 3.2 "prefill 下降 57%" 与实测 66.7% 不一致**: 数值偏差 10 个百分点。

### ✅ 改进确认

11. **80B 核心数据可溯源**: 8GB/16GB/32GB 三档的 pp/tg 数据均有原始日志支撑（首次审计的严重问题已修复）

12. **GSM8K 精度完全可溯源**: 三组精度数据与 JSON summary 完全一致

13. **环境脚本已补全**: setup-cgroups.sh 现已存在

14. **KV eviction 诚实标注后续工作**: 不再标 ✅

15. **负面结果诚实记录**: IQ4_XS 推理崩溃、speculative decoding -53.2%、FlashAttention 与 eviction 冲突、数据波动 0.28→1.03

16. **核心实验脚本可复现**: [`scripts/bench/run-core-experiments.sh`](../../scripts/bench/run-core-experiments.sh) 存在且可读

---

## 四、论文质量评估

### 学术诚实度 — ✅ 显著提升

论文在以下方面体现了学术诚实：
- 明确标注后续工作（KV eviction 深度集成）
- 记录负面结果（IQ4_XS 崩溃、spec decoding 失败、FA-eviction 冲突）
- 承认数据波动（tg8 0.28→1.03）
- 不再宣称"全模块完成"
- 不再宣称"baseline OOM"（改为准确的"0.08 t/s 极慢"）

### 数据可信度 — ⚠️ 中上

- 核心数据（80B 三档、GSM8K、FlashAttention）可溯源 ✅
- 部分数据点无溯源（F16、-KV q4_0）🔴
- 部分数据拼接（tab:ablation_single Full 行）🔴
- figures 有模拟数据（volatility）⚠️
- 小模型数据挑选不透明 ⚠️

### 可复现性 — ✅ 基本达标

- 核心实验脚本 [`run-core-experiments.sh`](../../scripts/bench/run-core-experiments.sh) 存在
- 环境脚本 [`setup-cgroups.sh`](../../scripts/env/setup-cgroups.sh) 存在
- 集成脚本 [`apply-slim-arc.py`](../../scripts/apply-slim-arc.py) 存在
- 原始日志保存完整（raw-80b/ 16个 + full-rerun/ 10个）

---

## 五、改进建议

### 必须修复（影响数据可信度）

1. **统一 tab:ablation_single Full 行数据来源**: 用同一日志的 pp64 和 tg48，不要拼接
2. **补跑 F16 和 -KV q4_0 实验**: 或标注数据来源（如"估算"或"来自 fig_performance_landscape"）
3. **核实 32GB baseline=0.08**: 若是笔误则改为实测值；若确实是 0.08 需解释为何与 8GB 相同
4. **补跑 fa-off 成功实验**: 当前日志报错，需重新跑一次

### 建议修复（提升学术质量）

5. **fig_volatility_radar caption 加"示意性数据"标注**
6. **统一 figure 与 table 环境**: 或在 caption 明确标注环境差异
7. **小模型数据挑选标准说明**: 在论文文字或图注说明为何选 020442
8. **OLMoE 12GB 负结果文字说明**: 诚实标注 slim-arc 在 12GB 的负结果
9. **修正 Section 3.2 prefill 下降数值**: 57% → 66.7%（或标注配置差异）
10. **修正 fig_performance_landscape panel (d) 8GB SLIM-ARC pp=0.27 → 0.25**

### 锦上添花

11. **补 Q3_K_M 数据**: tab:quant_comparison 中 Q3_K_M 行是"---"，可补跑
12. **补 WikiText-2 PPL 实测**: 当前 F16 参考值来自技术报告未实测，可补测

---

## 六、结论

相比首次审计（2026-06-23），SLIM-ARC 项目在**数据可信度和学术诚实度上有显著进步**：

- 80B 核心数据从"无原始日志"变为"完全可溯源"
- 论文从"夸大完成度"变为"诚实记录负面结果和后续工作"
- 环境脚本从"不存在"变为"已补全"
- 核心实验脚本可复现

**但仍有 3 个严重问题**（数据拼接、无溯源数据点、32GB baseline 可疑）和 7 个中等问题（模拟数据、环境不一致、挑选不透明等）需要修复。

**建议**: 修复第三节的 3 个严重问题后，论文数据层面可达到比赛正式材料的可信度要求。当前状态可以作为初稿提交，但**答辩前必须修复数据拼接和无溯源数据点问题**，否则评委交叉核对表格与日志时会发现问题。

---

## 附: 审计证据索引

| 证据 | 路径 |
|------|------|
| 论文 | [`reports/Competition_Report/sections/`](../../reports/Competition_Report/sections/) |
| Figures 脚本 | [`reports/Competition_Report/figures/generate_figures_v2.py`](../../reports/Competition_Report/figures/generate_figures_v2.py) |
| 80B 原始日志 | [`logs/ablation/raw-80b/`](../../logs/ablation/raw-80b/) |
| Full-rerun 日志 | [`logs/ablation/full-rerun/`](../../logs/ablation/full-rerun/) |
| GSM8K 结果 | [`logs/gsm8k_*_summary.json`](../../logs/) |
| 核心实验脚本 | [`scripts/bench/run-core-experiments.sh`](../../scripts/bench/run-core-experiments.sh) |
| 环境脚本 | [`scripts/env/setup-cgroups.sh`](../../scripts/env/setup-cgroups.sh) |
| 首次审计 | [`plan/audit/00-v1-completion-audit.md`](00-v1-completion-audit.md) |
