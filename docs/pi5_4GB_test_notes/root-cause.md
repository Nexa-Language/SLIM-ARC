# SLIM-ARC 补丁编译失败根因分析（T1）

> 日期：2026-08-05（UTC+8）
> 环境：树莓派 5（4GB / aarch64 / Debian 13 trixie），upstream llama.cpp commit 1c3c9674
> 证据：首次构建完整日志当时保存为 `build-slimarc-attempt-1.log`（现按清理要求移除，属中间过程），关键错误摘要见下。

## 一、现象

执行 `python3 scripts/apply-slim-arc.py` 后编译 `llama-cli` / `llama-bench` 失败。
`src/llama-upstream/src/llama-context.cpp`（`llama_context::graph_compute`）编译报错：

```
2480: error: ‘INT_MAX’ was not declared in this scope
2489/2500/2505/2517/2522: error: ‘max_layer’ was not declared in this scope; did you mean ‘min_layer’?
2501/2518: error: ‘slim_arc::prefetch_scheduler’ has no member named ‘effective_window’
2507/2524: error: ‘slim_arc::prefetch_scheduler’ has no member named ‘get_cached_experts’
2508/2525: error: ‘slim_arc::prefetch_scheduler’ has no member named ‘prefetch_experts’
2513: error: ‘slim_arc::prefetch_scheduler’ has no member named ‘set_phase’
2513/2514: error: ‘slim_arc::compute_phase’ has not been declared
2560: error: ‘slim_arc::prefetch_scheduler’ has no member named ‘cache_router_experts’
```

## 二、根因分类

### A 类：脚本与补丁源码接口版本不同步（主因）

`scripts/apply-slim-arc.py` 插入到 `llama-context.cpp` / `llama-model-loader.cpp` 的代码，
调用了 `patches/llama-upstream/slim-arc-prefetch.{h,cpp}` 中**尚未实现**的接口：

| 缺失项 | 类型 | 调用位置（脚本插入） | 应实现语义 |
|---|---|---|---|
| `slim_arc::compute_phase` 枚举（`PREFILL`/`DECODE`） | 枚举 | llama-context.cpp:2513 | 阶段标识（Dense 模型用） |
| `prefetch_scheduler::set_phase(compute_phase)` | 方法 | llama-context.cpp:2513 | 记录当前计算阶段 |
| `prefetch_scheduler::effective_window()` | 方法 | llama-context.cpp:2501/2518 | 返回预取窗口 `window_` |
| `prefetch_scheduler::get_cached_experts(layer,&n)` | 方法 | llama-context.cpp:2507/2524 | 返回某层缓存的路由专家 ID 数组 |
| `prefetch_scheduler::prefetch_experts(layer,exps,n)` | 方法 | llama-context.cpp:2508/2525 | 对指定层选中专家发 WILLNEED |
| `prefetch_scheduler::cache_router_experts(layer,exps,n)` | 方法 | llama-context.cpp:2560 | 缓存某层路由选中的专家 ID |
| `prefetch_scheduler::register_expert_tensor(...)` | 方法 | llama-model-loader.cpp | 注册 3D 合并专家张量（MoE） |
| `prefetch_scheduler::set_memory_budget(size_t)` | 方法 | unified-scheduler.cpp:80 | 记录权重预取带宽预算 |

### B 类：upstream llama.cpp API/头文件漂移（次要）

- **`INT_MAX` 未声明**：`scripts/apply-slim-arc.py` 的 `patch_context` 只添加了
  `<vector>`，但脚本插入的代码（`int min_layer = INT_MAX, ...`）依赖 `<climits>`。
  本次 `llama-context.cpp` 未间接包含 `<climits>`（上游 1c3c9674 亦如此），导致
  **`int min_layer = INT_MAX, max_layer = -1;` 整行声明解析失败**，进而 `max_layer`
  在后续 5 处引用全部报 "was not declared" —— 即**级联错误**。

### C 类：补丁源码中完全缺失的全局符号

- **`slim_arc::register_mmap_region(void*, size_t)`**：`apply-slim-arc.py` 在
  `llama-model-loader.cpp` 中调用（MADV_RANDOM 分支内注册 mmap 区域），但
  `patches/llama-upstream/` 全部 8 个文件均无该函数定义/声明，必然链接失败。
  （首次日志在 llama-context.cpp 处终止，未及报出；源码核对确认缺失。）

## 三、影响范围

- 所有缺失项均为"脚本已调用、实现缺失"的单向缺口，无 API 设计冲突。
- `unified_io_scheduler` 的 `set_phase(runtime_phase)` / `tick()` / `runtime_phase`
  枚举均**已存在且可编译**，无需改动。
- `kv_eviction_manager` 接口完整，无需改动。
- 修复方向：**补齐 prefetch_scheduler 缺失接口 + 增加 `<climits>` + 补充
  register_mmap_region 定义**，严格对齐脚本调用意图，不做逻辑/机制重构。

## 四、修复策略（T2）

1. `scripts/apply-slim-arc.py`：`patch_context` 增加 `<climits>`（幂等），修复 INT_MAX 级联错误。
2. `patches/llama-upstream/slim-arc-prefetch.h`：新增 `compute_phase` 枚举、
   8 个缺失成员声明、`register_mmap_region` 全局函数声明。
3. `patches/llama-upstream/slim-arc-prefetch.cpp`：实现上述成员与全局函数
   （最小实现，保持原设计意图）。
4. **镜像同步**：重新运行 `apply-slim-arc.py`（自动将 `patches/` 复制到
   `src/llama-upstream/src/`，并对 llama-context.cpp 应用 `<climits>` 补丁）。
5. 迭代编译，记录 `build-slimarc-attempt-N.log`（N≥2）。

## 五、既有基线参考

- vanilla upstream llama.cpp 已编译成功（`llama-cli`/`llama-bench` 产物存在）。
- Qwen3-4B 既有基线约 0.3/0.4 t/s（见 `docs/pi5_4GB_test_notes/pi5_qwen3_4b_results.md`）。
