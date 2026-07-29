// SLIM-ARC: Tensor-level On-Demand Loader Implementation

#include "slim-arc-on-demand.h"

#include <algorithm>
#include <climits>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace slim_arc {

on_demand_loader::on_demand_loader(const std::string & gguf_path, size_t memory_budget_bytes)
    : memory_budget_(memory_budget_bytes) {
    gguf_fd_ = open(gguf_path.c_str(), O_RDONLY);
    if (gguf_fd_ < 0) {
        return;
    }
    struct stat st;
    if (fstat(gguf_fd_, &st) == 0) {
        gguf_size_ = st.st_size;
    }

    // Start prefetch worker threads
    int n_workers = 2;
    for (int i = 0; i < n_workers; ++i) {
        prefetch_workers_.emplace_back([this] { prefetch_worker_loop(); });
    }
}

on_demand_loader::~on_demand_loader() {
    {
        std::lock_guard<std::mutex> lk(prefetch_mtx_);
        stop_ = true;
    }
    prefetch_cv_.notify_all();
    for (auto & t : prefetch_workers_) {
        if (t.joinable()) t.join();
    }
    // Free all staging buffers
    for (auto & [tensor, buf] : staging_buffers_) {
        free(buf);
    }
    if (gguf_fd_ >= 0) {
        close(gguf_fd_);
    }
}

int on_demand_loader::extract_layer(const std::string & name) {
    if (name.size() > 4 && name.substr(0, 4) == "blk.") {
        size_t dot = name.find('.', 4);
        if (dot != std::string::npos) {
            return std::stoi(name.substr(4, dot - 4));
        }
    }
    return -1;
}

bool on_demand_loader::is_expert_tensor(const std::string & name) {
    return name.find("_exps") != std::string::npos ||
           name.find("experts") != std::string::npos;
}

void on_demand_loader::register_tensor(const char * name, ggml_tensor * tensor,
                                        size_t file_offset, size_t size) {
    std::lock_guard<std::mutex> lk(mtx_);
    tensor_meta meta;
    meta.name = name;
    meta.file_offset = file_offset;
    meta.size = size;
    meta.layer = extract_layer(name);
    meta.is_expert = is_expert_tensor(name);
    meta.expert_id = -1; // TODO: parse from name

    tensor_meta_[tensor] = meta;
    if (meta.layer >= 0) {
        layer_tensors_[meta.layer].push_back(tensor);
    }

    // Set tensor data to NULL - will be loaded on demand
    tensor->data = nullptr;
}

void on_demand_loader::load_tensor_sync(ggml_tensor * tensor) {
    if (gguf_fd_ < 0) return;

    auto it = tensor_meta_.find(tensor);
    if (it == tensor_meta_.end()) return;
    if (tensor->data != nullptr) return; // already loaded

    const auto & meta = it->second;

    // Allocate buffer for tensor data
    void * buf = aligned_alloc(64, meta.size);
    if (!buf) return;

    // Read from file
    ssize_t n = pread(gguf_fd_, buf, meta.size, meta.file_offset);
    if (n != (ssize_t)meta.size) {
        free(buf);
        return;
    }

    tensor->data = buf;
    {
        std::lock_guard<std::mutex> lk(mtx_);
        loaded_tensors_.insert(tensor);
        loaded_bytes_ += meta.size;
    }
    load_count_++;
}

void * on_demand_loader::ensure_loaded(ggml_tensor * tensor) {
    if (!tensor) return nullptr;

    // Check if already loaded
    {
        std::lock_guard<std::mutex> lk(mtx_);
        if (tensor->data != nullptr) {
            return tensor->data;
        }
    }

    // Check if prefetched in staging
    {
        std::lock_guard<std::mutex> lk(mtx_);
        auto sit = staging_buffers_.find(tensor);
        if (sit != staging_buffers_.end()) {
            tensor->data = sit->second;
            loaded_tensors_.insert(tensor);
            loaded_bytes_ += tensor_meta_[tensor].size;
            staging_buffers_.erase(sit);
            return tensor->data;
        }
    }

    // Load synchronously
    load_tensor_sync(tensor);

    // Enforce memory budget
    enforce_memory_budget();

    return tensor->data;
}

