// SLIM-ARC: Tensor-level asynchronous prefetch scheduler
//
// Implements layer-ahead prefetch on top of upstream llama.cpp's mmap.
// When computing layer N, async madvise(WILLNEED) for layers N+1..N+window.

#include "slim-arc-prefetch.h"

#include <algorithm>
#include <cstring>
#include <sys/mman.h>

namespace slim_arc {

namespace {
prefetch_scheduler * g_scheduler = nullptr;
}

prefetch_scheduler * get_global_prefetch_scheduler() { return g_scheduler; }
void set_global_prefetch_scheduler(prefetch_scheduler * s) { g_scheduler = s; }

int tensor_layer_from_name(const char * name) {
    if (!name) return -1;
    // match "blk.%d." prefix
    if (std::strncmp(name, "blk.", 4) != 0) return -1;
    const char * p = name + 4;
    if (*p < '0' || *p > '9') return -1;
    int layer = 0;
    while (*p >= '0' && *p <= '9') {
        layer = layer * 10 + (*p - '0');
        ++p;
    }
    if (*p != '.') return -1;
    return layer;
}

prefetch_scheduler::prefetch_scheduler(int n_threads, int window)
    : n_threads_(std::max(1, n_threads)),
      window_prefill_(std::max(1, window + 1)),  // prefill: larger window (compute-bound)
      window_decode_(1) {                         // decode: minimal window (memory-bound, avoid overhead)
    workers_.reserve(n_threads_);
    for (int i = 0; i < n_threads_; ++i) {
        workers_.emplace_back([this] { worker_loop(); });
    }
}

void prefetch_scheduler::set_phase(compute_phase phase) {
    phase_.store(phase);
    effective_window_.store(compute_effective_window());
}

void prefetch_scheduler::set_memory_budget(size_t budget_bytes) {
    memory_budget_.store(budget_bytes);
    effective_window_.store(compute_effective_window());
}

int prefetch_scheduler::compute_effective_window() const {
    auto phase = phase_.load();
    int w = (phase == compute_phase::PREFILL) ? window_prefill_ : window_decode_;

    // If memory budget is set, limit window to fit budget
    size_t budget = memory_budget_.load();
    if (budget > 0 && !tensors_by_layer_.empty()) {
        // Estimate average layer size
        size_t total = 0;
        int n = 0;
        for (const auto & layer_tensors : tensors_by_layer_) {
            for (const auto & t : layer_tensors) {
                total += t.size;
                ++n;
            }
        }
        if (n > 0) {
            size_t avg_layer = total / tensors_by_layer_.size();
            int max_w = (int)(budget / avg_layer);
            if (max_w < 1) max_w = 1;
            if (w > max_w) w = max_w;
        }
    }
    return w;
}

prefetch_scheduler::~prefetch_scheduler() {
    {
        std::lock_guard<std::mutex> lk(mtx_);
        stop_ = true;
    }
    cv_.notify_all();
    for (auto & t : workers_) {
        if (t.joinable()) t.join();
    }
}

void prefetch_scheduler::register_tensor(const char * name, void * addr, size_t size, int layer) {
    (void) name; // name not stored currently, used for layer extraction upstream
    if (layer < 0 || addr == nullptr || size == 0) return;
    if ((size_t)layer >= tensors_by_layer_.size()) {
        tensors_by_layer_.resize(layer + 1);
    }
    tensors_by_layer_[layer].push_back({addr, size, layer, 0});
}

void prefetch_scheduler::register_expert_tensor(const char * name, void * addr, size_t total_size,
                                                 int layer, int n_experts) {
    (void) name;
    if (layer < 0 || addr == nullptr || total_size == 0 || n_experts <= 0) return;
    expert_tensor_info info;
    info.base_addr = addr;
    info.total_size = total_size;
    info.n_experts = n_experts;
    info.per_expert_size = total_size / n_experts;
    expert_tensors_[layer].push_back(info);
}

void prefetch_scheduler::prefetch_experts(int layer, const int * expert_ids, int n_experts) {
    if (n_experts <= 0 || expert_ids == nullptr) return;
    auto it = expert_tensors_.find(layer);
    if (it == expert_tensors_.end()) return;

    size_t bytes = 0;
    for (const auto & et : it->second) {
        for (int i = 0; i < n_experts; ++i) {
            int eid = expert_ids[i];
            if (eid < 0 || eid >= et.n_experts) continue;
            void * expert_addr = (uint8_t *) et.base_addr + (size_t) eid * et.per_expert_size;
            // posix_madvise is thread-safe and idempotent
            (void) posix_madvise(expert_addr, et.per_expert_size, POSIX_MADV_WILLNEED);
            bytes += et.per_expert_size;
        }
    }
    total_bytes_.fetch_add(bytes);
    total_calls_.fetch_add(1);
}

void prefetch_scheduler::notify_layer_compute(int current_layer) {
    if (!enabled_.load()) return;
    // In DECODE phase with hot cache (small model fits in RAM), skip prefetch.
    // But for large models with MADV_RANDOM, decode also needs prefetch because
    // pages may have been reclaimed. We check memory budget: if budget is set
    // and model likely exceeds it, always prefetch (cold cache scenario).
    if (phase_.load() == compute_phase::DECODE) {
        // Only skip decode prefetch if memory budget is 0 (small model, hot cache)
        if (memory_budget_.load() == 0) return;
    }
    {
        std::lock_guard<std::mutex> lk(mtx_);
        target_layer_     = current_layer;
        target_signature_ = ++signature_;
    }
    cv_.notify_one();
}

void prefetch_scheduler::evict_layer(int layer) {
    if (layer < 0 || (size_t)layer >= tensors_by_layer_.size()) return;
    // Synchronous eviction - must complete before next layer needs memory.
    // madvise(DONTNEED) is fast (just marks pages for reclaim, no I/O).
    for (const auto & t : tensors_by_layer_[layer]) {
        if (t.addr == nullptr || t.size == 0) continue;
        (void) posix_madvise(t.addr, t.size, POSIX_MADV_DONTNEED);
    }
}

void prefetch_scheduler::worker_loop() {
    while (true) {
        int      target_layer;
        uint64_t sig;
        {
            std::unique_lock<std::mutex> lk(mtx_);
            cv_.wait(lk, [this] { return stop_ || target_layer_ != current_layer_.load(); });
            if (stop_) return;
            target_layer = target_layer_;
            sig          = target_signature_;
        }

        if (sig != signature_.load()) continue; // stale

        current_layer_.store(target_layer);

        // Prefetch layers [target+1, target+effective_window]
        // Window adapts to Prefill (larger) vs Decode (smaller)
        int eff_window = effective_window_.load();
        size_t bytes_this_round = 0;
        for (int w = 1; w <= eff_window; ++w) {
            int layer = target_layer + w;
            if (layer < 0 || (size_t)layer >= tensors_by_layer_.size()) continue;
            for (const auto & t : tensors_by_layer_[layer]) {
                if (t.addr == nullptr || t.size == 0) continue;
                // posix_madvise is thread-safe and idempotent
                (void) posix_madvise(t.addr, t.size, POSIX_MADV_WILLNEED);
                bytes_this_round += t.size;
            }
        }

        total_bytes_.fetch_add(bytes_this_round);
        total_calls_.fetch_add(1);
    }
}

} // namespace slim_arc
