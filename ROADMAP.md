# SLIM-ARC ROADMAP

> 本文件采用倒序日志：最新记录在顶部。每条记录包含时间戳、变更描述、涉及文件、决策原因。

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
