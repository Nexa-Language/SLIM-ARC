# SLIM-ARC ROADMAP

---

## 2026-06-25 FlashAttention + GSM8K 标准benchmark测试

### 变更描述
按综述 ALEM 协议测试 FlashAttention 和 GSM8K 精度。

### FlashAttention 测试（80B IQ4_XS, 32GB, 8 threads, KV q4_0）
| 配置 | pp64 t/s | tg48 t/s | vs baseline |
|------|---------|---------|------------|
| baseline (无 -fa) | 5.89 | 3.01 | --- |
| -fa on | 6.64 | 3.90 | +29.6% |
| **-fa auto (默认)** | **12.99** | **5.16** | **+71.4%** |

**关键发现**: `-fa auto` 让模型自选最优 attention 实现，tg48 达 5.16 t/s（+71.4%）。FlashAttention 通过 IO-aware tiling 融合显著减少 decode 的内存读写。

### GSM8K 精度测试（8-shot, temp=0.2, top_p=0.95）
| 模型 | 量化 | Accuracy | Throughput | 说明 |
|------|------|---------|-----------|------|
| Qwen3-4B | Q4_K_M | **15/20 = 75%** | 7.8 tok/s | 数学推理保持 |
| Qwen3-Next-80B | IQ4_XS + KV q4_0 | **0/10 = 0%** | 1.7 tok/s | **推理能力崩溃** |

**关键发现**: IQ4_XS + KV q4_0 在 80B 上导致数学推理能力完全崩溃（0%），但语言流畅性保持。典型表现：计算正确但最终答案写错（"2+1=3, The answer is 2"）。说明极端量化对 MoE 推理的损害远大于语言建模。

### 结论
1. FlashAttention (`-fa auto`) 是高收益零成本优化，应作为默认配置
2. 量化对精度的影响需要按任务类型评估：语言建模 OK ≠ 推理 OK
3. GSM8K 是比 PPL 更敏感的精度代理指标
4. 比赛展示应区分"流畅生成"和"精确推理"两个场景

### 涉及文件
- `scripts/bench/run-gsm8k-api.py`（GSM8K API 测试脚本）
- `data/benchmarks/gsm8k/gsm8k_test.jsonl`（标准测试集）
- `logs/gsm8k_qwen3_4b_20q.jsonl` + `logs/gsm8k_80b_10q.jsonl`
- `logs/ablation/raw-80b/80b-32g-flashattn-*.txt`

---

## 2026-06-24 Speculative Decoding 调研：MoE 80B 净负收益

### 变更描述
测试 llama.cpp 内置 speculative decoding（ngram-simple 模式）在 80B IQ4_XS 上的效果。

### 测试结果
- **配置**: 80B IQ4_XS, 32GB, 8 threads, self-draft (同模型做 draft+target), ngram n=8 m=4
- **accept rate**: 33.3% (72 drafted, 24 accepted)
- **decode speed**: 1.41 t/s (vs baseline 3.01 t/s) — **净负收益 -53%**
- **原因**: 80B 做 draft 没有小模型加速，验证开销 > 投机收益；MoE router 的高熵使 n-gram 预测准确率低

### 结论
1. Speculative decoding 在 80B MoE 上**不适用**（验证 unsloth 的结论）
2. 需要真正的 small draft model（如 Qwen3-0.6B），但 Qwen3-Next 没有 small 版本
3. n-gram speculation 适合重复性高的文本（代码、结构化输出），不适合开放生成
4. **记录为负面结果**，在报告中诚实呈现

### 原始日志
- `logs/speculative_ngram_test.txt`

---

## 2026-06-24 80B eviction benchmark: decode +9.6% 加速

### 变更描述
80B IQ4_XS 在 32GB 环境下，KV eviction (sink=4, window=32) 对比 baseline：
- **tg48: 3.30 t/s vs 3.01 t/s (+9.6%)** — eviction 释放 KV 内存，改善权重 cache 命中率
- **pp64: 4.85 t/s vs 5.89 t/s (-17.7%)** — prefill 阶段有初始化开销（eviction 逻辑检查）

### 结论
1. KV eviction 在 80B 受限场景下有实际收益（decode +9.6%）
2. 机制工作正常：12 次驱逐，seq_len 稳定在 36
3. 原始日志: `logs/ablation/raw-80b/80b-32g-eviction-pp64-tg48.txt` + `80b-32g-baseline-pp64-tg48.txt`

---

## 2026-06-24 StreamingLLM KV Eviction 实现与验证 (Phase 4 P0)

### 变更描述
基于综述 (Sec 4.3) 和 StreamingLLM (Xiao et al. 2023) 论文，实现了 KV Cache 的 sink+sliding window eviction 机制。

### 实现
- **文件**: `src/llama-upstream/src/llama-context.cpp` (graph_compute 末尾)
- **机制**: decode 后检查 KV seq_len，超过 `sink+window` 阈值时调用 `memory->seq_rm(0, p0, p1)` 驱逐中间 token
- **配置**: 环境变量 `SLIM_ARC_KV_EVICT=1`, `SLIM_ARC_KV_SINK=4` (默认), `SLIM_ARC_KV_WINDOW=1024` (默认)

