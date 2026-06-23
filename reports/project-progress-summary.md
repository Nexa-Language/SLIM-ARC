# SLIM-ARC 项目进度总结

> **审计修正版**: 经独立审计后重写，修正完成度标记和数据口径。

## 项目概述

**SLIM-ARC** (Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization for On-Device Agents) 是 2026 全国大学生系统能力大赛操作系统设计赛 Proj 59 参赛项目。

## 核心成果（有原始日志佐证）

### Qwen3-Next-80B (45GB MoE) 在 8GB cgroup

**四组单点消融（pp16+tg4）**：

| 配置 | pp16 | tg4 | 说明 |
|------|------|-----|------|
| baseline | 0.63 | 0.08 | 全关 |
| MADV_RANDOM only | 0.27 | **0.29** | decode +262% |
| prefetch only | 0.54 | 0.07 | 等价 baseline |
| slim-arc (全开) | 0.28 | 0.29 | = MADV only |

**pp4+tg1 对比**：

| Mode | pp4 | tg1 | 提升 |
|------|-----|-----|------|
| baseline | 0.22 | 0.08 | - |
| slim-arc | 0.25 | 0.43 | **tg +437%** |

原始日志: [`logs/ablation/raw-80b/`](../logs/ablation/raw-80b/)

### 关键发现

1. **MADV_RANDOM 是 decode 提升的核心**：+262% ~ +437%
2. **prefetch_scheduler 当前冗余**：全开 == MADV only（详见归因分析）
3. **prefill 有代价**：-57%（MADV_RANDOM 阻止顺序预读）
4. **baseline 能跑 80B**：禁用 repack 后不 OOM，只是 decode 慢

## 模块完成度（诚实标记）

| 模块 | 集成状态 | 说明 |
|------|---------|------|
| mmap + MADV_RANDOM | ✅ 真集成 | 大模型(>6GB)自动启用，核心驱动 |
| 禁用 GGML_CPU_REPACK | ✅ 编译配置 | 无此则 OOM |
| prefetch_scheduler | ✅ 集成但冗余 | 80B 场景无独立价值 |
| Phase 2a MoE router hook | ✅ 真集成 | 但效果未独立验证 |
| Phase 2a 跨层专家预取 | ✅ 真集成 | 但与全开无差异 |
| Phase 3 unified tick() | ✅ 真集成 | 但 KV=nullptr |
| **evict_layer** | ⚠️ 接口完成，**未调用** | 定义存在，无调用点 |
| **Phase 2b KV 换页** | ⚠️ 接口完成，**未集成推理** | kv_manager 传 nullptr |
| Phase 2b KV clear 页释放 | ✅ 轻量集成 | DONTNEED on clear |
| **Phase 2d Tile 流水线** | ⚠️ 隐式实现 | 依赖内核 page cache，无独立代码 |
| Phase 2c 动态锁定 | ✅ phase 感知 + cgroup 自适应 | |

## 代码资产

```
src/llama-upstream/src/
├── slim-arc-prefetch.h/cpp          # WILLNEED + evict + expert 接口
├── slim-arc-unified-scheduler.h/cpp # 统一调度器 tick()
├── slim-arc-kv-eviction.h/cpp       # KV 换页接口（未集成推理）
├── slim-arc-on-demand.h/cpp         # 旧方案（已禁用）
├── llama-model-loader.cpp           # mmap + MADV_RANDOM + cgroup 自适应
├── llama-context.cpp                # graph_compute: router hook + unified tick
├── llama-kv-cache.cpp               # clear 时 DONTNEED
└── llama-model.cpp/h                # 移除旧 on-demand loader
```

### 环境变量开关

| 变量 | 作用 |
|------|------|
| `SLIM_ARC_DISABLE=1` | 全关（baseline 对比） |
| `SLIM_ARC_NO_MADV_RANDOM=1` | 只关 MADV_RANDOM |
| `SLIM_ARC_NO_PREFETCH=1` | 只关 prefetch |
| （默认） | 全开 |

## 设计文档

| 文档 | 内容 |
|------|------|
| [`architecture.md`](../docs/design/architecture.md) | 总架构 + 实现状态 |
| [`phase2a-moe-expert-prediction.md`](../docs/design/phase2a-moe-expert-prediction.md) | MoE 专家预取 |
| [`phase2b-kv-cache-offload.md`](../docs/design/phase2b-kv-cache-offload.md) | KV 换页设计 |
| [`phase2c-dynamic-locking.md`](../docs/design/phase2c-dynamic-locking.md) | 动态锁定策略 |
| [`phase2d-tile-pipeline.md`](../docs/design/phase2d-tile-pipeline.md) | Tile 流水线 |
| [`phase3-unified-io-scheduler.md`](../docs/design/phase3-unified-io-scheduler.md) | 统一调度器 |

## 报告

| 报告 | 内容 |
|------|------|
| [`phase4-ablation-summary.md`](phase4-ablation-summary.md) | 消融实验（含全部 CSV） |
| [`optimization-attribution-analysis.md`](optimization-attribution-analysis.md) | 四组归因分析 |
| [`phase2b-kv-cache-analysis.md`](phase2b-kv-cache-analysis.md) | KV 内存占用分析 |

## 最终验证结论（6GB + 长上下文）

### 6GB 环境（更受限）验证
80B 6GB 四组消融：prefetch 仍冗余，MADV_RANDOM 是唯一驱动（decode +112%）。

### 长上下文验证（OLMoE pp512+tg32）
小模型（<6GB）不触发 MADV_RANDOM，prefetch 反而有害（-18%）。确认 SLIM-ARC 价值仅在大模型（>6GB）+ MoE 稀疏性场景。

### 适用场景边界
- ✅ **大模型（>6GB）+ MoE**: decode +112%~+425%
- ❌ **小模型（<6GB）**: prefetch 增加开销，无收益
- ❌ **Dense 模型**: 无 MoE 稀疏性，MADV_RANDOM 无优势

## 代码资产（三重保护）

1. **`patches/llama-upstream/`**: 8 个 slim-arc 独立文件（已跟踪）
2. **`patches/llama-upstream/slim-arc-integration.patch`**: 完整 1535 行 patch（已跟踪）
3. **`scripts/apply-slim-arc.py`**: 幂等集成脚本，可从 patches 完整恢复（已跟踪）

### 恢复流程
```bash
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git src/llama-upstream
python3 scripts/apply-slim-arc.py src/llama-upstream
cd src/llama-upstream/build && cmake -DGGML_CPU_REPACK=OFF .. && cmake --build . -j
```

## Git 提交记录

共 15+ 次提交，审计后修正了：
- 80B 数据可溯源（raw-80b/ 目录）
- 模块标记诚实（接口 vs 集成区分）
- 四组单点消融数据
- 删除矛盾说法

## 核心卖点（修正版）

1. **80B 在 8GB decode 提升 262-437%** — 有原始日志可溯源
2. **MADV_RANDOM + MoE 稀疏性** — 四组消融证明核心机制
3. **诚实的技术归因** — prefetch 冗余被承认，非夸大
4. **可复现** — 环境变量开关 + 脚本 + 原始日志
