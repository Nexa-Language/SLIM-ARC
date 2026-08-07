# RK3588 编译问题 Root-Cause 与修复记录

- 日期：2026-08-05
- 设备：Orange Pi 5 Plus（RK3588，8GB RAM），内核 5.10.160-rockchip-rk3588
- 上游：llama.cpp master `360e134`
- 相关日志：`build-rk3588-attempt-1.log` / `build-rk3588-attempt-2.log` / `build-rk3588-attempt-3.log` / `apply-slim-arc-log-*.txt`

## 背景

`src/llama-upstream` 缺失（仓库无 `src/` 目录），用户已将 llama.cpp 拉取到
`/home/orangepi/src/llama-upstream`。运行
`python3 scripts/apply-slim-arc.py /home/orangepi/src/llama-upstream` 应用补丁后，
`cmake --build build --target llama-cli llama-bench -j2` 出现两类编译错误。

## 问题一：llama-context.cpp 编译失败（INT_MAX 级联错误 + prefetch_scheduler 缺失接口）

### 现象（attempt-1）
```
llama-context.cpp:2480: error: 'INT_MAX' was not declared in this scope
llama-context.cpp:2489: error: 'max_layer' was not declared in this scope; did you mean 'min_layer'?
llama-context.cpp:2501: error: 'class slim_arc::prefetch_scheduler' has no member named 'effective_window'
llama-context.cpp:2507: error: ... no member named 'get_cached_experts'
llama-context.cpp:2508: error: ... no member named 'prefetch_experts'
llama-context.cpp:2513: error: ... no member named 'set_phase'
llama-context.cpp:2513: error: 'slim_arc::compute_phase' has not been declared
llama-context.cpp:2560: error: ... no member named 'cache_router_experts'
```
共 16 个错误，全部集中在 `llama-context.cpp` 的 SLIM-ARC graph_compute 钩子。

### 根因分析
1. **`INT_MAX` 未声明**：`llama-context.cpp` 只 `#include <limits>`（不保证提供
   `INT_MAX`），SLIM-ARC 钩子使用 `int min_layer = INT_MAX, ...` 需要 `<climits>`。
   `INT_MAX` 报错会**级联**导致 `max_layer` 声明被编译器吞掉，进而出现
   `'max_layer' was not declared in this scope; did you mean 'min_layer'?`。
2. **`prefetch_scheduler` 缺失接口**：`apply-slim-arc.py` 生成的 graph_compute 钩子
   调用了 `effective_window()` / `get_cached_experts()` / `prefetch_experts()` /
   `set_phase()` / `cache_router_experts()` 与 `compute_phase` 枚举，以及
   `llama-model-loader.cpp` 中调用的 `set_memory_budget()` /
   `register_expert_tensor()` / `register_mmap_region()`，但
   `patches/llama-upstream/slim-arc-prefetch.{h,cpp}` 仍是**旧版本**（不含这些接口）。
   该仓库的 patches 尚未同步 Pi5 上的接口补齐修复。

### 修复
- [`scripts/apply-slim-arc.py`](../scripts/apply-slim-arc.py)：在 patch_context 中
  追加 `#include <climits>`（`INT_MAX` 级联错误防护），标注
  `// SLIM-ARC FIX 2026-08-05`。
- [`patches/llama-upstream/slim-arc-prefetch.h`](../../patches/llama-upstream/slim-arc-prefetch.h)：
  新增 `compute_phase` 枚举、`expert_tensor_info` 结构，以及
  `set_phase()` / `effective_window()` / `set_memory_budget()` /
  `register_expert_tensor()` / `cache_router_experts()` /
  `get_cached_experts()` / `prefetch_experts()` 方法与自由函数
  `register_mmap_region()` 声明。
- [`patches/llama-upstream/slim-arc-prefetch.cpp`](../../patches/llama-upstream/slim-arc-prefetch.cpp)：
  实现上述接口。`register_expert_tensor` 记录 3D 合并专家张量（每专家大小 =
  `size/n_experts`）；`prefetch_experts` 对 `addr + eid*per_expert` 区域发
  `posix_madvise(WILLNEED)`；`register_mmap_region` 维护全局 mmap 区域表。
- 修复后重新运行 `apply-slim-arc.py`（幂等）同步到 `src/llama-upstream/src/`。

## 问题二：llama-model-loader.cpp 编译失败（重复大括号）

### 现象（attempt-2）
```
llama-model-loader.cpp:1425: error: expected declaration before '}' token
```
（`init_mappings` 函数末尾多了一个 `}`。）

### 根因分析
`apply-slim-arc.py` 的 `prefetch_block` 末尾自带一个关闭函数的大括号 `}`，
而 `init_mappings` 原有的大括号仍保留在插入点之后，导致**重复大括号**。

### 修复
- [`scripts/apply-slim-arc.py`](../scripts/apply-slim-arc.py)：`prefetch_block`
  去掉末尾的 `}`（函数由原代码的右大括号关闭），标注
  `// SLIM-ARC FIX 2026-08-05`。
- `git checkout -- src/llama-model-loader.cpp` 恢复该上游文件，重新运行
  `apply-slim-arc.py` 重新生成正确的 patch。

## 编译最终结果（attempt-3）

```
BUILD_EXIT=0
[100%] Built target llama-bench
[100%] Built target llama-cli
```
- 产物：`/home/orangepi/src/llama-upstream/build/bin/llama-cli`、
  `build/bin/llama-bench`（version 1, 360e134, aarch64, GNU 11.4.0）。
- 验证：`nm -D build/bin/libllama.so` 确认 `slim_arc::prefetch_scheduler::*`、
  `register_expert_tensor` 等符号已正确导出。

## 修复清单汇总

| 文件 | 改动 | 原因 | 标注 |
|:---|:---|:---|:---|
| `scripts/apply-slim-arc.py` | 追加 `<climits>` | INT_MAX 级联错误 | SLIM-ARC FIX 2026-08-05 |
| `scripts/apply-slim-arc.py` | prefetch_block 去末尾 `}` | 重复大括号 | SLIM-ARC FIX 2026-08-05 |
| `patches/llama-upstream/slim-arc-prefetch.h` | 补齐接口/枚举/结构 | prefetch_scheduler 缺失接口 | SLIM-ARC FIX 2026-08-05 |
| `patches/llama-upstream/slim-arc-prefetch.cpp` | 实现接口 | 同上 | SLIM-ARC FIX 2026-08-05 |

> 说明：以上均为最小外科手术式 bug 修复，未改动任何核心机制/算法逻辑。
> patches 与 `src/llama-upstream/src/` 已通过 `apply-slim-arc.py` 保持镜像同步。
