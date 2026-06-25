# 动态 MADV 切换 API 文档

> 源码：`src/llama-upstream/src/slim-arc-prefetch.h` / `.cpp` 的 `register_mmap_region` / `switch_madvise_all`

## 概述

Linux 的 `posix_madvise` 提供三种策略控制 mmap 区域的页面预取：
- `MADV_WILLNEED`（0）：内核顺序预读，适合 prefill 的顺序访问
- `MADV_RANDOM`（1）：禁用预读，仅 page fault 时加载，适合 MoE decode 的稀疏访问
- `MADV_DONTNEED`（2）：释放物理页，保留虚拟映射

SLIM-ARC 默认对大模型（>6GB）设 MADV_RANDOM，并可选在 prefill↔decode 切换时动态切换策略。

## 接口

```cpp
// 注册 mmap 区域（在 llama-model-loader 的 init_mappings 中调用）
void register_mmap_region(void * addr, size_t size);

// 批量切换所有注册区域的 madvise 策略
// advice: 0=WILLNEED, 1=RANDOM, 2=DONTNEED
void switch_madvise_all(int advice);
```

## 调用流程

### 静态模式（默认）
在 `llama-model-loader.cpp` 的 `init_mappings` 末尾：
```cpp
if (total_weight_size > 6GB) {
    posix_madvise(addr, size, POSIX_MADV_RANDOM);  // 一次性设置
}
```

### 动态模式（`SLIM_ARC_DYNAMIC_MADV=1`）
在 `llama-context.cpp` 的 `graph_compute` 开头：
```cpp
if (getenv("SLIM_ARC_DYNAMIC_MADV")) {
    static int current_madv = -1;
    int target = batched ? 0 : 1;  // prefill=WILLNEED, decode=RANDOM
    if (current_madv != target) {
        switch_madvise_all(target);
        current_madv = target;
    }
}
```

## 实验结论

动态切换在 llama-bench 的分离测试（prefill 和 decode 独立运行）中**表现不佳**：
- prefill 阶段设 WILLNEED，预读的页面在切换到 RANDOM 时被丢弃
- 切换开销抵消了理论收益

在真实连续推理（prefill→decode 过渡）中可能有效，但需要进一步验证。当前默认使用静态 MADV_RANDOM（decode 优先），通过 `SLIM_ARC_NO_MADV_RANDOM=1` 可关闭。

## 环境变量

| 变量 | 作用 |
|------|------|
| `SLIM_ARC_DISABLE` | 禁用所有 SLIM-ARC |
| `SLIM_ARC_NO_MADV_RANDOM` | 不设 MADV_RANDOM（仅用默认 WILLNEED） |
| `SLIM_ARC_DYNAMIC_MADV` | 启用动态切换（实验性） |
