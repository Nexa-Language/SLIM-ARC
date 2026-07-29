# SLIM-ARC 全局审计报告 v1

## 审计元信息

- **审计日期**: 2026-06-26
- **审计人**: Zoo (architect 模式)
- **审计范围**: 整个工作区（不止数据，含代码、脚本、文档、配置、日志、gitignore 全维度）
- **对比基准**: [`00-v1-completion-audit.md`](00-v1-completion-audit.md) + [`01-v1-paper-data-audit.md`](01-v1-paper-data-audit.md)
- **审计方法**: 从论文出发，逐文件交叉验证 src/、patches/、scripts/、docs/、config/、README、AGENT.md、ROADMAP、tests/、.gitignore 的一致性
- **总体结论**: 论文数据层面已修复到位（commit db79afe），但**文档层面严重过时**——README、AGENT.md、docs/design/architecture.md、config/slim-arc.toml 仍停留在"基于 FlexInfer"的旧叙事，与实际"基于 upstream llama.cpp + mmap + madvise"的实现严重脱节。代码实际比 raw_analysis 报告声称的更完整（KV eviction 已真集成）。

---

## 一、修复确认（commit db79afe）

论文数据层面的修复已落实：

| 修复项 | 论文位置 | 修复前 | 修复后 | 核查 |
|--------|---------|--------|--------|------|
| tab:ablation_single Full tg48 | 05_evaluation.tex:253 | 3.77（拼接） | 3.03（core-iq4xs-32g） | ✅ 一致 |
| 32GB baseline | fig_performance_landscape | 0.08（错误） | 3.01（80b-32g-baseline-pp64-tg48.txt） | ✅ 一致 |
| MADV 贡献 | 05_evaluation.tex:255-256 | -43% | -41% | ⚠️ 见下方问题1 |
| prefill 下降 | 03_core_design.tex:66 | 57% | 67% | ✅ 0.63→0.21=66.7% |
| decode 提升 | 03_core_design.tex:66 | 200-850% | 437-850% | ✅ 0.08→0.43=+437% |
| scatter pp | generate_figures_v2.py:138 | 0.27 | 0.25 | ✅ 日志 0.25 |
| volatility caption | 05_evaluation.tex:323 | 无标注 | "示意性数据" | ✅ 已加 |

---

## 二、仍存在的问题

### 🔴 严重问题（文档与实现严重脱节）

#### 问题 1: MADV 贡献百分比计算错误

论文 05_evaluation.tex:255-256 写 "-41%"，但实际计算：
- Full tg48 = 3.03，-MADV tg48 = 2.15
- 相对 Full 下降：(3.03-2.15)/3.03 = **29.0%**，不是 41%
- 相对 -MADV 增长：(3.03-2.15)/2.15 = **40.9%**（这是"+41%"，是 Full 相对 no-MADV 的提升，不是 no-MADV 相对 Full 的下降）

论文用 "-41%" 表示"关闭 MADV 后下降"，但 29% 才是正确的下降百分比。41% 是 Full 相对 no-MADV 的提升百分比。**表述方向错误**。

#### 问题 2: README.md 严重过时（基于 FlexInfer 的旧叙事）

[`README.md`](../../README.md) 多处与实际严重脱节：

| 位置 | README 声称 | 实际 | 严重度 |
|------|------------|------|--------|
| :13 | "基于 FlexInfer 的权重卸载框架" | 已放弃 FlexInfer，用 upstream llama.cpp | 🔴 |
| :20-22 | 列 FlexInfer/DUAL-BLADE/MobileMoE PDF | docs/papers/ 下无这些 PDF | 🔴 |
| :65-68 | 模型表只列 Qwen3-4B + Qwen3-Next-A3B | 实际核心模型是 80B + OLMoE | 🔴 |
| :68 | "Qwen3-Next-A3B ~1.8GB" | 实际用 80B（45GB） | 🔴 |
| :76-86 | 快速开始引用 `src/flexinfer/build-host.sh`、`scripts/convert-models.sh`、`scripts/bench/run-baseline.sh`、`scripts/bench/run-slim-arc.sh` | **这些脚本均不存在** | 🔴 |
| :107 | 项目结构 `src/flexinfer/`（待移入） | 实际是 `src/llama-upstream/`（主开发）+ `src/flexinfer/`（参考） | 🔴 |
| :118-126 | 优化方向表全是"计划中" | 大部分已实现 | ⚠️ |
| :138 | "FlexInfer — 核心 baseline" | 实际 baseline 是 upstream llama.cpp | 🔴 |

