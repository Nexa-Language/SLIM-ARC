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
};

// Global singleton (set by llama_context during init)
prefetch_scheduler * get_global_prefetch_scheduler();
void set_global_prefetch_scheduler(prefetch_scheduler * s);

// Helper: extract layer index from tensor name (blk.%d.*)
int tensor_layer_from_name(const char * name);

} // namespace slim_arc
