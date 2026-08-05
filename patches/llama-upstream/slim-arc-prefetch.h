#pragma once

// SLIM-ARC: Tensor-level asynchronous prefetch scheduler
//
// This module implements layer-ahead prefetch on top of upstream llama.cpp's
// mmap infrastructure. When computing layer N, it asynchronously issues
// posix_madvise(WILLNEED) for tensors in layers N+1..N+window, allowing the
// kernel to overlap I/O with computation.

#include "ggml.h"

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>

namespace slim_arc {

struct tensor_prefetch_info {
    void *   addr;      // mmap address of tensor data
    size_t   size;      // tensor data size in bytes
    int      layer;     // layer index (or -1 for non-layer tensors)
    uint64_t signature; // monotonic counter to detect graph changes
};

// SLIM-ARC FIX 2026-08-05: runtime compute phase used by set_phase().
// Consumed by the graph_compute hook inserted by scripts/apply-slim-arc.py.
enum class compute_phase {
    PREFILL,   // batched / prefill graph compute
    DECODE,    // token-by-token decode graph compute
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

    // SLIM-ARC FIX 2026-08-05: interface required by the hooks inserted by
    // scripts/apply-slim-arc.py and by slim-arc-unified-scheduler.cpp.
    // Set current compute phase (PREFILL vs DECODE).
    void set_phase(compute_phase phase) { phase_.store(phase); }
    // Current effective prefetch lookahead window (in layers).
    int effective_window() const { return window_; }
    // Set weight prefetch bandwidth budget (bytes per cycle).
    void set_memory_budget(size_t bytes) { memory_budget_.store(bytes); }
    // Register a 3D-merged MoE expert tensor (ne[2] == n_experts).
    void register_expert_tensor(const char * name, void * addr, size_t size,
                                int layer, int n_experts);
    // Cache router-selected expert IDs for a layer (from ffn_moe_topk).
    void cache_router_experts(int layer, const int * experts, int n);
    // Get cached router expert IDs for a layer; sets *n to count, returns nullptr if none.
    const int * get_cached_experts(int layer, int * n) const;
    // Issue madvise(WILLNEED) for the given experts of a layer.
    void prefetch_experts(int layer, const int * experts, int n);

  private:
    void worker_loop();

    int n_threads_;
    int window_;
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

    // SLIM-ARC FIX 2026-08-05: phase/budget state and MoE expert bookkeeping.
    std::atomic<compute_phase> phase_{compute_phase::PREFILL};
    std::atomic<size_t>        memory_budget_{0};

    // per-expert sub-range of a 3D-merged expert tensor
    struct expert_tensor_info {
        void * base_addr;        // tensor start address
        size_t per_expert_size;  // bytes per expert (size / n_experts)
        int    n_experts;        // number of experts
    };
    std::vector<std::vector<expert_tensor_info>> expert_tensors_by_layer_;
    std::vector<std::vector<int>>                cached_experts_by_layer_;
};

// Global singleton (set by llama_context during init)
prefetch_scheduler * get_global_prefetch_scheduler();
void set_global_prefetch_scheduler(prefetch_scheduler * s);

// Helper: extract layer index from tensor name (blk.%d.*)
int tensor_layer_from_name(const char * name);

// SLIM-ARC FIX 2026-08-05: register an mmap region for potential dynamic MADV
// switching (called by llama-model-loader when MADV_RANDOM is applied).
void register_mmap_region(void * addr, size_t size);

} // namespace slim_arc