**影响**: 评委看 README 会以为项目基于 FlexInfer，但论文说基于 upstream llama.cpp。**自相矛盾**，且 README 的快速开始命令无法执行。

#### 问题 3: AGENT.md 过时

[`AGENT.md`](../../AGENT.md) 多处过时：

| 位置 | AGENT.md 声称 | 实际 |
|------|--------------|------|
| :19 | "主语言: C/C++（FlexInfer / llama.cpp 生态）" | FlexInfer 已放弃 |
| :20 | "构建: CMake 3.14+，build-host.sh 方式" | 用 cmake -DGGML_CPU_REPACK=OFF，无 build-host.sh |
| :22 | "GGUF，4096 字节对齐（FlexInfer Direct I/O 要求）" | FlexInfer 已放弃，4096 对齐不再必要 |
| :23 | "Q4_K_M 为主，Q8_0 用于精度对比" | 实际 IQ4_XS 为主（论文核心） |
| :29 | "docs/papers/FlexInfer/ 仅作参考，运行前需移入 src/flexinfer/" | src/flexinfer/ 是参考源码，不运行 |
| :44 | "Phase 0: 环境搭建与基线复现（llama.cpp + FlexInfer）" | FlexInfer baseline 未做 |
| :55 | "FlexInfer 是纯 CPU 框架" | 实际用 llama.cpp |
| :58 | "模型固定: Qwen3-4B + Qwen3-Next-A3B" | 实际用 80B + OLMoE |
| :59 | "Baseline: llama.cpp + 自复现 FlexInfer" | FlexInfer 未复现 |

**影响**: AGENT.md 是 Agent 协作规则，过时会导致后续 agent 误解项目状态。

#### 问题 4: docs/design/architecture.md 严重过时

[`docs/design/architecture.md`](../../docs/design/architecture.md) 第 14-41 行架构图仍写"(FlexInfer)"、"(DUAL-BLADE)"、"(MobileMoE)"，第 38-40 行"FlexInfer / ggml 底层"，第 45 行"权重卸载模块（继承自 FlexInfer）"，第 84 行"验证模型: Qwen3-Next-A3B"。

**与论文 03_core_design.tex 的三层架构（内核协同层 + 运行时调度层 + 量化优化层）完全不同**。论文已更新为 upstream llama.cpp + mmap + madvise 叙事，但 design 文档仍是 FlexInfer 叙事。

#### 问题 5: config/slim-arc.toml 过时

[`config/slim-arc.toml`](../../config/slim-arc.toml):
- `[models.moe]` 写 `Qwen3-Next-A3B` + `weight_size = "TBD"` — 实际用 `Qwen3-Next-80B-A3B`（45GB）
- `[benchmarks]` 引用 `data/benchmarks/wikitext-103/`、`hellaswag/`、`c4/` — 这些目录不存在，实际只有 `data/benchmarks/gsm8k/`
- `[prefetch]` 配置与代码实际默认值（window=2/3）可能不一致

### ⚠️ 中等问题（数据/代码一致性）

#### 问题 6: raw_analysis 报告与代码实际不一致

[`reports/raw_analysis/phase4-ablation-summary.md`](../../reports/raw_analysis/phase4-ablation-summary.md) 和 [`project-progress-summary.md`](../../reports/raw_analysis/project-progress-summary.md):