size_t on_demand_loader::ensure_layer_loaded(int layer) {
    std::lock_guard<std::mutex> lk(mtx_);
    auto it = layer_tensors_.find(layer);
    if (it == layer_tensors_.end()) return 0;

    size_t total = 0;
    // Release lock for loading (load_tensor_sync uses its own lock)
    auto tensors = it->second;
    mtx_.unlock();
    for (auto * t : tensors) {
        if (t->data == nullptr) {
            load_tensor_sync(t);
            total += tensor_meta_[t].size;
        }
    }
    mtx_.lock();
    enforce_memory_budget();
    return total;
}

void on_demand_loader::evict(ggml_tensor * tensor) {
    if (!tensor || !tensor->data) return;

    std::lock_guard<std::mutex> lk(mtx_);
    auto it = tensor_meta_.find(tensor);
    if (it == tensor_meta_.end()) return;

    free(tensor->data);
    tensor->data = nullptr;
    loaded_tensors_.erase(tensor);
    loaded_bytes_ -= it->second.size;
    evict_count_++;
}

size_t on_demand_loader::evict_layer(int layer) {
    std::lock_guard<std::mutex> lk(mtx_);
    auto it = layer_tensors_.find(layer);
    if (it == layer_tensors_.end()) return 0;

    size_t total = 0;
    for (auto * t : it->second) {
        if (t->data) {
            free(t->data);
            t->data = nullptr;
            loaded_tensors_.erase(t);
            loaded_bytes_ -= tensor_meta_[t].size;
            evict_count_++;
            total += tensor_meta_[t].size;
        }
    }
    return total;
}

void on_demand_loader::enforce_memory_budget() {
    while (loaded_bytes_ > memory_budget_) {
        // Find oldest loaded tensor to evict (simple LRU: evict lowest layer)
        int min_layer = INT_MAX;
        ggml_tensor * victim = nullptr;

        for (auto * t : loaded_tensors_) {
            auto & meta = tensor_meta_[t];
            if (meta.layer >= 0 && meta.layer < min_layer) {
                min_layer = meta.layer;
                victim = t;
            }
        }

        if (!victim) break;
        free(victim->data);
        victim->data = nullptr;
        loaded_tensors_.erase(victim);
        loaded_bytes_ -= tensor_meta_[victim].size;
        evict_count_++;
    }
}

void on_demand_loader::prefetch_layers(int current_layer, int window) {
    {
        std::lock_guard<std::mutex> lk(prefetch_mtx_);
        prefetch_target_layer_ = current_layer;
        prefetch_window_ = window;
    }
    prefetch_cv_.notify_one();
}

void on_demand_loader::prefetch_worker_loop() {
    while (true) {
        int target_layer, window;
        {
            std::unique_lock<std::mutex> lk(prefetch_mtx_);
            prefetch_cv_.wait(lk, [this] { return stop_ || prefetch_target_layer_ >= 0; });
            if (stop_) return;
            target_layer = prefetch_target_layer_;
            window = prefetch_window_;
            prefetch_target_layer_ = -1; // consume
        }

        // Prefetch layers [target+1, target+window]
        for (int w = 1; w <= window; ++w) {
            int layer = target_layer + w;
            std::vector<ggml_tensor *> tensors_to_prefetch;

            {
                std::lock_guard<std::mutex> lk(mtx_);
                auto it = layer_tensors_.find(layer);
                if (it == layer_tensors_.end()) continue;
                for (auto * t : it->second) {
                    if (t->data == nullptr &&
                        staging_buffers_.find(t) == staging_buffers_.end()) {
                        tensors_to_prefetch.push_back(t);
                    }
                }
            }

            for (auto * t : tensors_to_prefetch) {
                auto & meta = tensor_meta_[t];
                void * buf = aligned_alloc(64, meta.size);
                if (!buf) continue;

                ssize_t n = pread(gguf_fd_, buf, meta.size, meta.file_offset);
                if (n == (ssize_t)meta.size) {
                    std::lock_guard<std::mutex> lk(mtx_);
                    staging_buffers_[t] = buf;
                    prefetch_count_++;
                } else {
                    free(buf);
                }
            }
        }
    }
}

} // namespace slim_arc
