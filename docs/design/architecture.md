# SLIM-ARC 架构设计

## 1. 设计目标

在纯 CPU、受限内存（8-16GB）环境下，为端侧 LLM 推理提供统一的 I/O 调度框架，实现：

1. **低内存占用**: 通过权重卸载和 KV 换页，使大模型在受限内存下可运行
2. **高吞吐量**: 通过预取掩盖 I/O 延迟，逼近"计算无等待"的理想流水线
3. **低延迟**: 优化 TTFT 和 TPOT，满足交互式场景需求
4. **精度保持**: 换页和量化不显著影响输出质量（PPL 损失 < 1%）

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    SLIM-ARC 统一调度层                       │
│                                                             │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐         │
│  │ 权重卸载  │  │ KV 换页    │  │ MoE 专家预测预取  │         │
│  │ 模块     │  │ 模块       │  │ 模块              │         │
│  │(FlexInfer)│  │(DUAL-BLADE)│  │  (MobileMoE)    │         │
│  └─────┬────┘  └─────┬─────┘  └────────┬────────┘         │
│        └──────────────┼──────────────────┘                  │
│               ┌───────▼───────┐                             │
│               │ 统一 I/O 调度器│ ← 核心创新点                 │
│               │ (带宽预算分配) │                             │
│               └───────┬───────┘                             │
│        ┌──────────────┼──────────────────┐                 │
│   ┌────▼────┐  ┌─────▼─────┐  ┌────────▼─────┐             │
│   │Tile流水线│  │动态锁定    │  │投机解码       │             │
│   │+融合反量化│ │(Prefill/   │  │(Draft-Verify) │             │
│   │         │  │ Decode)    │  │              │             │
│   └─────────┘  └───────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              mmap + madvise 内核协同层 (已实现)               │
│  (MADV_RANDOM 按需分页 · WILLNEED 异步预取 · DONTNEED 换出)  │
│  (upstream llama.cpp · GGML backend buffer · GGUF 格式)     │
└─────────────────────────────────────────────────────────────┘
```

## 实现状态（2026-06-22）

| 模块 | 状态 | 文件 |
|------|------|------|
| 权重按需加载 (mmap+MADV_RANDOM) | ✅ 已实现 | `llama-model-loader.cpp` |
| 禁用 GGML_CPU_REPACK | ✅ 已配置 | CMake `-DGGML_CPU_REPACK=OFF` |
| prefetch_scheduler | ✅ 已实现 | `slim-arc-prefetch.h/cpp` |
| Phase 感知 (Prefill/Decode) | ✅ 已实现 | `prefetch_scheduler::set_phase` |
| cgroup 自适应跳过 | ✅ 已实现 | `init_mappings` |
| MoE expert tensor 注册 | ✅ 已实现 | `register_expert_tensor` |
| 跨层专家预测预取 | ✅ 已实现 | graph_compute router hook |
| evict_layer (DONTNEED) | ✅ 接口已实现 | `prefetch_scheduler::evict_layer` |
| unified_io_scheduler | ✅ 原型+集成 | `slim-arc-unified-scheduler.h/cpp` |
| KV eviction manager | ✅ 接口已实现 | `slim-arc-kv-eviction.h/cpp` |
| KV 集成到推理流程 | ❌ 待实现 | 需修改 `llama-kv-cache.cpp` |
| Tile 流水线 | ✅ 隐式实现 | mmap page cache 粒度 |

## 核心成果

### 1. 80B 模型端到端成功
- Qwen3-Next-80B (45GB) 在 16GB cgroup: pp4=0.17 t/s, tg1=0.38 t/s
- Baseline (SLIM_ARC_DISABLE=1) 在 8GB/16GB 均 OOM

### 2. 冷启动消融数据
- OLMoE 8GB: pp +8.7%
- Qwen3-4B 8GB: tg +18.6%
- 详见 [`reports/phase4-ablation-summary.md`](../reports/phase4-ablation-summary.md)

## 3. 核心模块

### 3.1 权重卸载模块（继承自 FlexInfer）

**职责**: 将模型权重卸载到 SSD，按需通过 Direct I/O 加载到内存。

**关键机制**:
- 张量级异步多线程预取（默认窗口 = 3）
- 均衡内存锁定（mlock 固定物理页）
- 灵活张量保留（Algorithm 1，静态启发式决定 FFN/Attention 保留比例）

**SLIM-ARC 改造点**:
- 将静态 Algorithm 1 升级为运行时动态策略（见 3.6）
- 预取线程池统一纳入调度器管理（见 3.5）

### 3.2 KV Cache 换页模块

**职责**: 将长上下文中低注意力分数的 KV Block 换出到 SSD，需要时预取回内存。

**参考**: DUAL-BLADE（NVMe-direct 双路）、ScoutAttention（层前 CPU 预计算）、HillInfer（分层 KV 驱逐）

**关键机制**:
- KV Block 级注意力分数追踪（轻量，不引入额外计算）
- 冷热分级：sink token（永久驻留）+ sliding window（热区）+ cold block（可换出）
- 异步换出/换入流水线（复用 FlexInfer prefetch 线程池）

**设计决策**:
- 不引入 SmartSSD 等特殊硬件（保持纯 CPU + NVMe）
- 换出策略基于注意力分数阈值，非固定窗口，适应不同 prompt 模式

### 3.3 MoE 专家预测预取模块

**职责**: 对 MoE 模型，提前预测激活专家，仅预取所需权重，降低 I/O 带宽需求。

**参考**: MobileMoE（端侧 MoE 扩展）、MoE-Prism（专家解耦）、Distributed MoE Expert Placement

**关键机制**:
- 轻量级 Router Predictor（基于上一层 Router 输出 + 薄 MLP）
- 提前 1-2 层预测，预留 I/O 时间
- 预测失败时的 fallback（退化为保守预取 + 延迟容忍）

**验证模型**: Qwen3-Next-A3B（3B 总参，稀疏激活）

### 3.4 Tile 级微流水线 + 融合反量化

**职责**: 将张量切分为 Cache 友好的 Tile，I/O 与计算交错；反量化与 MatMul 融合。

**参考**: flexinfer-optimize.md（自主论证）

**关键机制**:
- Tile 大小对齐 L2/L3 Cache 行（典型 64KB-256KB）
- 双缓冲：I/O 线程读 Tile-N 时计算线程处理 Tile-N-1
- 融合反量化：数据从 SSD 流入 CPU Cache 时即时反量化，不写回内存

### 3.5 统一 I/O 带宽预算调度器（核心创新）

**职责**: 运行时监控三路 I/O 需求（权重、KV、专家），基于阶段动态分配带宽。

**问题定义**:
```
maximize  吞吐量
s.t.     Σ bandwidth_i(t) ≤ B_total       # 带宽上限
         latency_weight(t) ≤ L_max         # 权重延迟约束
         latency_kv(t) ≤ L_max             # KV 延迟约束
         latency_expert(t) ≤ L_max         # 专家延迟约束