| 报告声称 | 代码实际 | 矛盾 |
|---------|---------|------|
| "evict_layer ⚠️ 接口完成，未集成调用" | `llama-context.cpp:2485` 调用 `notify_layer_compute`（含 evict 逻辑）；`llama-context.cpp:2551-2558` 有 SLIM_ARC_KV_EVICT 真集成 StreamingLLM eviction | raw_analysis 过时 |
| "Phase 2b KV 换页 ⚠️ 接口完成，未集成推理" | 代码已集成（环境变量控制） | raw_analysis 过时 |
| "prefill -57%" | 论文已改 67% | raw_analysis 未同步论文修复 |
| "Phase 2d Tile 流水线 ⚠️ 隐式实现" | 论文已不再声称 Tile 流水线 | raw_analysis 保留旧叙事 |

**影响**: raw_analysis 是"原始分析报告"，与论文（修复后）和代码（已集成）都不一致。若评委同时看 raw_analysis 和论文，会发现矛盾。

#### 问题 7: project-progress-summary 含无溯源数据

[`reports/raw_analysis/project-progress-summary.md`](../../reports/raw_analysis/project-progress-summary.md) 第 99 行："80B 6GB 四组消融：prefetch 仍冗余，MADV_RANDOM 是唯一驱动（decode +112%）"— **logs/ablation/ 下无 6GB 原始日志**。

第 102 行："长上下文验证（OLMoE pp512+tg32）小模型 prefetch 反而有害（-18%）"— **也无对应原始日志**。

#### 问题 8: 旧报告（defense-data-summary、optimization-attribution-analysis）未清理

[`reports/raw_analysis/defense-data-summary.md`](../../reports/raw_analysis/defense-data-summary.md) 和 [`optimization-attribution-analysis.md`](../../reports/raw_analysis/optimization-attribution-analysis.md) 仍存在，可能包含已被论文修正的旧数据（如 343% 提升、baseline OOM 等说法）。评委若先看这些会获得错误印象。

#### 问题 9: tests/ 缺失文件

[`tests/README.md`](../../tests/README.md) 引用 `test_prefetch.cpp`、`test_model_load.sh`、`test_bench_smoke.sh`，但 tests/ 下只有 `README.md` 和 `test_env.sh`。**3 个测试文件不存在**。

#### 问题 10: scripts/profile/src/ 残留旧代码

`.gitignore` 第 277 行 ignore 了 `scripts/profile/src/`，但该目录下仍有完整的 flexinfer 和 llama-upstream 副本（含旧版 llama-model-loader.cpp，与实际 src/ 不一致）。**残留垃圾**，可能造成混淆。

#### 问题 11: apply-slim-arc.py 与 src 代码细节差异

[`scripts/apply-slim-arc.py`](../../scripts/apply-slim-arc.py) 第 86-99 行的 madv_block **不含** `register_mmap_region` 调用，但 [`src/llama-upstream/src/llama-model-loader.cpp`](../../src/llama-upstream/src/llama-model-loader.cpp) 第 1370 行有。apply 脚本可能未更新到包含动态 MADV 切换的版本。若用 apply 脚本重新应用，**动态 MADV 切换功能会丢失**。

#### 问题 12: 32GB "baseline" 语义问题

论文将 32GB baseline 改为 3.01（来自 `80b-32g-baseline-pp64-tg48.txt`），但该日志的配置是 **IQ4_XS + KV q4_0 + fa off**（SLIM-ARC 无 FA），不是真正的 upstream baseline。**语义上把 SLIM-ARC 无 FA 当作 baseline**，不严谨。

#### 问题 13: ROADMAP 不是最新

ROADMAP 最新条目日期是 2026-06-25，但当前是 2026-06-26。06-26 的论文修复（commit db79afe）未在 ROADMAP 记录。

#### 问题 14: fig_performance_landscape panel (c) 数据无溯源