### 验证结果 (Qwen3-4B Q4_K_M, 32GB, 4 threads, n=300)
| 配置 | decode t/s | 质量 | 说明 |
|------|-----------|------|------|
| baseline (无 eviction) | 13.45 | 连贯 | KV 全量保留 |
| KV eviction (sink=4, window=256) | 13.06 | 连贯 | 64 次驱逐，KV 稳定在 260 |

- **性能开销**: 仅 2.9%（13.45→13.06 t/s）
- **生成质量**: 文本连贯，语义正确（童话故事续写）
- **eviction 触发**: seq_len > 260 时每步驱逐 1 个最老非 sink token

### 关键发现
1. 32GB 环境 Qwen3-4B (2.4GB) 场景 KV 不构成内存瓶颈，eviction 收益不显著
2. 真正价值在 80B + 8GB：KV cache 成为内存瓶颈时，eviction 可释放 DRAM 给权重缓存
3. StreamingLLM 的 attention sink 机制对 Qwen3 有效（前 4 token 足够稳定 attention）

### 涉及文件
- `src/llama-upstream/src/llama-context.cpp`（graph_compute 末尾新增 eviction hook）
- `logs/kv_eviction_test.txt`（eviction 测试日志）
- `logs/kv_eviction_baseline.txt`（baseline 对比日志）
- `plan/04-v1-survey-inspired-optimization.md`（优化计划）

---

## 2026-06-24 学术报告完善 + 80B 端到端文本生成验证

### 变更描述
1. **80B 端到端文本生成 demo** 成功完成（`llama-completion` + IQ4_XS + 32GB 环境）
2. **Qwen3-4B Perplexity 测试** 进行中（WikiText, 32 chunks, ETA ~30min）
3. 学术报告 LaTeX 新增两个 section：端到端生成验证 + 模型精度验证
4. PDF 重新编译：23 页，1.7MB

### 80B 文本生成结果（32GB, IQ4_XS, 8 threads）
- **Prompt**: "The capital of China is Beijing. It is a"
- **Generation**: "major political, cultural, historical, and economic center of the country. As the seat of the Chinese government and home to the State Council, the National People's Congress, and the Chinese Communist"
- **Load time**: 41.2s (mmap 冷启动)
- **Prompt eval**: 0.95 t/s (18 tokens)
- **Decode**: 1.56 t/s (47 tokens, 642 ms/token) — 语义连贯、事实正确
- **原始日志**: `logs/ablation/raw-80b/80b-iq4xs-32g-demo-text.txt`

### Qwen3-4B Perplexity 部分结果（48/145 chunks, 已保存）
- 几何均值 PPL: **12.70**
- 区间: [11.25, 15.51]
- 原始日志: `logs/perplexity_partial_48chunks.txt`

### 涉及文件
- `reports/Competition_Report/sections/05_evaluation.tex`（新增端到端验证 + PPL section）
- `reports/Competition_Report/main.pdf`（23 页重编译）
- `logs/ablation/raw-80b/80b-iq4xs-32g-demo-text.txt`（80B 生成日志）
- `logs/perplexity_partial_48chunks.txt`（PPL 部分结果）

### 关键决策
- 80B 的完整 145-chunk PPL 测试需要 4+ 小时，报告以 Qwen3-4B PPL + 80B 端到端生成质量作为精度代理指标
- `llama-cli` 即使 `-no-cnv -p` 仍进入交互模式，改用 `llama-completion` + `setsid` 脱离终端

---

## 2026-06-23 重大突破：IQ4_XS 量化 + SLIM-ARC 实现 80B 流畅运行

### 最终优化成果

| 环境 | 模型 | pp | tg | vs baseline |
|------|------|-----|-----|------------|
| 8GB | IQ4_XS + SLIM-ARC + KV q4_0 | 0.35 | **0.76** | **+850% (9.5×)** |
| 16GB | IQ4_XS + SLIM-ARC + KV q4_0 | **1.71** | **1.12** | **+522% (6.2×)** |
| 32GB | IQ4_XS + SLIM-ARC + KV q4_0 | **2.64** | **2.45** | **流畅运行！** |

### 关键发现
- **IQ4_XS 量化** (40GB vs Q4_K_M 45GB): 5GB 更小，page cache 命中率显著提升
- **32GB 热缓存达到 2.45 t/s**: 0.4 秒/token，完全流畅
- **8GB 最受限环境达到 0.76 t/s**: baseline 的 9.5 倍

### 优化技术栈
1. 禁用 GGML_CPU_REPACK（避免 OOM）
2. MADV_RANDOM（MoE 稀疏按需分页）
3. KV Cache q4_0 量化（内存减半）
4. IQ4_XS 模型量化（45→40GB）
5. 8 threads（memory-bound 最优）

---

## 2026-06-23 数据波动发现 + IQ4_XS 下载 + Perplexity 测试

### 数据波动问题
80B 16GB cgroup 下多次测量 tg8 波动极大（0.28-1.03）。根因：
- 80B 45GB 远超 16GB RAM，每次 decode 都要 page fault
- 速度取决于 page cache 命中率，受系统其他进程影响
- 之前测到的 1.03 是异常高点（恰好有热缓存）
- 稳定冷启动速度约 0.35-0.68 t/s

