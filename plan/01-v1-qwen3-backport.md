# Phase 0 子计划: Qwen3 架构 Backport 到 FlexInfer

## 背景

FlexInfer fork 自较旧版本的 llama.cpp（build 3907），不支持 `qwen3` 架构。官方 Qwen3-4B-GGUF 的 metadata 中 `general.architecture = qwen3`，加载时报错张量 shape 不匹配。

## 目标

从最新 llama.cpp backport Qwen3（及 Qwen3-Next MoE）架构支持到 FlexInfer，同时保留 FlexInfer 的 prefetch 机制完整。

## 前置条件

1. FlexInfer 已在 `src/flexinfer/` 并编译成功
2. 官方 Qwen3-4B-Q4_K_M.gguf 已下载
3. 网络代理 `http://127.0.0.1:7897` 可用

## 步骤拆解

### 步骤 1: 获取最新 llama.cpp 作为 backport 源

- 克隆 `https://github.com/ggml-org/llama.cpp` 到 `src/llama-upstream/`（不提交，仅参考）
- 确认上游版本支持 qwen3 和 qwen3-next

### 步骤 2: 分析三层代码差异

FlexInfer 与上游的差异分布在三层:

**层 1: ggml（底层张量库）**
- `ggml/include/ggml.h`: 架构枚举 `MODEL_ARCH_QWEN3`、张量类型枚举
- `ggml/src/ggml.c`: 张量映射、量化支持
- `ggml/src/ggml-quants.c/.h`: 量化 kernel（若涉及新量化类型）
- `ggml/src/ggml-common.h`: 量化 block 定义

**层 2: llama.cpp（模型定义层）**
- `src/llama.cpp`: 架构识别、张量映射、图构建（Qwen3 的 attention/FFN 实现）
- `include/llama.h`: 公共 API（通常无需改动）

**层 3: gguf-py + convert（Python 工具链）**
- `gguf-py/gguf/constants.py`: `MODEL_ARCH`、`MODEL_TENSORS`、`TENSOR_NAMES`
- `gguf-py/gguf/tensor_mapping.py`: 张量名映射
- `convert_hf_to_gguf.py`: HF → GGUF 转换（Qwen3Model 类）

### 步骤 3: backport 策略

**策略 A（推荐）: 架构定义 backport，不改量化**

先验证是否只是架构名不识别。如果 Q4_K_M 量化类型 FlexInfer 已支持（很可能，因为是常用类型），那么只需 backport:
- `ggml.h` 中添加 `MODEL_ARCH_QWEN3`
- `llama.cpp` 中添加 qwen3 的图构建逻辑
- `gguf-py/constants.py` 和 `tensor_mapping.py` 添加 qwen3 映射
- `convert_hf_to_gguf.py` 添加 Qwen3Model 类

**策略 B（兜底）: 若涉及 AWQ 新量化类型**

如果官方 GGUF 确实用了 FlexInfer 不支持的量化类型，还需 backport 量化 kernel。但 Q4_K_M 是标准类型，大概率不需要。

### 步骤 4: 分步实施

1. 先 backport Qwen3（Dense），验证 Qwen3-4B 能加载推理
2. 再 backport Qwen3-Next MoE（如果架构不同），验证 Qwen3-Next-A3B

### 步骤 5: 4096 对齐重处理

FlexInfer Direct I/O 要求 GGUF 张量 4096 字节对齐。官方 GGUF 可能用默认 32 字节对齐。
- 用 FlexInfer 的 `llama-quantize` 重新量化（会重写对齐）
- 或用 FlexInfer 的 `convert_hf_to_gguf.py` 从 HF 源重新转换（默认 4096 对齐）

## 验收标准

1. `flexinfer-cli` 能加载 Qwen3-4B-Q4_K_M.gguf 并正常推理
2. `llama-cli`（FlexInfer 版）也能加载（作为 non-prefetch baseline）
3. `flexinfer-bench` 能跑通并输出 tok/s
4. 若涉及 Qwen3-Next，同样验证

## 风险

| 风险 | 应对 |
|------|------|
| FlexInfer 的 prefetch 代码与上游 llama.cpp 差异过大，backport 冲突 | 逐文件 diff，仅取 Qwen3 相关增量 |
| Qwen3-Next MoE 架构复杂，backport 工作量大 | 先做 Dense，MoE 可降级用 Qwen2-MoE 替代 |
| 量化 kernel 差异 | 先验证 Q4_K_M 是否原生支持 |
| 对齐问题导致 Direct I/O 失败 | 用 FlexInfer 自带工具重对齐 |

## ROADMAP 变更记录

- 2026-06-21: 创建此子计划，基于用户决策"从最新 llama.cpp backport Qwen3 架构支持到 FlexInfer"
