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
#include <unordered_map>
#include <vector>

namespace slim_arc {

enum class compute_phase {
    PREFILL,  // compute-bound: large batch, I/O can be hidden
    DECODE,   // memory-bound: small batch, I/O latency critical
    UNKNOWN,
};

struct tensor_prefetch_info {
    void *   addr;      // mmap address of tensor data
    size_t   size;      // tensor data size in bytes
    int      layer;     // layer index (or -1 for non-layer tensors)
    uint64_t signature; // monotonic counter to detect graph changes
};

class prefetch_scheduler {
  public:
    explicit prefetch_scheduler(int n_threads = 2, int window = 3);
    ~prefetch_scheduler();

    // Register a tensor for potential prefetch. Called during model load.
    void register_tensor(const char * name, void * addr, size_t size, int layer);

    // SLIM-ARC Phase 2a: Register an MoE expert tensor (3D merged: [dim, dim, n_experts]).
    // Stores per-expert address ranges for selective prefetch.
    // n_experts: number of experts merged in this tensor
    void register_expert_tensor(const char * name, void * addr, size_t total_size,
                                int layer, int n_experts);

    // SLIM-ARC Phase 2a: Selectively prefetch specific experts in a layer.
    // expert_ids: indices of experts to prefetch (top-k from router)
    // n_experts: length of expert_ids array
    // This issues madvise(WILLNEED) for only the specified expert sub-regions,
    // reducing I/O bandwidth by ~(1 - k/n_experts) for MoE models.
    void prefetch_experts(int layer, const int * expert_ids, int n_experts);

    // SLIM-ARC Phase 2a: Cache router output expert IDs from layer N,
    // to be used as prediction for layer N+1 prefetch.
    // Called after graph_compute completes.
    void cache_router_experts(int layer, const int * expert_ids, int n_experts);

    // SLIM-ARC Phase 2a: Get cached expert IDs for a layer (from previous
    // layer's router output). Returns nullptr if no cache for this layer.
    const int * get_cached_experts(int layer, int * out_n) const;

    // Notify that we are about to compute layer `current_layer`.
    // This triggers async madvise(WILLNEED) for layers
    // [current_layer+1, current_layer+window].
    void notify_layer_compute(int current_layer);

    // Evict a completed layer's weight pages from RAM via madvise(DONTNEED).
    // Called after a layer finishes computation to free memory for subsequent
    // layers. This is essential for running large models (e.g. 45GB) on limited
    // RAM (8GB): without eviction, all accessed layers accumulate in page cache
    // and trigger OOM. With eviction, only the working set stays resident.
    //
    // Note: only weight tensors (file-backed mmap pages) are evicted. KV cache
    // and compute buffers (anonymous memory) are not affected.
    void evict_layer(int layer);

    // Set current compute phase (Prefill vs Decode).
    // In Prefill, we use a larger window (compute-bound, I/O hidden).
    // In Decode, we use a smaller window (memory-bound, precise prefetch).
    void set_phase(compute_phase phase);

    // Set memory budget in bytes. When exceeded, reduce window.
    void set_memory_budget(size_t budget_bytes);

    // Disable prefetch (e.g., when memory budget exceeded).
    void set_enabled(bool enabled) { enabled_.store(enabled); }

    // Collect statistics
    size_t total_prefetched_bytes() const { return total_bytes_.load(); }
    int    total_prefetch_calls()   const { return total_calls_.load(); }
    int    effective_window()       const { return effective_window_.load(); }

  private:
    void worker_loop();
    int  compute_effective_window() const;

    int n_threads_;
    int window_prefill_;  // larger window for prefill
    int window_decode_;   // smaller window for decode
    std::atomic<int>      effective_window_{3};
    std::atomic<bool>      enabled_{true};
    std::atomic<bool>      stop_{false};
    std::atomic<int>       current_layer_{-1};
    std::atomic<uint64_t>  signature_{0};
    std::atomic<size_t>    total_bytes_{0};
    std::atomic<int>       total_calls_{0};
    std::atomic<compute_phase> phase_{compute_phase::UNKNOWN};
    std::atomic<size_t>    memory_budget_{0};

    std::vector<std::thread>          workers_;
    std::mutex                       mtx_;
    std::condition_variable          cv_;
    int                               target_layer_{-1};
    uint64_t                          target_signature_{0};

    // tensor registry indexed by layer
    std::vector<std::vector<tensor_prefetch_info>> tensors_by_layer_;

    // SLIM-ARC Phase 2a: expert tensor registry for selective prefetch
    struct expert_tensor_info {
        void * base_addr;      // start of the 3D expert tensor
        size_t total_size;     // total size of all experts
        int    n_experts;      // number of experts merged
        size_t per_expert_size; // total_size / n_experts
    };
    // Key: layer -> list of expert tensors (gate_exps, up_exps, down_exps)
    std::unordered_map<int, std::vector<expert_tensor_info>> expert_tensors_;

    // SLIM-ARC Phase 2a: cached router expert IDs for cross-layer prediction
    // Key: layer, Value: vector of expert IDs from that layer's router
    std::unordered_map<int, std::vector<int>> router_expert_cache_;
};

// Global singleton (set by llama_context during init)
prefetch_scheduler * get_global_prefetch_scheduler();
void set_global_prefetch_scheduler(prefetch_scheduler * s);

// Helper: extract layer index from tensor name (blk.%d.*)
int tensor_layer_from_name(const char * name);

// SLIM-ARC: mmap region management for dynamic MADV switching.
// Stores mmap addresses so graph_compute can switch between
// MADV_WILLNEED (prefill: sequential readahead) and MADV_RANDOM
// (decode: precise demand paging) based on compute phase.
void register_mmap_region(void * addr, size_t size);

// Switch all registered mmap regions to the given advice.
// Called from graph_compute: MADV_WILLNEED before prefill, MADV_RANDOM before decode.
// This eliminates the prefill penalty while keeping decode speedup.
void switch_madvise_all(int advice);  // 0=WILLNEED, 1=RANDOM, 2=DONTNEED

} // namespace slim_arc