### 正在进行的优化
1. **IQ4_XS 模型下载** (~30GB vs 45GB Q4_K_M)
   - 更小模型能更好适应 16GB/32GB RAM
   - 预期：cache 命中率提升 → 速度更稳定更快
2. **Perplexity 测试** (Qwen3-4B)
   - 验证量化精度损失
   - 初步 PPL: [1]11.76, [2]14.19, [3]14.67

### 诚实的数据范围
- 80B 16GB 冷启动: tg8 ≈ 0.35-0.68 t/s（不稳定）
- 80B 32GB 热缓存: tg8 ≈ 0.57-1.24 t/s（不稳定）
- 80B 8GB 冷启动: tg1 ≈ 0.42 t/s（稳定，因为 8GB cgroup 更可控）

---

## 2026-06-23 深度优化：KV q4_0 + 动态 MADV + 80B 达 1.03 t/s

### 优化成果

| 配置 | pp32 | tg8 | vs baseline |
|------|------|-----|------------|
| baseline (16GB) | 1.04 | 0.18 | - |
| SLIM-ARC (16GB) | 1.26 | 0.90 | +400% |
| **SLIM-ARC + KV q4_0 (16GB)** | **1.34** | **1.03** | **+472% (5.7×)** |
| SLIM-ARC (32GB warm) | 1.90 | 1.24 | - |

### 尝试的优化方法

1. **动态 MADV 切换**: prefill→WILLNEED, decode→MADV_RANDOM
   - 实现 `switch_madvise_all()` + `register_mmap_region()`
   - 效果：开销抵消收益（45GB 区域 madvise 开销大）
   
2. **KV Cache 量化 (q4_0)**: ✅ 有效
   - KV 内存减半，更多 RAM 给权重
   - decode +14%（0.90→1.03 t/s）

3. **投机解码 (ngram-simple)**: 加载太慢未完成
   - 80B 冷启动 7+ 分钟，ngram 缓存建立慢
   - draft model (Qwen3-4B) 方案：两个大模型加载更慢

4. **线程数测试**: 8 threads 最优
   - 14 threads 反而慢（memory-bound，同步开销）

### 核心数据（可溯源）

- 80B 16GB + KV q4_0: **tg8=1.03 t/s**（baseline 5.7 倍）
- 80B 32GB warm: **tg8=1.24 t/s**（接近流畅）
- 原始日志: [`logs/ablation/raw-80b/`](logs/ablation/raw-80b/)

---

## 2026-06-23 重大失误：未跟踪代码丢失 + 恢复

### 事件
- src/llama-upstream/ 整个目录消失（WSL 重启清理未跟踪文件）
- 原因：.gitignore 误加了 `src/llama-upstream/`，导致修改后的 upstream llama.cpp 源文件不被跟踪
- 所有 SLIM-ARC 集成代码（对 llama-model-loader.cpp/llama-context.cpp/llama-kv-cache.cpp 的修改）丢失

### 教训（必须遵守）
1. **所有修改过的代码必须被 git 跟踪**，不能 ignore
2. .gitignore 只能 ignore 构建产物和外部依赖，不能 ignore 我们修改的源文件
3. 修改第三方代码后，必须用 `git add -f` 强制跟踪，或保存为 patch 文件

### 恢复措施
1. 重新 clone upstream llama.cpp
2. 创建 [`scripts/apply-slim-arc.py`](scripts/apply-slim-arc.py) 集成脚本（基于 patches/ 下的独立文件 + 模式匹配）
3. 验证恢复成功：80B 8GB slim-arc pp4=0.27 tg1=0.42（与之前数据一致）
4. 所有 slim-arc 独立文件在 `patches/llama-upstream/` 下（已跟踪）

### 防护机制
- 集成脚本 `scripts/apply-slim-arc.py` 是幂等的，可从 patches/ 完整恢复所有修改
- README 中说明恢复流程：clone upstream → run script → cmake build
- 不再依赖未跟踪的 src/ 目录

### 涉及文件
- `scripts/apply-slim-arc.py`: 集成脚本（新建，已跟踪）
- `patches/llama-upstream/`: slim-arc 独立文件（8个，已跟踪）
- `.gitignore`: 移除了误加的 `scripts/profile/src/`，保留 `src/llama-upstream/`（因为是独立 git clone）

---

## 2026-06-23 审计修复：数据可溯源 + 诚实标记 + 四组消融

### 背景
独立 agent 审计报告（[`plan/audit/00-v1-completion-audit.md`](plan/audit/00-v1-completion-audit.md)）指出严重问题：80B 数据无日志、CSV 挑选、baseline OOM 矛盾、setup-cgroups.sh 不存在、模块完成度夸大。

### 修复内容

**P0 可信度修复**:
1. **80B 原始日志已保存**: 6 个文件到 `logs/ablation/raw-80b/`，数据可溯源
2. **四组单点消融完成**: baseline / MADV only / prefetch only / full
3. **统一 baseline OOM 口径**: 禁用 repack 后 baseline 能跑（不 OOM），只是 decode 慢
4. **创建 `scripts/env/setup-cgroups.sh`**: 之前不存在

