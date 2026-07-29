# 报告大规模重构计划 v4

## 核心问题
实验部分与 design 逻辑脱节——很多实验在优化加入前独立测试，导致混乱。需重跑实验、重新画图、重新规划实验结构。

## 9 项要求

### ① 实验重跑（最核心）
所有核心实验和消融必须在**完整 SLIM-ARC（含所有优化）**下重做：
- 80B 三档性能：在 SLIM-ARC 全开（MADV+KVq4_0+IQ4_XS+FlashAttention）下测
- 消融：逐个关闭优化测贡献，而非独立测
- 对比 baseline = upstream llama.cpp（无任何 SLIM-ARC）
- 需重跑的实验列表：
  1. 80B Q4_K_M + SLIM-ARC 全开 三档（8/12/16GB）pp+tg
  2. 80B IQ4_XS + SLIM-ARC 全开 + FlashAttention 三档
  3. 消融：逐个关 MADV/KVq4/IQ4XS/FlashAttention/eviction
  4. 2GB+1核极端环境（两个小模型 Qwen3-4B + OLMoE）
  5. KV eviction 相关性消融（开/关 + 带宽变化）
  6. KV 量化对比（F16/Q8_0/Q4_0）在 SLIM-ARC 全开下

### ② 3.3.3 加 prefill/decode 量化占比
在 03_core_design 的 3.3.3（prefill/decode tradeoff）加数据：
- prefill 阶段 I/O 占比 vs decode 阶段 I/O 占比
- 权重 I/O vs KV I/O vs 计算 的占比量化
- 可从 llama-bench 的 pp/tg 时间推算

### ③ 3.6 refer 数据章节
03_core_design 的 3.6（FlashAttention 或 StreamingLLM）中 refer 到 05_evaluation 的对应实验数据

### ④ 优化相关性 highlight（放到前面）
在 abstract 或 intro 后加"优化协同 insight"section：
- MADV_RANDOM → 促进 KV q4_0（释放内存给 KV）
- KV q4_0 → 促进 IQ4_XS cache 命中（更多 RAM 给权重）
- IQ4_XS → 促进 FlashAttention（更小模型更快 attention）
- FlashAttention → 与 eviction 冲突（发现并记录）
- 写成"优化 A 促进 B"的匹配表

### ⑤ 优化分类放置
将优化分为 3 类：
- **A. 内核协同类**：MADV_RANDOM, GGML_CPU_REPACK=OFF
- **B. 量化压缩类**：IQ4_XS, KV q4_0
- **C. 计算融合类**：FlashAttention, StreamingLLM eviction
design 和 evaluation 按此分类组织

### ⑥ 超参数联调（写进计划）
- 各优化的超参数：MADV 阈值(6GB)、KV window/sink、prefetch window、IQ4_XS vs Q4_K_M
- 决赛用 ML 联调（贝叶斯优化/网格搜索）
- 写进 06_conclusion 的未来展望

### ⑦ abstract 和 intro 分开
- 01_abstract.tex：摘要（含全部优化分类的 design 图引用 + 优化总览）
- 新建 intro section（在 abstract 后、background 前）：介绍背景动机 + design 总览图
- abstract 中放一个"全部优化点分类包含的 design 图"

### ⑧ FlashAttention baseline 改名
05_evaluation 中 FlashAttention 实验的 "baseline" 改为 "SLIM-ARC (无 -fa)" 或 "SLIM-ARC 无 FlashAttention"，因为 baseline 是 SLIM-ARC 本身而非 upstream

### ⑨ 2GB+1核极端环境实验
- Qwen3-4B Dense 在 2GB+1核
- OLMoE-1B-7B MoE 在 2GB+1核
- 测量 SLIM-ARC 在极端受限下的效果

### ⑩ 实验部分重新规划小节
4 大节不变，小节重组：
- 5.1 实验设置（环境+模型+方法+数据集+对比维度+基线）
- 5.2 核心实验（80B 三档全开性能 + 优化链 + 端到端生成）
- 5.3 附属实验（小模型含2GB极端 + KV量化对比 + FlashAttention + eviction）
- 5.4 消融实验（逐个关闭 + 相关性消融 + 精度验证 + 负面结果）

## 执行顺序
1. ⑦ 拆分 abstract/intro + 优化分类 design 图描述
2. ④⑤ 优化协同 insight + 分类表（写进 intro）
3. ②③ 3.3.3 数据 + 3.6 refer
4. ⑧ FlashAttention baseline 改名
5. ⑥ 超参数联调写进计划
6. ①⑨⑩ 重跑实验 + 2GB极端 + 重新规划实验小节（最大工作量）
7. 重新画图（优化链、消融、相关性）
8. 编译 + 推送

## 风险
- 实验重跑需要数小时（80B 慢）
- 2GB 环境可能 OOM 需调试
- 图表全部重画工作量大
