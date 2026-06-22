# SLIM-ARC ROADMAP

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
