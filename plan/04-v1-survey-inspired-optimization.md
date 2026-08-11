# Phase 4-v1: 综述启发的新一轮 SLIM-ARC 优化

## 目标

基于《On-Device Large Language Models: A Survey of Model Compression and System Optimization》综述和 USENIX FAST'26 SolidAttention 论文，识别 SLIM-ARC 尚未实现的高价值优化方向，设计并实现下一阶段增强。

## 前置条件

- ✅ Phase 0-3 已完成（mmap+MADV_RANDOM, prefetch_scheduler, KV q4_0, IQ4_XS, unified_io_scheduler 设计）
- ✅ 80B 在 8GB/16GB/32GB 三档均有可运行结果
- ✅ 学术报告 LaTeX 23 页已完成
- ✅ 综述 PDF 已提取（`/tmp/survey.txt`, 6076 行）
- ✅ SolidAttention 论文已深度阅读

## 综述与 SolidAttention 的关键发现

### 综述 (Sec 4.3 Memory Optimization) 的 practical tips
1. "Quantize weights first (W4/W8); quantize KV only if context exceeds device capacity" — **我们已做 KV q4_0**
2. "Enable paging early—it prevents OOM and improves batching" — **我们有 mmap 但无显式 paging**
3. "For long context, combine KV compression with **eviction policies (e.g., window + sink tokens)**" — **我们未实现！**

### SolidAttention (FAST'26) 的核心技术
1. **KV Consolidator (K/V 交错)**: token 级 K-V 交错，传输单元翻倍，I/O 次数减半 → -22% attention 延迟
2. **Speculative Prefetcher**: 跨层选择相似性 81%，预测下一层 KV block 提前预取 → -3.1~3.9× 阻塞延迟
3. **SSD-aware DAG Scheduler**: attention 分解为 microtask，计算-I/O 细粒度重叠 + 同步点复用 → -25%-22%
4. **Block-wise 动态 attention sparsity**: init blocks (sinks) + local blocks (window) + selected blocks (top-k)
5. **context budget = 1k tokens**: 只保留 1k token KV → 内存减少 98%

### 综述 (Sec 4.5 ECCC) 的启发
1. **Early Exit**: 根据输入复杂度调整计算深度，减少 40-50% 计算
2. **Semantic caching**: 84% hit rate, ~50% lower latency，用上下文摘要替代原始 KV
3. **Speculative decoding**: CE-LSLM 达 6× 加速

## SLIM-ARC 差距分析

| 方向 | 综述/SolidAttention 建议 | SLIM-ARC 现状 | 差距 |
|------|--------------------------|---------------|------|
| KV eviction | window + sink tokens (StreamingLLM) | ❌ 无 eviction，KV 全量保留 | **大** |
| KV 布局优化 | K/V token 级交错 | ❌ K/V 分离存储 | **中** |
| 跨层 KV 预取 | 跨层选择相似性 81% 投机预取 | ❌ 仅权重层感知预取 | **大** |
| 计算重叠 | DAG microtask 调度 | ❌ 同步执行 | **大** |
| Attention sparsity | block-wise top-k 选择 | ❌ 全量 attention | **大** |
| Speculative decoding | draft model 投机 | ❌ 未实现 | **中** |
| KV 量化 | KVQuant/KIVI | ✅ Q4_0 已实现 | 完成 |
| 权重量化 | IQ4_XS/W4 | ✅ IQ4_XS 已实现 | 完成 |

## 优化方向优先级（按"可行 × 收益"排序）

### P0: StreamingLLM 式 KV Eviction（最易实现 + 有先例）
- **原理**: 保留前 4 个 token (attention sinks) + 最近 W 个 token (sliding window)，驱逐中间
- **实现点**: `llama-kv-cache.cpp` 的 `llama_memory_clear` 或 seq_rm 逻辑
- **预期**: 长上下文（>4k）场景 KV 内存恒定，避免 80B decode 后期 KV 膨胀
- **风险**: Qwen3-Next 训练上下文 262k，需要验证 sink token 数量是否适用
- **工作量**: ~2 天（纯 CPU，无 GPU kernel 改动）