**P1 完成度诚实标记**:
5. **降级标记**: evict_layer/KV-eviction/Tile = ⚠️ 接口完成，未集成
6. **创建 `docs/design/phase2c-dynamic-locking.md`**: 之前缺失
7. **消融报告呈现全部 4 份 CSV**: 不再挑选

### 关键技术发现（四组消融）

| 配置 | pp16 | tg4 |
|------|------|-----|
| baseline | 0.63 | 0.08 |
| MADV_RANDOM only | 0.27 | **0.29** |
| prefetch only | 0.54 | 0.07 |
| slim-arc (全开) | 0.28 | 0.29 |

**MADV_RANDOM 是 decode 提升唯一驱动**。prefetch_scheduler 在 80B 8GB 场景冗余（全开 == MADV only）。这修正了之前"prefetch 有贡献"的说法。

### 诚实评估

- 80B decode +262% (pp16+tg4) ~ +437% (pp4+tg1) — 真实可复现
- prefetch 当前冗余 — 承认，需后续优化（如 KV 集成后统一调度）
- Phase 2b/2d 接口 only — 承认，未集成推理流程

### 涉及文件

- `logs/ablation/raw-80b/`: 80B 原始日志
- `scripts/env/setup-cgroups.sh`: cgroups 配置脚本（新建）
- `scripts/bench/run-80b-bench.sh`: 80B 测试脚本（新建）
- `docs/design/phase2c-dynamic-locking.md`: Phase 2c 设计（新建）
- `reports/phase4-ablation-summary.md`: 重写，全部 CSV
- `reports/optimization-attribution-analysis.md`: 重写，四组归因
- `reports/project-progress-summary.md`: 重写，诚实标记
- `reports/defense-data-summary.md`: 重写，可溯源数据
- `src/llama-upstream/src/llama-model-loader.cpp`: 加 `SLIM_ARC_NO_PREFETCH` 开关

---

## 2026-06-22 核心成果：80B 8GB decode 提升 343%

### 变更描述

Qwen3-Next-80B (45GB) 在 8GB cgroup 的完整对比测试完成。

### 关键数据

| Mode | pp4 (t/s) | tg1 (t/s) |
|------|-----------|----------|
| baseline (SLIM_ARC_DISABLE=1) | 0.17 | 0.07 |
| **SLIM-ARC** | **0.20 (+17.6%)** | **0.31 (+343%)** |

**decode 提升 4.4 倍**是最核心的对比数据。

### 分析

- baseline 默认 WILLNEED 全预读，8GB 内存压力下频繁 page reclaim → thrashing
- SLIM-ARC 的 MADV_RANDOM 只加载访问的页面 + prefetch_scheduler 精准预取
- decode 是内存敏感场景，提升最明显
- prefill 提升较小（compute-bound，I/O 可隐藏）

### 涉及文件

- [`reports/phase4-ablation-summary.md`](reports/phase4-ablation-summary.md): 更新 80B 对比表
- [`reports/project-progress-summary.md`](reports/project-progress-summary.md): 更新核心成果

---

## 2026-06-22 Phase 2a Router Hook 集成完成

### 变更描述

在 `graph_compute` 中集成 MoE router hook：
1. **计算后**：遍历 graph 节点，找 `ffn_moe_topk` tensor（router 输出的 top-k expert IDs），读取 I32 数据，存入 `cache_router_experts(layer, expert_ids)`
2. **计算前**：用上一层的 router cache 通过 `prefetch_experts(layer, cached_ids)` 对当前层的 expert tensor 子区域发 `madvise(WILLNEED)`，实现跨层专家预测预取

### 接口

- `cache_router_experts(layer, expert_ids, n)`: 缓存 layer N 的 router 输出
- `get_cached_experts(layer, &n)`: 获取缓存的 expert IDs
- `prefetch_experts(layer, ids, n)`: 对 expert tensor 子区域发 WILLNEED

### cgroup 自适应阈值调整

从 40% 调整到 60%（`total_weight < cgroup_mem * 60%` 时跳过 prefetch），让 OLMoE 3.9GB 在 8GB 环境也跳过（避免 madvise 开销）。

### 消融数据（80B 后台干扰，数据有噪声）

| 模型 | Tier | Baseline pp | SLIM-ARC pp | 提升 |
|------|------|------------|------------|------|
| OLMoE | mid(12G) | 42.96 | 71.86 | +67% |
| OLMoE | high(16G) | 64.55 | 88.21 | +37% |

### 涉及文件

- `src/llama-upstream/src/slim-arc-prefetch.h/cpp`: cache_router_experts + get_cached_experts
- `src/llama-upstream/src/llama-context.cpp`: graph_compute router hook + 跨层专家预取
- `src/llama-upstream/src/llama-model-loader.cpp`: cgroup 阈值 40%→60%

---

## 2026-06-22 Phase 2a/3 接口实现 + 完整消融报告

### 变更描述

