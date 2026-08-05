// SLIM-ARC: Tensor-level asynchronous prefetch scheduler
//
// Implements layer-ahead prefetch on top of upstream llama.cpp's mmap.
// When computing layer N, async madvise(WILLNEED) for layers N+1..N+window.

#include "slim-arc-prefetch.h"

#include <algorithm>
#include <cstring>
#include <utility>
#include <sys/mman.h>

namespace slim_arc {

namespace {
prefetch_scheduler * g_scheduler = nullptr;
// SLIM-ARC FIX 2026-08-05: registry of mmap regions registered for potential
// dynamic MADV switching (populated by llama-model-loader).
std::mutex                             g_mmap_mtx;
std::vector<std::pair<void *, size_t>> g_mmap_regions;
}

prefetch_scheduler * get_global_prefetch_scheduler() { return g_scheduler; }
void set_global_prefetch_scheduler(prefetch_scheduler * s) { g_scheduler = s; }

void register_mmap_region(void * addr, size_t size) {
    if (!addr || size == 0) return;
    std::lock_guard<std::mutex> lk(g_mmap_mtx);
    g_mmap_regions.emplace_back(addr, size);
}

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
    : n_threads_(std::max(1, n_threads)), window_(std::max(1, window)) {
    workers_.reserve(n_threads_);
    for (int i = 0; i < n_threads_; ++i) {
        workers_.emplace_back([this] { worker_loop(); });
    }
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
    if (layer < 0 || addr == nullptr || size == 0) return;
    if ((size_t)layer >= tensors_by_layer_.size()) {
        tensors_by_layer_.resize(layer + 1);
    }
    tensors_by_layer_[layer].push_back({addr, size, layer, 0});
}

void prefetch_scheduler::notify_layer_compute(int current_layer) {
    if (!enabled_.load()) return;
    {
        std::lock_guard<std::mutex> lk(mtx_);
        target_layer_     = current_layer;
        target_signature_ = ++signature_;
    }
    cv_.notify_one();
}

void prefetch_scheduler::register_expert_tensor(const char * name, void * addr, size_t size,
                                                int layer, int n_experts) {
    (void) name;  // name kept for interface symmetry with register_tensor
    if (layer < 0 || addr == nullptr || size == 0 || n_experts <= 1) return;
    if ((size_t)layer >= expert_tensors_by_layer_.size()) {
        expert_tensors_by_layer_.resize(layer + 1);
    }
    expert_tensors_by_layer_[layer].push_back({addr, size / (size_t)n_experts, n_experts});
}

void prefetch_scheduler::cache_router_experts(int layer, const int * experts, int n) {
    if (layer < 0 || experts == nullptr || n <= 0) return;
    std::lock_guard<std::mutex> lk(mtx_);
    if ((size_t)layer >= cached_experts_by_layer_.size()) {
        cached_experts_by_layer_.resize(layer + 1);
    }
    cached_experts_by_layer_[layer].assign(experts, experts + n);
}

const int * prefetch_scheduler::get_cached_experts(int layer, int * n) const {
    if (n) *n = 0;
    if (layer < 0 || (size_t)layer >= cached_experts_by_layer_.size()) return nullptr;
    const auto & v = cached_experts_by_layer_[layer];
    if (v.empty()) return nullptr;
    if (n) *n = (int) v.size();
    return v.data();
}

void prefetch_scheduler::prefetch_experts(int layer, const int * experts, int n) {
    if (!enabled_.load()) return;
    if (layer < 0 || experts == nullptr || n <= 0) return;
    if ((size_t)layer >= expert_tensors_by_layer_.size()) return;
    size_t bytes_this_round = 0;
    std::lock_guard<std::mutex> lk(mtx_);
    for (const auto & et : expert_tensors_by_layer_[layer]) {
        if (et.base_addr == nullptr || et.per_expert_size == 0) continue;
        for (int i = 0; i < n; ++i) {
            int eid = experts[i];
            if (eid < 0 || eid >= et.n_experts) continue;
            void * eaddr = (uint8_t *) et.base_addr + (size_t) eid * et.per_expert_size;
            (void) posix_madvise(eaddr, et.per_expert_size, POSIX_MADV_WILLNEED);
            bytes_this_round += et.per_expert_size;
        }
    }
    total_bytes_.fetch_add(bytes_this_round);
    total_calls_.fetch_add(1);
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

        // Prefetch layers [target+1, target+window]
        size_t bytes_this_round = 0;
        for (int w = 1; w <= window_; ++w) {
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