### P1: 跨层 KV 投机预取（SolidAttention 核心创新移植）
- **原理**: 记录每层 attention 的 top-k block 选择历史，预测下一层预取
- **实现点**: `slim-arc-prefetch.cpp` 新增 `kv_block_history` + `predict_next_layer_blocks()`
- **预期**: 减少 decode 阻塞延迟，尤其 8GB 环境 KV 从 SSD 换页时
- **风险**: 纯 CPU 场景下 KV 在 DRAM 而非 SSD，收益可能不如 GPU+SSD 场景
- **工作量**: ~3 天

### P2: Block-wise 动态 Attention Sparsity（SolidAttention 核心）
- **原理**: decode 时只对 top-k 相似度的 KV block 计算 attention
- **实现点**: 需要修改 `llama-context.cpp` 的 attention graph，或通过 custom node 注入
- **预期**: 长 context 下 attention 计算量减少 90%（context budget=1k）
- **风险**: 改动 llama.cpp attention kernel 较深，可能影响精度
- **工作量**: ~5 天（高风险）

### P3: KV K/V 交错布局（SolidAttention KV Consolidator）
- **原理**: K 和 V 在 token 维度交错存储，mmap 读取时双倍粒度
- **实现点**: GGUF tensor 重排 + mmap 路径修改
- **预期**: SSD 读取粒度翻倍，I/O 次数减半
- **风险**: 需要重新转换 GGUF 或在 load 阶段重排，工程量大
- **工作量**: ~4 天

### P4: Speculative Decoding（综述 ECCC 推荐）
- **原理**: 用小模型（Qwen3-4B）生成 draft，大模型（80B）验证
- **实现点**: llama.cpp 已有 `llama-speculative`，需要配置 draft model
- **预期**: 80B decode 加速 2-3×（若 draft 接受率高）
- **风险**: 8GB 环境同时加载 4B+80B 内存不够，需要 offload draft
- **工作量**: ~2 天（配置为主）

## 步骤拆解

### Step 1: 实现 StreamingLLM KV Eviction (P0)
1. 研究 llama.cpp KV cache 的 seq_rm 接口
2. 在 `slim-arc-prefetch.cpp` 新增 `kv_eviction_policy` 类
3. 实现 sink_tokens (前 4) + sliding_window (最近 W) 策略
4. 在 decode 每步后触发 eviction
5. 测试 80B 16GB 长 context (4k/8k/16k) 效果

### Step 2: 跨层 KV 投机预取 (P1)
1. 在 attention 计算后 hook 记录 top-k block indices
2. 实现 `kv_block_history` 环形缓冲
3. 预测下一层需要的 block，提前 MADV_WILLNEED
4. 测试 decode 延迟分布

### Step 3: 评估与消融
1. baseline (当前 SLIM-ARC) vs +eviction vs +prefetch vs +both
2. 三档环境 (8/12/16GB) × 长 context (4k/8k)
3. 精度验证: StreamingLLM eviction 的 PPL 对比

### Step 4: 更新报告与 ROADMAP
1. 新增 section 到 `05_evaluation.tex`
2. 生成新图表对比
3. 更新 `reference.bib` 加入 StreamingLLM/SolidAttention 引用

## 验收标准

- [ ] StreamingLLM KV eviction 实现并通过 80B 长 context 测试
- [ ] 跨层 KV 投机预取实现并量化延迟改善
- [ ] 消融实验数据可溯源（raw logs 保存）
- [ ] 精度验证：eviction 后 PPL 不显著退化（<15%）
- [ ] 学术报告更新，PDF 重编译
- [ ] ROADMAP 记录

## 风险

1. **StreamingLLM sink token 数量**: Qwen3 可能需要更多 sink（非标准 4 个），需实验确定
2. **纯 CPU 场景 KV 预取收益有限**: 如果 KV 全在 DRAM，预取无意义；只在 KV 触发 SSD 换页时有收益
3. **attention sparsity 改动深**: 修改 llama.cpp graph 可能引入精度 bug，优先级降低
4. **时间约束**: 比赛临近，优先实现 P0+P1，P2/P3 视时间情况

## ROADMAP 变更记录

### 2026-06-24 创建 v1
- **原因**: 用户要求读综述寻找新优化思路
- **依据**: 综述 Sec 4.3/4.5 + SolidAttention (FAST'26)
- **新增方向**: KV eviction (StreamingLLM) + 跨层 KV 投机预取 (SolidAttention)