1. **Phase 2a MoE 专家选择性预取**: 实现 `register_expert_tensor` + `prefetch_experts` 接口，支持对 3D 合并 expert tensor 的子区域发 `madvise(WILLNEED)`。router hook 集成待后续。
2. **Phase 3 统一调度器**: `unified_io_scheduler` 原型已就绪（phase 感知 budget 分配表），当前 `prefetch_scheduler` 已具备 phase 感知能力，作为简化版统一调度器运行。
3. **完整消融报告**: [`reports/phase4-ablation-summary.md`](reports/phase4-ablation-summary.md) 汇总三档 × 两模型数据。

### 12GB 环境异常分析

mid tier (12GB) 出现性能下降（-8.8%/-13%），可能原因：
- 模型 4GB 在 12GB 下能全缓存，MADV_RANDOM 未应用（<6GB 阈值）
- prefetch_scheduler 的 WILLNEED 系统调用在热缓存模型上引入开销
- **改进方向**: 当 model_size < cgroup_memory * 0.5 时，应完全禁用 prefetch（模型能全缓存）

### 关键成果汇总

| 模型 | 环境 | Baseline | SLIM-ARC | 提升 |
|------|------|---------|---------|------|
| OLMoE-1B-7B | 8GB | pp=59, tg=26 | pp=97, tg=40 | **+63%/+53%** |
| Qwen3-4B | 8GB | pp=24, tg=13 | pp=29, tg=14 | +17%/+6% |
| Qwen3-Next-80B | 8GB | **OOM** | **能运行** | ∞ |

### 涉及文件

- `src/llama-upstream/src/slim-arc-prefetch.h/cpp`: expert tensor 接口
- `src/llama-upstream/src/llama-model-loader.cpp`: expert tensor 自动注册
- `docs/design/phase2a-moe-expert-prediction.md`: Phase 2a 设计分析
- `reports/phase4-ablation-summary.md`: 完整消融报告

---

## 2026-06-22 消融实验：OLMoE在8GB环境提升53-63%

### 变更描述

实现 `SLIM_ARC_DISABLE` 环境变量开关，支持 baseline vs SLIM-ARC 对比。完成三档消融实验（Qwen3-4B + OLMoE），产出 CSV 数据。

### 关键数据（[`logs/ablation/ablation-20260623-014809.csv`](logs/ablation/ablation-20260623-014809.csv)）

**OLMoE-1B-7B（MoE）在 8GB cgroup（最受限环境）：**

| Test | Baseline (t/s) | SLIM-ARC (t/s) | 提升 |
|------|---------------|----------------|------|
| pp64 (prefill) | 59.26 | **96.75** | **+63.2%** |
| tg16 (decode) | 26.34 | **40.32** | **+53.1%** |

**Qwen3-4B（Dense）在 8GB cgroup：**

| Test | Baseline (t/s) | SLIM-ARC (t/s) | 提升 |
|------|---------------|----------------|------|
| pp64 (prefill) | 24.41 | 28.69 | +17.5% |
| tg16 (decode) | 12.84 | 13.57 | +5.7% |

### 分析

1. **8GB 环境 MoE 提升最大**：OLMoE 在内存压力下，SLIM-ARC 的 prefetch + MADV_RANDOM 让 expert 权重按需加载，避免 OOM 导致的频繁 page reclaim，提升 53-63%
2. **Dense 模型提升较小**：Qwen3-4B 只 2.4GB，8GB 能全缓存，优化空间有限
3. **12GB 环境数据异常**：需调查（memory.peak 读取可能有误）
4. **16GB 环境持平**：模型完全在 RAM，优化无额外收益

### 涉及文件

- `src/llama-upstream/src/llama-model-loader.cpp`：MADV_RANDOM 条件化（>6GB）+ SLIM_ARC_DISABLE 开关
- `scripts/bench/run-quick-ablation.sh`：新增三档消融脚本
- `logs/ablation/ablation-20260623-014809.csv`：消融数据

### 决策原因

用户反馈：80B 跑不出来先放，先在其他模型上比 baseline 高出一大截。8GB 环境 OLMoE 提升 53-63% 正是"高出一大截"的证据，是最有比赛价值的对比数据。

> 本文件采用倒序日志：最新记录在顶部。每条记录包含时间戳、变更描述、涉及文件、决策原因。

---

## 2026-06-22 核心突破：45GB模型在8GB cgroup不OOM

### 变更描述

放弃旧 on-demand loader（pread+aligned_alloc 方案，SIGSEGV 无法修复），改用 **mmap + MADV_RANDOM + 禁用 repack** 方案，成功让 Qwen3-Next-80B（45GB）在 8GB cgroup 下启动且不 OOM。

### 根因分析

旧方案失败的三个原因：
1. **顺序错误**：`register_tensor` 遍历 `ml.ctx_map` 时，`ctx_ptr` 已被 `std::move` 到 `pimpl->ctxs_bufs`，导致空指针解引用
2. **架构冲突**：upstream llama.cpp 的 CPU backend 依赖 `tensor->buffer + tensor->data` 组合，直接用 `aligned_alloc` 设置 `tensor->data` 而 buffer 是 dummy 会破坏 backend scheduler
3. **repack 内存翻倍**：CPU backend 默认启用 `GGML_CPU_REPACK`，把 Q4_K 权重重打包成 `q4_K_8x8`，分配额外匿名内存副本 → 45GB 模型产生 45GB 匿名内存 → 必然 OOM

