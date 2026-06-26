# SLIM-ARC 代码架构文档

> 本文档面向开发者，描述 SLIM-ARC 的代码结构、模块职责、调用关系与构建方式。

## 1. 源码组织

SLIM-ARC 的代码分为两部分：

### 1.1 独立模块（`src/llama-upstream/src/slim-arc-*.h/.cpp`）

这些文件是 SLIM-ARC 原创，独立于 llama.cpp upstream，通过 CMake 编译为 llama 静态库的一部分。

| 文件 | 职责 | 行数 |
|------|------|------|
| `slim-arc-prefetch.h/.cpp` | 层感知预取调度器、MoE Router Hook、mmap 区域管理、MADV 切换、KV eviction | ~300 |
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

## 2. 三层架构

SLIM-ARC 采用三层协同架构（与论文 03_core_design.tex 对应）：

### 2.1 内核协同层（底层）

利用 mmap 将 GGUF 模型文件映射到虚拟地址空间，通过 posix_madvise 控制页面预取策略。

- **mmap**：45GB VSZ 虚拟映射，不占用物理内存
- **MADV_RANDOM**：禁用内核顺序预读，仅 page fault 时加载 → RSS 从 45GB 降至 2GB
- **page cache**：利用内核 demand paging，MoE 10/512 激活专家按需加载
- **NVMe SSD**：3.5GB/s 顺序读写，GGUF 文件直接 mmap

### 2.2 运行时调度层（中层）

基于运行时阶段（Prefill/Decode）和 MoE Router 输出，动态调度权重预取与专家选择性加载。

- **prefetch_scheduler**：层感知异步预取，窗口大小随阶段调整
- **MoE Router Hook**：提取 ffn_moe_topk 张量，跨层预测激活专家
- **unified_io_scheduler**：权重/KV/专家三路 I/O 带宽预算分配
- **StreamingLLM eviction**：sink(4) + sliding window(1024) KV 驱逐

### 2.3 量化优化层（顶层）

从算法层面降低内存占用和 I/O 带宽需求。

- **IQ4_XS**：4.25 bpw 量化，45GB → 40GB
- **KV q4_0**：KV Cache 内存减半，decode +14%
- **FlashAttention**：IO-aware tiling 融合，decode +71.4%
- **GGML_CPU_REPACK=OFF**：禁用重打包，避免 45→90GB 内存翻倍

## 3. 关键数据结构

### 3.1 `tensor_prefetch_info`（slim-arc-prefetch.h）
```c
struct tensor_prefetch_info {
    void *   addr;      // mmap 地址
    size_t   size;      // 张量字节数
    int      layer;     // 层级
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

## 4. 运行时控制（环境变量）

| 环境变量 | 默认 | 作用 |
|---------|------|------|
| `SLIM_ARC_DISABLE` | 未设置 | 设置后禁用所有 SLIM-ARC 优化 |
| `SLIM_ARC_NO_MADV_RANDOM` | 未设置 | 设置后不设 MADV_RANDOM |
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
| `scripts/bench/run-core-experiments.sh` | 80B 三档核心实验 |
| `scripts/bench/run-serial-ablation.sh` | 串行消融实验 |
| `scripts/bench/run-gsm8k-api.py` | GSM8K 精度测试 |
| `scripts/env/setup-cgroups.sh` | cgroups v2 三档环境配置 |

## 7. 模块详细文档

- [prefetch_scheduler API](phase2a-moe-expert-prediction.md)
- [KV Cache eviction](phase2b-kv-cache-offload.md)
- [动态 MADV 切换](phase2c-dynamic-locking.md)
- [Tile 流水线](phase2d-tile-pipeline.md)
- [统一 I/O 调度器](phase3-unified-io-scheduler.md)
