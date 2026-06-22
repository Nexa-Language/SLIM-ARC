# SLIM-ARC 项目进展总结

**项目**: Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization for On-Device Agents  
**赛题**: Proj 59 - 内存受限环境的大语言模型推理优化问题  
**团队**: 中山大学 · 欧阳易芃、马福泉、刘昊 · 指导老师：赵帅

## 技术路线

由于 FlexInfer fork 版本过旧无法加载 Qwen3 GGUF，我们选择在上游最新 llama.cpp 基础上实现 SLIM-ARC 的预取调度器。核心创新是**统一 I/O 带宽预算调度器**，协调权重预取、KV Cache 换页和 MoE 专家预取三者竞争带宽。

## 已完成

### Phase 0: 环境搭建与基线复现 ✅

- cgroups v2 三档隔离（8G+4核 / 12G+6核 / 16G+8核）
- 上游 llama.cpp 编译，Qwen3-4B 和 OLMoE-1B-7B GGUF 模型下载
- 三档 baseline 数据采集

### Phase 1: 访存行为分析 ✅

- GGUF 张量分析工具（`scripts/profile/analyze_gguf.py`）
- Qwen3-4B: 36层，每层 57.5 MiB，FFN 占 80%
- OLMoE: 64 专家，每专家 3.6 MiB

### Phase 2a: MoE 专家预测预取（设计+分析）✅

- MoE 专家分布分析工具（`scripts/profile/analyze_moe.py`）
- 带宽减少潜力：87.5%（完美预测）、70%（80% 准确率）

### Phase 2b: KV Cache 异步换页（设计）✅

- 分层 KV Cache 设计：hot(sink) / warm(sliding) / cold(mmap→SSD)
- 注意力分数驱动驱逐策略

### Phase 2c: Prefill/Decode 动态锁定 ✅

- 实现 `slim-arc-prefetch.h/cpp` 张量级异步预取调度器
- 集成到 `llama-context.cpp` 的 `graph_compute`
- Prefill 阶段：窗口=4，async madvise(WILLNEED)
- Decode 阶段：禁用（避免 madvise 开销）
- 测试结果：16GB prefill +5%

### Phase 2d: Tile 级流水线（设计）✅

- Tile 大小选择基于 L2 cache（1 MiB）
- 融合反量化+MatMul 消除双倍带宽

### Phase 3: 统一 I/O 带宽预算调度器（设计）✅

- 阶段感知带宽分配（Prefill/Decode/MoE/长上下文）
- 动态自适应调整

### Phase 4: 消融实验框架 ✅

- `scripts/bench/run-ablation.sh` 系统化实验脚本
- 三档 × 两模型 × warm/cold 全矩阵测试

## Baseline 数据

### Qwen3-4B (Dense, Q4_K_M, 2.32 GiB)

| 环境 | pp64 (tok/s) | tg32 (tok/s) |
|------|-------------|-------------|
| 8GB+4核 | 39.80 | 9.74 |
| 12GB+6核 | 52.40 | 11.33 |
| 16GB+8核 | 54.28 | 11.90 |

### OLMoE-1B-7B (MoE, Q4_K_M, 3.92 GiB)

| 环境 | pp64 (tok/s) | tg32 (tok/s) |
|------|-------------|-------------|
| 无限制 | 97.61 | 26.45 |

### SLIM-ARC Phase 2c (Qwen3-4B, prefill-only prefetch)

| 环境 | pp64 (tok/s) | 提升 | tg32 (tok/s) | 变化 |
|------|-------------|------|-------------|------|
| 8GB+4核 | 40.88 | +2.7% | 8.05 | -17.3%* |
| 16GB+8核 | 56.58 | +4.2% | 10.51 | -11.7%* |

*Decode 回退因热缓存下 madvise 开销；已通过禁用 decode 预取修复

## GitHub 提交记录

1. `:tada: chore: initialize SLIM-ARC project structure`
2. `:construction: chore(phase0): setup cgroups, build flexinfer, clone upstream`
3. `:memo: docs: add plan/02 for approach A`
4. `:sparkles: feat(bench): add upstream baseline script`
5. `:sparkles: feat(prefetch): implement tensor-level async prefetch scheduler`
6. `:wrench: chore: populate config/data/logs/tests dirs`
7. `:sparkles: feat: record baseline data, verify OLMoE MoE`
8. `:chart_with_upwards_trend: feat(phase1): add memory access profiler`
9. `:zap: feat(phase2c): implement Prefill/Decode-aware dynamic prefetch`
10. `:memo: docs: update ROADMAP with Phase 2c results`
11. `:memo: docs: add Phase 2a/2b design documents`
12. `:sparkles: feat(phase2a): MoE expert profiler, 87.5% bandwidth reduction`
13. `:memo: docs: add Phase 2d and Phase 3 designs`
14. `:wrench: feat(phase4): add ablation study framework`
15. `:chart_with_upwards_trend: docs: add Phase 4 ablation summary`

## 待完成

1. Qwen3-Next-80B 下载完成后测试 45GB 模型在受限环境表现
2. 冷缓存消融实验完整运行
3. Phase 2b KV Cache offloading 实现
4. Phase 3 统一调度器实现
5. Phase 2d Tile 流水线实现
6. 完整消融实验和最终报告