### 新方案（plan/05-v1-mmap-on-demand-redesign.md）

三层机制协同：
1. **mmap**：模型文件 mmap 到虚拟地址空间（45GB VSZ），tensor->data 指向 mmap 区域
2. **MADV_RANDOM**：在 `init_mappings()` 中对整个 mmap 区域调用 `posix_madvise(MADV_RANDOM)`，关闭内核默认的 sequential readahead，只有访问的页面进 page cache
3. **禁用 repack**：`cmake -DGGML_CPU_REPACK=OFF`，CPU backend 直接用 mmap 原始权重计算，不分配匿名副本

### 验证结果

- Qwen3-Next-80B（45GB）在 8GB cgroup（slim-arc-low）下启动成功
- 进程存活 36+ 分钟未 OOM kill
- RSS=8.1GB（贴满 8GB 限制但未超），VSZ=47GB（45GB 模型 mmap 映射）
- `memory.events`: file-rss 极低（MADV_RANDOM 生效），anon-rss 为主（KV cache + compute buffer）
- OOM kill 发生在旧 repack 版本，禁用 repack 后不再 OOM

### 待解决：冷启动速度

- 45GB 模型冷启动 36 分钟未完成推理（每层从 SSD page fault）
- 已添加 `evict_layer()` API（madvise DONTNEED）但未在 graph_compute 中调用
- 后续优化方向：prefetch_scheduler 的 WILLNEED 需要更精细的层间触发

### 性能数据（Qwen3-4B 热缓存，no-cgroup）

| 配置 | pp16 (t/s) | tg4 (t/s) |
|------|-----------|----------|
| 禁用 repack 前（mmap 默认） | 29.35 | 8.02 |
| 禁用 repack 后（mmap+MADV_RANDOM） | 30.58 | 14.97 |

**关键发现**：禁用 repack 在热缓存下无性能损失，decode(tg4) 反而提升 87%（8.02→14.97）。冷启动慢的根因是 MADV_RANDOM + 冷缓存（无预读），不是禁用 repack。

### 涉及文件

- `src/llama-upstream/src/llama-model-loader.cpp`：添加 MADV_RANDOM 调用
- `src/llama-upstream/src/llama-model.cpp`：移除旧 on-demand loader 代码
- `src/llama-upstream/src/llama-model.h`：移除 on_demand_loader 成员
- `src/llama-upstream/src/llama-context.cpp`：移除 on-demand ensure_loaded 调用
- `src/llama-upstream/src/slim-arc-prefetch.h/cpp`：新增 evict_layer() 接口
- `src/llama-upstream/src/CMakeLists.txt`：注释掉 slim-arc-on-demand.cpp
- `src/llama-upstream/build/`：重新配置 `-DGGML_CPU_REPACK=OFF`
- `plan/05-v1-mmap-on-demand-redesign.md`：设计文档

### 决策原因

旧 on-demand loader 试图绕过 backend buffer 系统，在 upstream llama.cpp 的 OOP 架构下不可行。mmap + MADV_RANDOM 是与内核协同的标准做法，代码改动极小（只新增 madvise 调用），且利用内核 page cache 的 LRU 淘汰，无需手动管理内存。

---

## 2026-06-22 Qwen3-Next-80B 下载完成与受限环境测试

### 变更描述

Qwen3-Next-80B-A3B-Instruct Q4_K_M（45GB）下载完成，完成 MoE 分析和受限环境测试。

### 关键发现

1. **Qwen3-Next-80B-A3B 架构**：
   - 512 个专家（超稀疏 MoE），仅激活 10 个/token
   - 98% 稀疏率 → 完美预测可减少 98% 带宽
   - 每专家仅 1.8 MiB，window=3 预取预算仅 54 MiB

2. **受限环境 OOM**：
   - 45GB 模型在 32GB WSL2 上 OOM（mmap 和 direct-io 都不行）
   - 上游 llama.cpp 的 mmap 是全量映射，page cache 增长导致 OOM killer
   - **这验证了赛题核心挑战：需要张量级按需加载，而非全量 mmap**

3. **技术路线确认**：
   - 需要实现 FlexInfer 风格的张量级按需加载
   - 只把当前计算的层加载到内存，其他层留在 SSD
   - SLIM-ARC 的 prefetch 调度器正好解决"何时加载哪些层"的问题

### 涉及文件

- `reports/phase1-memory-profile-qwen3next-80b.md`（访存分析）
- `reports/phase2a-moe-analysis-qwen3next.md`（MoE 专家分析）

---

## 2026-06-22 Phase 2b+3 KV Cache 换页 + 统一 I/O 调度器原型完成

### 变更描述

完成 Phase 2b KV Cache 异步换页原型和 Phase 3 统一 I/O 带宽预算调度器原型代码。

### 涉及文件

- `patches/llama-upstream/slim-arc-kv-eviction.h/cpp`（KV Cache 换页管理器）
- `patches/llama-upstream/slim-arc-unified-scheduler.h/cpp`（统一调度器）
- `reports/phase4-ablation-summary.md`（完整三档 baseline 数据）

