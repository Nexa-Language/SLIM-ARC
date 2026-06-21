# Phase 0 技术发现：上游 llama.cpp 预取机制分析

## 关键发现

### 1. 上游 llama.cpp 已内置 mmap 预取

文件：`src/llama-mmap.cpp`（行 445-470）

```cpp
impl(struct llama_file * file, size_t prefetch, bool numa) {
    // ...
    if (prefetch > 0) {
        if (posix_madvise(addr, std::min(file->size(), prefetch), POSIX_MADV_WILLNEED)) {
            // 预取指定大小的文件到内存
        }
    }
    if (prefetch == 0 || file->size() > prefetch) {
        if (posix_madvise(addr, file->size(), POSIX_MADV_RANDOM)) {
            // 其余部分标记为随机访问
        }
    }
}
```

调用链：`llama_model_loader::init_mappings(prefetch=true)` → `llama_mmap(file, prefetch=-1, numa)`

### 2. FlexInfer 的核心差异

FlexInfer 在 `#ifdef FLEXINFER` 下实现了：
- **逐层张量级预取**：计算第 N 层时，异步预取第 N+1/N+2 层张量
- **Direct I/O**：绕过 page cache（`FLEXINFER_USE_DIRECT_IO`）
- **内存锁定**：mlock 固定物理页
- **Algorithm 1**：按内存预算决定 FFN/Attention 保留比例

上游的 madvise 预取是**加载时全量预取**，不是逐层调度。

### 3. SLIM-ARC 的创新方案

**方向**：在上游 llama.cpp 的 mmap 路径上，实现逐层张量级异步预取调度。

**核心思路**：
- 利用上游已有的 mmap 机制（无需 Direct I/O）
- 在 `llama_context::graph_compute` 前，对即将计算的层做 `madvise(WILLNEED)`
- 用独立线程池异步预取未来 N 层的张量
- 根据 Prefill/Decode 阶段动态调整预取窗口

**优势**：
- 复用上游完整的 Qwen3 支持
- 复用上游的 mmap + madvise 基础设施
- 只需在计算图执行前注入预取调用
- 工作量远小于复刻 FlexInfer 的 Direct I/O 路径

## Baseline 数据

上游 llama.cpp（无 cgroup，4 线程）：
- pp64 (prefill): 41.77 ± 1.45 tok/s
- tg32 (decode):  8.33 ± 0.61 tok/s

## 下一步实施计划

1. 在 `src/llama-upstream/src/` 创建 `slim-arc-prefetch.cpp` 实现逐层预取调度器
2. 在 `llama_context::graph_compute` 前注入预取调用
3. 添加 CLI 参数 `-am`（内存预算）和 `-tp`（预取线程数）
4. 对比 baseline vs SLIM-ARC prefetch 的性能

## ROADMAP 变更

- 2026-06-21: 确认方案 A 可行，发现上游已有 madvise 基础，制定逐层预取方案
