#pragma once

// SLIM-ARC: Tensor-level asynchronous prefetch scheduler
//
// This module implements layer-ahead prefetch on top of upstream llama.cpp's
// mmap infrastructure. When computing layer N, it asynchronously issues
// posix_madvise(WILLNEED) for tensors in layers N+1..N+window, allowing the
// kernel to overlap I/O with computation.

#include "ggml.h"

#include <atomic>
#include <climits>  // SLIM-ARC FIX 2026-08-05: 防护 INT_MAX 级联错误
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>
#include <utility>

namespace slim_arc {

// SLIM-ARC FIX 2026-08-05: 计算阶段枚举，供 graph_compute 中 set_phase() 使用。
// 当 unified_io_scheduler 未启用时，prefetch_scheduler 单独使用该阶段信息。
enum class compute_phase {
    PREFILL,
    DECODE,
};

struct tensor_prefetch_info {
    void *   addr;      // mmap address of tensor data
    size_t   size;      // tensor data size in bytes
    int      layer;     // layer index (or -1 for non-layer tensors)
    uint64_t signature; // monotonic counter to detect graph changes
};

// SLIM-ARC FIX 2026-08-05: MoE 专家张量注册信息（3D 合并张量 *_exps）。
// addr 指向整个 3D 张量数据，n_experts = ne[2]，每个专家大小为 size/n_experts。
struct expert_tensor_info {
    void * addr;        // mmap address of the merged 3D expert tensor
    size_t size;        // total bytes of the merged tensor
    int    n_experts;   // number of experts (ne[2])
};

class prefetch_scheduler {
  public:
    explicit prefetch_scheduler(int n_threads = 2, int window = 3);
    ~prefetch_scheduler();

    // Register a tensor for potential prefetch. Called during model load.
    void register_tensor(const char * name, void * addr, size_t size, int layer);

    // Notify that we are about to compute layer `current_layer`.
    // This triggers async madvise(WILLNEED) for layers
    // [current_layer+1, current_layer+window].
    void notify_layer_compute(int current_layer);

    // Disable prefetch (e.g., when memory budget exceeded).
    void set_enabled(bool enabled) { enabled_.store(enabled); }

    // Collect statistics
    size_t total_prefetched_bytes() const { return total_bytes_.load(); }
    int    total_prefetch_calls()   const { return total_calls_.load(); }

    // ---- SLIM-ARC FIX 2026-08-05: 补齐 Pi5 端修复所需接口 ----
    // 设置计算阶段（prefill / decode）
    void set_phase(compute_phase phase) { phase_.store(phase); }
    // 当前预取窗口大小（供 graph_compute 计算待预取层范围）
    int  effective_window() const { return window_; }
    // 内存预算（供 unified_io_scheduler 分配权重预取额度）
    void set_memory_budget(size_t bytes) { memory_budget_ = bytes; }

    // Phase 2a: 注册 MoE 专家张量（3D 合并张量 *_exps）
    void register_expert_tensor(const char * name, void * addr, size_t size, int layer, int n_experts);
    // 缓存该层路由器选中的专家 ID（用于跨层预测）
    void cache_router_experts(int layer, const int * expert_ids, int n);
    // 获取某层最近缓存的路由专家 ID
    const int * get_cached_experts(int layer, int * n) const;
    // 对指定层的给定专家发起 WILLNEED 预取
    void prefetch_experts(int layer, const int * expert_ids, int n);

  private:
    void worker_loop();
    void issue_expert_willneed(int layer, const int * expert_ids, int n);

    int n_threads_;
    int window_;
    std::atomic<compute_phase> phase_{compute_phase::DECODE};
    size_t memory_budget_ = 0;
    std::atomic<bool>       enabled_{true};
    std::atomic<bool>       stop_{false};
    std::atomic<int>        current_layer_{-1};
    std::atomic<uint64_t>   signature_{0};
    std::atomic<size_t>     total_bytes_{0};
    std::atomic<int>        total_calls_{0};

    std::vector<std::thread>          workers_;
    std::mutex                        mtx_;
    std::condition_variable           cv_;
    int                               target_layer_{-1};
    uint64_t                          target_signature_{0};

    // tensor registry indexed by layer
    std::vector<std::vector<tensor_prefetch_info>> tensors_by_layer_;
    // MoE expert registry indexed by layer
    std::vector<std::vector<expert_tensor_info>>   experts_by_layer_;
    // Router-selected expert IDs per layer (for next-layer prediction)
    mutable std::vector<std::vector<int>>          cached_router_experts_;
};

// Global singleton (set by llama_context during init)
prefetch_scheduler * get_global_prefetch_scheduler();
void set_global_prefetch_scheduler(prefetch_scheduler * s);

// Helper: extract layer index from tensor name (blk.%d.*)
int tensor_layer_from_name(const char * name);

// SLIM-ARC FIX 2026-08-05: mmap 区域注册表（供动态 MADV 切换；当前仅记录）。
// 在 init_mappings 中为 >6GB 模型设置 MADV_RANDOM 时调用。
void register_mmap_region(void * addr, size_t size);

} // namespace slim_arc