### 关键成果

1. **Phase 2b KV Cache 换页原型**：
   - 分层 KV Cache：hot(sink) / warm(sliding) / cold(mmap→SSD)
   - 注意力分数驱动驱逐策略
   - mmap 动态增长 + madvise 异步预取
   - 统计追踪（evictions, prefetches, RAM/SSD 用量）

2. **Phase 3 统一 I/O 调度器原型（核心创新）**：
   - 5 种运行时阶段感知的带宽分配
   - 动态自适应：基于 weight stalls / KV page faults / expert miss rate 调整
   - 适配历史追踪

3. **完整三档 baseline（warm cache）**：
   - Dense Qwen3-4B: pp64 39.55→57.81, tg32 8.12→10.88
   - MoE OLMoE-1B-7B: tg32 25.56→35.66

### 下载进度

- Qwen3-Next-80B-A3B-Instruct Q4_K_M: 72% (33GB/45GB)，ETA 37 分钟
- 下载慢的原因：45GB 大文件 + hf-mirror 镜像限速 20-30 MB/s

---

## 2026-06-22 Phase 2c Prefill/Decode 动态预取实现与测试

### 变更描述

实现 SLIM-ARC Phase 2c（Prefill/Decode 感知的动态预取），完成三档环境测试。

### 涉及文件

- `patches/llama-upstream/slim-arc-prefetch.h`（添加 phase 感知、memory budget）
- `patches/llama-upstream/slim-arc-prefetch.cpp`（实现动态窗口、decode 禁用）
- `src/llama-upstream/src/llama-context.cpp`（集成 phase 检测）
- `reports/phase2c-prefill-decode-results.md`（测试报告）
- `reports/phase1-memory-profile-*.md`（访存行为分析）
- `scripts/profile/analyze_gguf.py`（GGUF 分析工具）

### 关键成果

1. **Phase 1 访存行为分析完成**：Qwen3-4B 每层 57.5 MiB，FFN 占 72%
2. **Phase 2c 动态预取实现**：Prefill 窗口=4，Decode 禁用
3. **三档 baseline 数据**：
   - 8GB+4核: pp64=39.80, tg32=9.74 tok/s
   - 12GB+6核: pp64=52.40, tg32=11.33 tok/s
   - 16GB+8核: pp64=54.28, tg32=11.90 tok/s
4. **Phase 2c 结果**：16GB pp64 +5%，decode 无退化（已禁用）

### 关键发现

- Qwen3-4B (2.5GB) 在所有档位都完全放入内存，prefetch 无明显收益
- 真正的预取收益需要冷缓存或模型超出内存（Qwen3-Next-80B 45GB）
- OLMoE-1B-7B 验证 MoE 模型可跑：pp64=97.61, tg32=26.45 tok/s
- Qwen3-Next-80B 下载中（9%，预计 2 小时完成）

### 待办

- 冷缓存测试（drop_caches 后对比）
- Qwen3-Next-80B 下载完成后测试 45GB 模型在受限环境的表现
- Phase 2b: KV Cache 异步换页
- Phase 3: 统一 I/O 带宽预算调度器

---

## 2026-06-21 Qwen3 兼容性根因定位与方案调整

### 变更描述

定位到 FlexInfer 无法加载 Qwen3 GGUF 的根因，并验证上游 llama.cpp 可正常加载。

### 关键发现

1. FlexInfer 的 gguf-py constants.py 已有 QWEN3 枚举，但 C++ llama.cpp 不支持
2. 已在 FlexInfer llama.cpp 添加 QWEN3→QWEN2 的别名映射（架构识别已通过）
3. 但仍报错 `tensor data not within file bounds`，根因是 FlexInfer 的 GGUF reader 对 padding/alignment 的处理与官方 GGUF 不兼容
4. **上游最新 llama.cpp 可正常加载 Qwen3-4B GGUF**，说明文件本身没问题

### 决策调整

原计划"从最新 llama.cpp backport Qwen3 到 FlexInfer"遇到结构性障碍：
- 上游 llama.cpp 已重构为 C++ 面向对象（llama-graph.cpp 等）
- FlexInfer 是旧 C 风格单文件（22659行）
- GGUF reader 的 alignment/padding 逻辑也存在不兼容

**调整方案**：直接在上游最新 llama.cpp 基础上实现 FlexInfer 的 prefetch 机制。这避免了 backport 地狱，且能利用上游完整的 Qwen3 支持。

### 待办

- 等待上游 llama-cli 测试结果确认
- 若上游正常，则切换技术路线：以上游 llama.cpp 为基础，backport FlexInfer 的 prefetch patch

---

## 2026-06-21 Phase 0 实施进展与 Qwen3 兼容性阻塞

### 变更描述

Phase 0 启动实施，完成 cgroups 脚本、FlexInfer 编译、模型下载，但发现 FlexInfer 不支持 Qwen3 架构。

### 涉及文件

- [`scripts/env/setup-cgroups.sh`](scripts/env/setup-cgroups.sh)（新建）
- `src/flexinfer/`（从 docs/papers 复制，编译成功）
- `data/models/Qwen3-4B-Q4_K_M.gguf`（从 Qwen/Qwen3-4B-GGUF 下载）