```

**调度策略**（启发式，非最优求解）:

| 阶段 | 权重优先级 | KV 优先级 | 专家优先级 | 说明 |
|------|----------|---------|----------|------|
| Prefill（短） | 高 | 低 | 中 | 计算密集，I/O 易掩盖 |
| Prefill（长） | 高 | 中 | 中 | KV 开始增长 |
| Decode（短） | 高 | 低 | 中 | 访存密集，权重是瓶颈 |
| Decode（长） | 中 | 高 | 中 | KV 成为主瓶颈 |
| MoE Decode | 中 | 中 | 高 | 专家稀疏性可利用 |

**实现**: 轻量级运行时监控器，基于历史 I/O 延迟和计算吞吐量动态调整预算比例。

### 3.6 Prefill/Decode 动态锁定

**职责**: 将 FlexInfer 的静态 Algorithm 1 升级为运行时动态策略。

**机制**:
- 阶段检测器：基于 batch size 和序列长度判断 Prefill/Decode
- Prefill 模式：少保留（计算密集，I/O 易掩盖）
- Decode 模式：多保留（访存密集，减少 I/O）
- 长上下文模式：FFN 内存配额让渡给 KV Cache

## 4. 数据流

### 4.1 Prefill 阶段

```
用户输入 prompt
    │
    ▼
Tokenize ──► Embedding
    │
    ▼
┌─────────────────────────────────────────┐
│  Layer 0                                │
│  ┌─────────┐  ┌─────────┐  ┌────────┐ │
│  │预取 L1   │  │计算 L0   │  │换出冷KV│ │
│  │权重+KV  │  │权重+KV  │  │(异步)  │ │
│  └─────────┘  └─────────┘  └────────┘ │
└─────────────────────────────────────────┘
    │
    ▼
  ... (重复 N 层)
    │
    ▼
Logits ──► Sample ──► 首 token
```

### 4.2 Decode 阶段

```
上一 token
    │
    ▼
┌─────────────────────────────────────────┐
│  Layer 0                                │
│  ┌──────────┐  ┌──────────┐  ┌───────┐ │
│  │预取 L1   │  │计算 L0   │  │预测L2 │ │
│  │权重(仅   │  │+ 读KV   │  │专家   │ │
│  │激活专家) │  │         │  │       │ │
│  └──────────┘  └──────────┘  └───────┘ │
└─────────────────────────────────────────┘
    │
    ▼
  ... (重复 N 层)
    │
    ▼
Logits ──► Sample ──► 下一 token
```

## 5. 与现有工作的差异

| 维度 | FlexInfer | DUAL-BLADE | MobileMoE | **SLIM-ARC** |
|------|-----------|------------|-----------|---------------|
| 权重卸载 | ✓ | ✗ | ✗ | ✓ |
| KV 换页 | ✗ | ✓ | ✗ | ✓ |
| MoE 预取 | ✗ | ✗ | ✓ | ✓ |
| 统一调度 | ✗ | ✗ | ✗ | **✓** |
| 纯 CPU | ✓ | ✗（NVMe-direct） | 部分 | ✓ |
| 开源可复现 | ✓ | ✗ | 部分 | ✓ |

## 6. 技术指标目标

| 指标 | FlexInfer Baseline | SLIM-ARC 目标 | 提升幅度 |
|------|-------------------|--------------|---------|
| 吞吐量 (8G) | X tok/s | 1.5X tok/s | +50% |
| TTFT (16K) | Y ms | 0.7Y ms | -30% |
| 峰值内存 | Z GB | 0.85Z GB | -15% |
| PPL 损失 | 0 | < 0.5 | 可接受 |

*具体数值待 Phase 0 baseline 跑出后确定*

## 7. 演进路线

1. **Phase 0-1**: 复现 FlexInfer，建立 baseline，完成访存 profiling
2. **Phase 2**: 单点优化（各模块独立验证）
3. **Phase 3**: 统一调度器集成
4. **Phase 4**: 全矩阵消融实验
5. **Phase 5**: Agent 场景适配（后期）
