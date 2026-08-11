# 05-v1: On-Demand 加载方案重新设计（mmap + madvise）

## 时间
2026-06-22

## 背景
之前的 on-demand loader 方案（`slim-arc-on-demand.h/cpp`）使用 `pread + aligned_alloc + tensor->data` 直接操作，在 upstream llama.cpp 中存在两个致命问题：

1. **顺序错误**：`register_tensor` 遍历 `ml.ctx_map` 时，`ctx_ptr` 已被 `std::move` 到 `pimpl->ctxs_bufs`（line 1589），导致 `ctx_ptr.get()` 返回 nullptr → SIGSEGV at `ggml_get_first_tensor()`。

2. **架构冲突**：upstream llama.cpp 的 CPU backend 计算时依赖 `tensor->buffer` + `tensor->data` 的组合。直接用 `aligned_alloc` 设置 `tensor->data` 而 `tensor->buffer` 是 dummy buffer（size=0），backend scheduler 行为不可预测。

3. **时序错误**：`use_on_demand` 在 buffer 分配阶段（line 1553）就被检查，但直到 line 1634 才被设为 true，该分支永远不会执行。

## 新方案：mmap + madvise（与内核协同）

**核心思路**：放弃手动 `pread`，改用内核的 demand paging 机制。

- `use_mmap = true` 时，upstream llama.cpp 已经把 GGUF 文件 mmap 到内存，tensor->data 指向 mmap 区域
- 内核默认对 mmap 文件做 sequential readahead，对 45GB 模型会预读过多页面
- 我们的优化：
  1. `madvise(MADV_RANDOM)`：关闭 readahead，只在真正访问时触发 page fault
  2. `madvise(MADV_DONTNEED)`：主动释放已完成计算的层，腾出 RAM
  3. `madvise(MADV_WILLNEED)`：预取即将计算的层，异步触发 page fault

**优势**：
- 不破坏 backend buffer 架构（tensor->buffer 和 tensor->data 都正常）
- 利用内核 page cache 的 LRU 淘汰，无需手动管理内存
- 代码改动极小（只新增 madvise 调用，不改 load_tensors 流程）
- 内核级别的 page fault 处理比用户态 pread 更高效

## 前置条件
- 模型文件已在 `data/models/`
- upstream llama.cpp 可编译

## 步骤拆解

### Step 1: 创建 slim-arc-mmap-advisor 模块
- 新增 `slim-arc-mmap-advisor.h/cpp`
- 提供 `madvise_layer_range(void * base, size_t len, int advice)` 接口
- 提供 `advise_layer_willneed(int layer)` / `advise_layer_dontneed(int layer)`
- 从 tensor name 解析 layer id，记录 tensor 的 mmap 地址范围

### Step 2: 集成到 llama-model-loader.cpp
- 在 `init_mappings()` 完成后，对整个 mmap 区域调用 `madvise(MADV_RANDOM)`
- 注册 tensor 的 mmap 地址到 advisor

### Step 3: 集成到 llama-context.cpp 的 graph_compute
- 计算前：对当前层 + 未来 window 层的 tensor 调用 `madvise(MADV_WILLNEED)`
- 计算后：对已完成的层的 tensor 调用 `madvise(MADV_DONTNEED)`

### Step 4: 移除旧的 on-demand loader
- 删除 `slim-arc-on-demand.h/cpp` 的集成代码（保留文件以便后续消融对比）
- 从 `llama-model.cpp` 移除 1553-1564 和 1622-1674 的代码块
- 从 `llama-model.h` 移除 `on_demand_loader` 和 `use_on_demand` 成员
- 从 `CMakeLists.txt` 暂时保留 on-demand.cpp（无害）

### Step 5: 测试验证
- 用 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf` 在 cgroups 8GB 环境下运行
- 确认能启动并完成推理（不 OOM）
- 对比 baseline（no-mmap，OOM）vs SLIM-ARC（mmap+madvise，能跑）

## 验收标准
- [ ] Qwen3-Next-80B 在 8GB cgroups 下能启动 `llama-bench -p 4 -n 2`
- [ ] 输出 token 且不 OOM
- [ ] 内存峰值 < 8GB（cgroup 限制）
- [ ] madvise 调用生效（/proc/[pid]/smaps 可见）

## 风险
1. **WSL2 的 mmap 行为**：WSL2 下 page cache 可能不如原生 Linux 精确，但 demand paging 仍然有效
2. **MoE 专家的 madvise 粒度**：512 个专家只激活 10 个，理想情况只对激活的专家做 WILLNEED。但当前不知道激活哪些专家（需要 router 输出），先做粗粒度（整个层）
3. **MADV_DONTNEED 的时机**：如果过早释放，decode 阶段每步都需要重新加载，反而慢。需要区分 prefill（顺序，可释放）和 decode（随机，需保留）