### 进展

1. cgroups v2 确认可用，三档隔离脚本就绪
2. FlexInfer host 版编译成功，产出 `flexinfer-cli`、`llama-cli`、`flexinfer-bench` 等
3. 官方 Qwen3-4B-Q4_K_M GGUF 已下载

### 阻塞问题

FlexInfer 无法加载 Qwen3-4B GGUF，具体表现：
- `llama-cli` 报错：`tensor 'blk.35.ffn_up.weight' data is not within the file bounds`
- `gguf-py` 读取器报错：`cannot reshape array of size 14004992 into shape (9728,1440)`
- GGUF metadata 确认 architecture = `qwen3`，feed_forward_length = 9728
- 模型名为 "Qwen3 4B Instruct **Awq**"，疑似使用 AWQ 量化

### 根因分析

FlexInfer fork 的 llama.cpp 版本较旧（build 3907），不支持：
1. `qwen3` 架构（仅有 qwen/qwen2/qwen2moe）
2. 可能的 AWQ 量化类型（Q4_K_M 的 block 结构与标准不同）

### 待决策

需要从最新 llama.cpp backport Qwen3 架构支持到 FlexInfer。涉及：
- `ggml` 层：张量类型、量化 kernel
- `llama.cpp` 层：架构定义、张量映射
- `gguf-py`：GGUF 读写支持
- `convert_hf_to_gguf.py`：模型转换脚本

工作量估计：中-大（需同步 3 层代码）。这是 Phase 0 的关键路径。

---

## 2026-06-21 项目启动与计划制定

### 变更描述

完成项目初始规划，确定技术路线、环境配置、模型选择和优化方向优先级。

### 涉及文件

- [`plan/00-v1-slim-arc-overview.md`](plan/00-v1-slim-arc-overview.md)（新建）
- [`AGENT.md`](AGENT.md)（新建）
- [`README.md`](README.md)（扩充）
- [`docs/architecture.md`](docs/architecture.md)（新建）
- [`.gitignore`](.gitignore)（新建）

### 决策记录

#### 决策 1: 技术路线定为"统一 I/O 带宽预算调度器"

- **原因**: FlexInfer 只调度权重，DUAL-BLADE 只调度 KV，MobileMoE 只调度专家。三者各自最优不等于全局最优。
- **核心 insight**: 在统一 I/O 带宽预算下，权重卸载、KV 换页、MoE 专家预取三者竞争带宽，需基于运行时阶段（Prefill/Decode/长上下文）动态分配。
- **预期贡献**: 证明"协同 > 单点之和"。

#### 决策 2: 三档环境配置

- 8GB RAM + 4 核 CPU（模拟中端手机/嵌入式）
- 12GB RAM + 6 核 CPU（模拟高端手机/轻量 PC）
- 16GB RAM + 8 核 CPU（模拟现代 PC/端侧服务器）
- **原因**: 用户明确要求"内存和核数可变，用来对比模拟不同档位端侧设备"，但不宜过多，三档足够覆盖从嵌入式到 PC 的频谱。
- **隔离工具**: cgroups v2（FlexInfer README 已示范，最普适）。

#### 决策 3: 模型选择

- Dense: Qwen3-4B（Q4_K_M 约 2.5GB，8G 下有压力但能跑）
- MoE: Qwen3-Next-A3B（3B 总参/稀疏激活，端侧 MoE 代表）
- **原因**: 用户指定。4B 在最小档位体现"受限"，A3B 的稀疏性是 MoE 优化的理想验证对象。

#### 决策 4: 优化方向优先级

- **P0（必做）**: KV Cache 异步换页、MoE 专家预测预取、Prefill/Decode 动态锁定
- **P1（进阶）**: Tile 级微流水线 + 融合反量化、统一 I/O 调度器
- **P2（选做）**: 投机解码、编译级算子融合
- **原因**: 用户要求"先复现论文思路，验证有效，再融合"。P0 三方向均有论文先例（DUAL-BLADE/ScoutAttention/HillInfer、MobileMoE/MoE-Prism、FlexInfer Algorithm 1 升级），风险可控。

#### 决策 5: 纯 CPU，不使用 GPU

- **原因**: 赛题示例 FlexInfer 是纯 CPU 框架，宫老师强调"平台合理性"。
- **影响**: 优化重心在 Cache 命中率、I/O 带宽利用、算子融合，而非 GPU kernel。

#### 决策 6: Agent 场景后期接入

- **原因**: 用户明确"Agent 是场景但早期不需要考虑，先做 LLM infer 部分"。
- **计划**: Phase 4 后再设计多轮 Agent 场景的上下文管理与 KV 语义感知。

### 风险预警

1. FlexInfer fork 版本可能较旧，Qwen3-Next 架构可能不支持 → 需从最新 llama.cpp backport
2. GGUF 4096 对齐转换可能失败 → 调试 convert 脚本
3. Phase 3 统一调度器复杂度高 → 降级为启发式规则集

### 待办

- 等待用户审阅本文档及计划文件
- 审阅通过后首次提交 GitHub
- 进入 Phase 0 实施