generate_figures_v2.py:115 写 `32GB IQ4_XS pp32=2.64 tg8=2.45`，但 logs/ablation/raw-80b/ 下无 32GB IQ4_XS pp32/tg8 的对应日志。80b-iq4xs-16g-summary.txt 提到 32GB 但未给 pp32/tg8 具体值。

### ✅ 改进确认

- 论文数据层面修复到位（tab:ablation_single、32GB baseline、prefill 67%、decode 437-850%）
- KV eviction 真集成到 graph_compute（SLIM_ARC_KV_EVICT 开关）
- 动态 MADV 切换真集成（SLIM_ARC_DYNAMIC_MADV 开关）
- GSM8K 精度数据完全可溯源
- 80B 核心数据完全可溯源
- 环境脚本 setup-cgroups.sh 已补全
- 集成脚本 apply-slim-arc.py 存在（虽有细节差异）
- 核心实验脚本 run-core-experiments.sh 存在且可复现
- 负面结果诚实记录（IQ4_XS 崩溃、spec decoding 失败、FA-eviction 冲突）
- phase2c 设计文档已补全

---

## 三、各维度状态总结

| 维度 | 状态 | 关键问题 |
|------|------|---------|
| 论文数据 | ✅ 修复到位 | 仅 MADV -41% 计算方向错误 |
| 代码实现 | ✅ 完整集成 | KV eviction 已真集成（raw_analysis 说过时） |
| Patches | ✅ 与 src 基本一致 | apply 脚本缺 register_mmap_region |
| Scripts | ✅ 完整 | tests/ 缺 3 个文件；scripts/profile/src/ 残留 |
| README | 🔴 严重过时 | 仍写 FlexInfer 叙事，快速开始命令无法执行 |
| AGENT.md | 🔴 严重过时 | 仍写 FlexInfer 生态、A3B 模型 |
| config | 🔴 严重过时 | 写 A3B + wikitext/hellaswag（不存在） |
| docs/design | 🔴 严重过时 | architecture.md 仍 FlexInfer 叙事 |
| raw_analysis | ⚠️ 与论文/代码不一致 | 仍写"未集成"、"-57%"、6GB 无溯源数据 |
| logs | ✅ 完整 | 80B 全档有原始日志；6GB/长上下文无日志 |
| .gitignore | ✅ 合理 | src/llama-upstream 被 ignore 但通过 patches 恢复（符合 AGENT.md 设计） |
| ROADMAP | ⚠️ 未更新 | 缺 06-26 修复记录 |
| tests | ⚠️ 缺失 | 3 个测试文件不存在 |
| LICENSE | ✅ Apache 2.0 | 与 README:149 一致 |

---

## 四、改进建议（按优先级）

### P0 必须修复（影响评委第一印象）

1. **重写 README.md**: 从 FlexInfer 叙事改为 upstream llama.cpp + mmap + madvise 叙事；模型表加 80B + OLMoE；快速开始改为实际可执行的命令（apply-slim-arc.py + run-core-experiments.sh）

2. **重写 AGENT.md**: 技术栈改为 llama.cpp；模型改为 80B + OLMoE + Qwen3-4B；Baseline 改为 upstream llama.cpp；删除 FlexInfer 相关描述

3. **重写 docs/design/architecture.md**: 从 FlexInfer 三层架构改为论文 03_core_design.tex 的三层架构（内核协同 + 运行时调度 + 量化优化）；删除 FlexInfer/DUAL-BLADE/MobileMoE 标注

4. **更新 config/slim-arc.toml**: 模型改为 80B（45GB）+ OLMoE + Qwen3-4B；删除不存在的 wikitext/hellaswag/c4 benchmarks；加 gsm8k

### P1 应该修复（影响数据可信度）

5. **修正 MADV 贡献百分比**: 论文 -41% 改为 -29%（或明确表述为"Full 相对 no-MADV 提升 41%"）

6. **同步 raw_analysis 报告**: phase4-ablation-summary 和 project-progress-summary 的模块完成度标记改为与代码一致（KV eviction 已集成）；prefill -57% 改为 -67%；删除 6GB 和长上下文无溯源数据

