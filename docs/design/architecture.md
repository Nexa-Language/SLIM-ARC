# SLIM-ARC 代码架构文档

> 本文档面向开发者，描述 SLIM-ARC 的代码结构、模块职责、调用关系与构建方式。
> 面向阅读源码的工程师，非项目计划。

## 1. 源码组织

SLIM-ARC 的代码分为两部分：

### 1.1 独立模块（`src/llama-upstream/src/slim-arc-*.h/.cpp`）

这些文件是 SLIM-ARC 原创，独立于 llama.cpp upstream，通过 CMake 编译为 llama 静态库的一部分。

| 文件 | 职责 | 行数 |
|------|------|------|
| `slim-arc-prefetch.h/.cpp` | 层感知预取调度器、MoE Router Hook、mmap 区域管理、MADV 切换 | ~300 |
| `slim-arc-unified-scheduler.h/.cpp` | 统一 I/O 带宽预算调度器 | ~170 |
| `slim-arc-kv-eviction.h/.cpp` | KV Cache 分层驱逐管理器（sink+window+cold） | ~160 |
| `slim-arc-on-demand.h/.cpp` | 按需加载控制（预留，当前由 prefetch 覆盖） | ~280 |

### 1.2 llama.cpp 源文件修改（通过 `scripts/apply-slim-arc.py` 集成）

| 上游文件 | 修改点 | 作用 |
|---------|--------|------|
| `llama-model-loader.cpp` | 模型加载后注册 mmap 区域、创建 scheduler | 在 `init_mappings` 末尾插入 SLIM-ARC 初始化 |
| `llama-context.cpp` | `graph_compute` 前后插入 hook | 预取调度 + MoE Router 提取 + KV eviction |
| `llama-kv-cache.cpp` | `clear()` 中加 `MADV_DONTNEED` | KV 清空时释放物理页 |
| `CMakeLists.txt` | 添加 SLIM-ARC 源文件 | 编译集成 |

## 2. 模块依赖关系

```
llama-model-loader (加载模型)
    │
    ├── register_mmap_region() ──→ slim-arc-prefetch (mmap 区域注册表)
    ├── set_global_prefetch_scheduler() ──→ prefetch_scheduler 单例
    └── set_global_unified_scheduler() ──→ unified_io_scheduler 单例
                                            │
llama-context::graph_compute (每层计算)     │
    │                                       │
    ├── tensor_layer_from_name() ──→ slim-arc-prefetch (解析层级)
    ├── notify_layer_compute() ──→ prefetch_scheduler (触发预取)
    ├── cache_router_experts() ──→ prefetch_scheduler (缓存 router 输出)
    ├── prefetch_experts() ──→ prefetch_scheduler (选择性专家预取)
    ├── get_cached_experts() ──→ prefetch_scheduler (获取预测)
    ├── unified tick() ──→ unified_io_scheduler (带宽预算调度)
    └── switch_madvise_all() ──→ slim-arc-prefetch (动态 MADV 切换)
```

## 3. 关键数据结构

### 3.1 `tensor_prefetch_info`（slim-arc-prefetch.h）
```c
struct tensor_prefetch_info {
    void *   addr;      // mmap 地址
    size_t   size;      // 张量字节数
    int      layer;     // 层级（blk.N 中的 N，-1 为非层张量）
    uint64_t signature; // 图变化检测
};
```

### 3.2 `expert_tensor_info`（slim-arc-prefetch.h）
```c
struct expert_tensor_info {
    void * base_addr;       // 3D 合并张量起始地址
    size_t total_size;      // 所有专家总大小
    int    n_experts;       // 专家数（如 512）
    size_t per_expert_size; // total_size / n_experts
};
```
用于 MoE 专家的子区域预取：`expert_addr = base_addr + expert_id * per_expert_size`。

### 3.3 `kv_eviction_config`（slim-arc-kv-eviction.h）
```c
struct kv_eviction_config {
    size_t sink_tokens   = 4;       // 永久热 token 数
    size_t window_tokens = 4096;    // 滑动窗口大小
    size_t budget_bytes  = 0;       // 内存预算（0=无限）
    double evict_threshold = 0.01;  // attention 分数驱逐阈值
    bool   enable_offload = false;  // 是否 offload 到 SSD
    std::string offload_path;       // mmap 临时文件路径
};
```

## 4. 运行时控制（环境变量）

| 环境变量 | 默认 | 作用 |
|---------|------|------|
| `SLIM_ARC_DISABLE` | 未设置 | 设置后禁用所有 SLIM-ARC 优化 |
| `SLIM_ARC_NO_MADV_RANDOM` | 未设置 | 设置后不设 MADV_RANDOM（仅 WILLNEED） |
| `SLIM_ARC_DYNAMIC_MADV` | 未设置 | 设置后启用 prefill/decode 动态 MADV 切换 |
| `SLIM_ARC_KV_EVICT` | 未设置 | 设置后启用 StreamingLLM KV eviction |
| `SLIM_ARC_KV_SINK` | 4 | attention sink token 数 |
| `SLIM_ARC_KV_WINDOW` | 1024 | KV 滑动窗口大小 |

## 5. 构建与复现

```bash
# 1. 克隆 upstream llama.cpp
git clone https://github.com/ggml-org/llama.cpp src/llama-upstream

# 2. 应用 SLIM-ARC 修改
python3 scripts/apply-slim-arc.py

# 3. 构建（禁用 repack 避免 OOM）
cd src/llama-upstream
cmake -B build -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)

# 4. 运行 80B
LD_LIBRARY_PATH=build/bin ./build/bin/llama-cli \
    -m ../../data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf \
    -t 8 -c 256 -ctk q4_0 -ctv q4_0 -fa auto -p "prompt"
```

## 6. 测试脚本

| 脚本 | 用途 |
|------|------|
| `scripts/bench/run-80b-bench.sh` | 80B benchmark（三档） |
| `scripts/bench/run-gsm8k-api.py` | GSM8K 精度测试（通过 llama-server API） |
| `scripts/bench/run-ablation.sh` | 四组消融实验 |
| `scripts/env/setup-cgroups.sh` | cgroups v2 三档环境配置 |

## 7. 模块详细文档

- [prefetch_scheduler API](phase2a-moe-expert-prediction.md) — 预取调度器
- [KV Cache eviction](phase2b-kv-cache-offload.md) — KV 分层驱逐
- [动态 MADV 切换](phase2c-dynamic-locking.md) — prefill/decode 策略切换
- [Tile 流水线](phase2d-tile-pipeline.md) — 设计草案（未实现）
- [统一 I/O 调度器](phase3-unified-io-scheduler.md) — 带宽预算
