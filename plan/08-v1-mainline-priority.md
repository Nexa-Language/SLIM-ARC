# 06-v1: 回归主线 - 优化系统优先级重排

## 代码修改细节（Step 1 实施）

### 修改 1: `llama-model-loader.cpp` MADV_RANDOM 条件化
- 只对 >6GB 的大模型应用 MADV_RANDOM（小模型让 upstream 默认 WILLNEED 全预读）
- 加 `SLIM_ARC_DISABLE=1` 环境变量开关，用于 baseline 对比
- prefetch_scheduler 注册也受同样开关控制

### 修改 2: `scripts/bench/run-ablation.sh` 增强
- 加 `--mode baseline|slim-arc` 参数
- baseline 模式设置 `SLIM_ARC_DISABLE=1`
- 输出 CSV 格式，便于后续汇总
- 加内存峰值收集（从 cgroup memory.peak 读取）

### 修改 3: 新增 `scripts/bench/run-quick-ablation.sh`
- 快速版：只跑 Qwen3-4B + OLMoE，3 档，warm cache
- 用于快速验证优化效果，不跑 cold（cold 太慢）

## 时间
2026-06-22

## 背景
用户反馈：80B 模型跑不出来可以先放，但要先把其他优化做完，让我们在 Dense（Qwen3-4B）或其他 MoE（OLMoE-1B-7B）上比 baseline 高出一大截。目标是一整个优化系统，不是单个子任务。

## 当前进度盘点

### 已完成（可用资产）
1. **Phase 0 环境**：cgroups v2 三档配置脚本（`scripts/env/setup-cgroups.sh`）
2. **Phase 0 Baseline**：upstream llama.cpp 编译成功，Qwen3-4B/OLMoE baseline 数据已采集
3. **Phase 1 分析**：GGUF 分析工具（`scripts/profile/analyze_gguf.py`）、MoE 分析（`scripts/profile/analyze_moe.py`）、三档内存报告
4. **Phase 2c 部分**：prefetch_scheduler（WILLNEED 预取 + phase 感知 + evict_layer API）
5. **按需加载核心**：mmap + MADV_RANDOM + 禁用 repack（45GB 不 OOM 已验证，但速度慢）

### 未完成（缺口）
1. **Phase 2a MoE 专家预取**：0% - 最关键的 MoE 优化
2. **Phase 2b KV Cache 换页**：10% - 只有原型
3. **Phase 2d Tile 流水线**：0%
4. **Phase 3 统一调度器**：10% - 只有原型
5. **Phase 4 消融矩阵**：20% - 只有部分 baseline

## 策略调整

### 核心原则
**以"能在比赛中展示的对比数据"为导向，而非"技术完美度"**

比赛评分看的是：baseline vs 优化后的对比数据。我们需要**可量化的提升**，而不是每个模块都做一半。

### 优先级重排

#### P0（必须完成，能立即产出对比数据）
1. **Qwen3-4B（Dense）三档完整消融**
   - baseline（upstream 默认）vs SLIM-ARC（mmap+MADV_RANDOM+prefetch）
   - 3 档环境 × 多 prompt 长度
   - 预期：热缓存下 tg 提升已验证 +87%

2. **OLMoE-1B-7B（MoE，4GB）三档完整消融**
   - 同上矩阵
   - MoE 模型的 prefetch 效果更明显（专家稀疏）

#### P1（核心创新，争取完成）
3. **Phase 2a MoE 专家选择性预取**
   - 在 OLMoE 上验证：只预取激活专家 vs 全专家预取
   - 这是 FlexInfer 论文的核心延伸
   - 即使只在 OLMoE 上有效也是成果

4. **Phase 3 统一调度器集成**
   - 将 prefetch_scheduler 升级为统一调度器
   - 协调权重预取 + KV 换页（如果有）
   - 在 Qwen3-4B/OLMoE 上验证"协同 > 单点"

#### P2（锦上添花，视进度）
5. **Phase 2b KV Cache 换页**：长上下文场景
6. **Phase 2d Tile 流水线**：计算-IO 重叠
7. **80B 端到端**：如果时间允许，用 16GB 环境跑

## 执行计划

### Step 1: 完善 benchmark 框架（快速）
- 修改 `scripts/bench/run-ablation.sh`，支持：
  - 三档 cgroup 自动切换
  - baseline vs SLIM-ARC 自动对比
  - 多 prompt 长度（16/64/128/512）
  - 自动收集 pp/tg/RSS 数据到 CSV

### Step 2: Qwen3-4B 完整消融（P0）
- 三档环境 × {baseline, +prefetch, +MADV_RANDOM, 全开}
- 产出 `reports/phase4-ablation-qwen3-4b.md`

### Step 3: OLMoE 完整消融（P0）
- 同上矩阵
- 产出 `reports/phase4-ablation-olmoe.md`

### Step 4: MoE 专家选择性预取（P1）
- 分析 OLMoE Router 决策模式
- 实现 expert_predictor：上一层 router 输出预测下一层激活专家
- 在 OLMoE 上验证：全专家预取 vs 选择性预取 vs Oracle

### Step 5: 统一调度器集成（P1）
- 将 prefetch_scheduler 升级，加入 KV 预留预算
- 验证 prefill/decode 阶段切换效果

## 验收标准
- [ ] Qwen3-4B 三档消融数据完整（baseline vs 优化，提升显著）
- [ ] OLMoE 三档消融数据完整
- [ ] MoE 专家预取在 OLMoE 上有对比数据
- [ ] 统一调度器有"协同 > 单点"的证据
- [ ] 消融报告可直接用于比赛材料

## 风险
1. 禁用 repack 后 Q4_K GEMM 速度：热缓存已验证无损失，冷缓存慢
2. cgroup 内存限制下 KV cache 分配：需控制 context size
3. MoE 专家预测准确率：若低则退化为保守预取
