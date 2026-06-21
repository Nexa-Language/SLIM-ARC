# Phase 0 方案 A: 在上游 llama.cpp 上实现 FlexInfer prefetch

## 背景

FlexInfer fork 的 llama.cpp 版本过旧（build 3907），GGUF reader 与官方 Qwen3 GGUF 的 alignment/padding 不兼容，无法加载。backport Qwen3 架构也因上游已重构为 C++ 面向对象而不可行。

决策：放弃 FlexInfer fork，在**上游最新 llama.cpp** 基础上实现 FlexInfer 的 prefetch 机制。

## 目标

在上游 llama.cpp（`src/llama-upstream/`）中实现 FlexInfer 论文的核心机制：
1. 张量级异步多线程预取
2. 均衡内存锁定（mlock）
3. 灵活张量保留（Algorithm 1）
4. Direct I/O 支持

## 前置条件

- 上游 llama.cpp 已克隆到 `src/llama-upstream/` 并编译成功
- Qwen3-4B-Q4_K_M GGUF 已下载
- 上游 llama-cli 可加载 Qwen3（验证中）

## FlexInfer Prefetch 机制分析

### 核心组件（需在上游重新实现）

1. **预取线程池**：异步读取下一层张量到内存
2. **Direct I/O 路径**：绕过 page cache，直接 SSD→内存
3. **4096 对齐**：GGUF 张量数据 4096 字节对齐（Direct I/O 要求）
4. **内存锁定**：mlock 固定物理页，防止被 OS 换出
5. **Algorithm 1**：根据内存预算决定 FFN/Attention 保留比例

### FlexInfer 代码位置（参考）

- `src/flexinfer/ggml/src/ggml-prefetch.c`（预取核心）
- `src/flexinfer/ggml/src/ggml-alloc-prefetch.c`（内存分配）
- `src/flexinfer/ggml/src/ggml-backend-prefetch.cpp`（后端）
- `src/flexinfer/src/llama-prefetch.cpp`（模型层）
- `src/flexinfer/common/common-prefetch.cpp`（CLI 参数）
- 编译宏 `FLEXINFER` 控制是否启用 prefetch 路径

### 关键 CLI 参数

- `-am <GB>`：可用内存预算
- `-tp <N>`：预取线程数（0 = 同步读取）

## 实施步骤

### 步骤 1: 验证上游 baseline

- 确认上游 llama-cli 能正常推理 Qwen3-4B
- 记录 baseline 性能数据（无 prefetch）

### 步骤 2: 分析 FlexInfer prefetch 代码

- 阅读 `src/flexinfer/ggml/src/ggml-prefetch.c`
- 理解预取线程池、Direct I/O、内存锁定的实现
- 提取核心逻辑，适配上游的 C++ 结构

### 步骤 3: 在上游实现 prefetch

由于上游是 C++ 面向对象，需要：
- 在 `ggml/src/` 添加 prefetch 模块
- 在 `llama/src/` 添加 prefetch 集成
- 在 `common/` 添加 `-am`, `-tp` 参数

### 步骤 4: 4096 对齐转换

- 用上游 convert 脚本从 HF 重新转换 Qwen3-4B（带 4096 对齐）
- 或修改 convert 脚本支持 `--alignment 4096`

### 步骤 5: 验证与对比

- 对比上游 baseline vs 上游+prefetch 的性能
- 三档环境（8G/12G/16G）下测试

## 风险

| 风险 | 应对 |
|------|------|
| 上游 C++ 结构与 FlexInfer C 风格差异大 | 逐步适配，保留 FlexInfer 核心算法 |
| Direct I/O 需要根权限 | 文档说明，或用 mmap + madvise 替代 |
| 预取逻辑与上游 graph 执行集成困难 | 参考 FlexInfer 的 graph 改造方式 |

## ROADMAP 变更记录

- 2026-06-21: 创建此子计划，基于用户决策"方案 A：在上游 llama.cpp 上实现 prefetch"
