// SLIM-ARC: Tensor-level On-Demand Loader
//
// Implements FlexInfer-style tensor offloading: instead of loading all model
// weights into RAM at startup (which causes OOM for large models like
// Qwen3-Next-80B at 45GB), this loader:
// 1. Opens the GGUF file and reads metadata only (no mmap of tensor data)
// 2. Allocates ggml_tensor structs with data=NULL (lazy allocation)
// 3. On first access to a tensor, reads its data from SSD into a managed buffer
// 4. After computation, can evict tensor data to free memory
// 5. Uses async prefetch threads to read-ahead future layers
//
// This is the CORE mechanism that enables running 45GB models on 8GB RAM.

#pragma once

#include <atomic>
#include <condition_variable>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "ggml.h"

namespace slim_arc {

struct tensor_meta {
    std::string name;
    size_t      file_offset;  // offset in GGUF file
    size_t      size;         // size in bytes
    int         layer;        // layer index (-1 if non-layer)
    bool        is_expert;    // is this an MoE expert tensor?
    int         expert_id;    // expert index within layer (-1 if not)
};

class on_demand_loader {
  public:
    on_demand_loader(const std::string & gguf_path, size_t memory_budget_bytes);
    ~on_demand_loader();

    // Register a tensor for lazy loading (called during model load)
    void register_tensor(const char * name, ggml_tensor * tensor,
                         size_t file_offset, size_t size);

    // Ensure a tensor's data is loaded into memory.
    // If not loaded, reads from SSD synchronously.
    // Returns pointer to tensor data.
    void * ensure_loaded(ggml_tensor * tensor);

    // Ensure all tensors for a given layer are loaded.
    // Returns total bytes loaded.
    size_t ensure_layer_loaded(int layer);

    // Evict a tensor's data from memory (free the buffer).
    // The tensor's data pointer is set to NULL.
    void evict(ggml_tensor * tensor);

    // Evict all tensors for a given layer.
    size_t evict_layer(int layer);

    // Async prefetch: read ahead future layers into a staging buffer.
    // Uses background threads to overlap I/O with computation.
    void prefetch_layers(int current_layer, int window);

    // Memory management
    size_t current_memory_usage() const { return loaded_bytes_.load(); }
    size_t memory_budget() const { return memory_budget_; }

    // Statistics
    int total_loads()    const { return load_count_.load(); }
    int total_evictions() const { return evict_count_.load(); }
    int total_prefetches() const { return prefetch_count_.load(); }

  private:
    int    gguf_fd_  = -1;
    size_t gguf_size_ = 0;
    size_t memory_budget_;

    std::mutex mtx_;

    // Map from tensor pointer to its metadata
    std::unordered_map<ggml_tensor *, tensor_meta> tensor_meta_;

    // Map from layer to list of tensors in that layer
    std::unordered_map<int, std::vector<ggml_tensor *>> layer_tensors_;

    // Set of currently loaded tensors
    std::unordered_set<ggml_tensor *> loaded_tensors_;

    // Memory tracking
    std::atomic<size_t> loaded_bytes_{0};
    std::atomic<int>    load_count_{0};
    std::atomic<int>    evict_count_{0};
    std::atomic<int>    prefetch_count_{0};

    // Async prefetch thread pool
    std::vector<std::thread> prefetch_workers_;
    std::atomic<bool>  stop_{false};
    std::mutex         prefetch_mtx_;
    std::condition_variable prefetch_cv_;
    int  prefetch_target_layer_{-1};
    int  prefetch_window_{3};

    // Staging buffer for prefetched data
    // Key: tensor pointer, Value: allocated buffer with data
    std::unordered_map<ggml_tensor *, void *> staging_buffers_;

    void load_tensor_sync(ggml_tensor * tensor);
    void prefetch_worker_loop();
    void enforce_memory_budget();
    int  extract_layer(const std::string & name);
    bool is_expert_tensor(const std::string & name);
};

} // namespace slim_arc