7. **清理旧报告**: defense-data-summary.md 和 optimization-attribution-analysis.md 标注"已过时，以论文为准"或删除

8. **修复 apply-slim-arc.py**: 补上 register_mmap_region 调用，确保重新应用能恢复完整功能

9. **更新 ROADMAP**: 加 2026-06-26 修复记录（commit db79afe 的内容）

### P2 锦上添花

10. **补 tests/ 缺失文件**: 或更新 tests/README.md 删除不存在的测试引用

11. **清理 scripts/profile/src/**: 删除残留的旧 flexinfer/llama-upstream 副本

12. **补 32GB 真正 upstream baseline**: 或在论文明确标注"32GB baseline 用 SLIM-ARC 无 FA 替代"

13. **补 fig_performance_landscape panel (c) 32GB IQ4_XS 数据溯源**: 或标注为估算

14. **补 6GB 和长上下文原始日志**: 或从 raw_analysis 删除这些声明

---

## 五、结论

经过两轮修复，SLIM-ARC 项目的**论文数据层面已达到比赛正式材料可信度**——80B 核心数据完全可溯源，GSM8K 精度数据完全可溯源，负面结果诚实记录，数据拼接问题已修复。

**但文档层面严重滞后**：README、AGENT.md、docs/design/architecture.md、config/slim-arc.toml 仍停留在"基于 FlexInfer"的旧叙事，与论文和代码实际（upstream llama.cpp + mmap + madvise + 80B + OLMoE）严重脱节。这是当前最大的问题——**评委看 README 会以为项目基于 FlexInfer，看论文发现是 llama.cpp，看 raw_analysis 发现模块"未集成"，看代码发现已集成**，多个文档互相矛盾。

**根本原因**: 项目经历了从"基于 FlexInfer"到"基于 upstream llama.cpp"的路线变更（plan/04-v2），但顶层文档（README、AGENT.md、architecture.md）未同步更新。论文和代码已对齐，但外围文档未对齐。

**建议**: P0 的 4 项文档重写是当前最紧急的工作。修复后，项目在数据、代码、文档三个层面将完全一致，可达到比赛正式材料的标准。

---

## 附: 审计证据索引

| 证据 | 路径 |
|------|------|
| 论文（修复后） | [`reports/Competition_Report/sections/`](../../reports/Competition_Report/sections/) |
| 代码（KV eviction 已集成） | [`src/llama-upstream/src/llama-context.cpp:2551`](../../src/llama-upstream/src/llama-context.cpp) |
| apply 脚本（缺 register_mmap_region） | [`scripts/apply-slim-arc.py:86`](../../scripts/apply-slim-arc.py) |
| README（FlexInfer 旧叙事） | [`README.md:13,76-86`](../../README.md) |
| AGENT.md（过时） | [`AGENT.md:19-59`](../../AGENT.md) |
| architecture.md（FlexInfer 旧叙事） | [`docs/design/architecture.md:14-45`](../../docs/design/architecture.md) |
| config（A3B + 不存在 benchmarks） | [`config/slim-arc.toml:26-42`](../../config/slim-arc.toml) |
| raw_analysis（与代码不一致） | [`reports/raw_analysis/phase4-ablation-summary.md:109-112`](../../reports/raw_analysis/phase4-ablation-summary.md) |
| project-progress（无溯源 6GB） | [`reports/raw_analysis/project-progress-summary.md:99`](../../reports/raw_analysis/project-progress-summary.md) |
| tests/README（引用不存在文件） | [`tests/README.md:7-10`](../../tests/README.md) |
| .gitignore（src 被 ignore） | [`.gitignore:267-268,277`](../../.gitignore) |
| 首次审计 | [`plan/audit/00-v1-completion-audit.md`](00-v1-completion-audit.md) |
| 第二次审计 | [`plan/audit/01-v1-paper-data-audit.md`](01-v1-paper-data-audit.md) |
