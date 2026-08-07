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

// SLIM-ARC FIX 2026-08-05: mmap 区域注册表（供动态 MADV 切换；当前仅记录）。
std::mutex g_mmap_mtx;
std::vector<std::pair<void *, size_t>> g_mmap_regions;
}

prefetch_scheduler * get_global_prefetch_scheduler() { return g_scheduler; }
void set_global_prefetch_scheduler(prefetch_scheduler * s) { g_scheduler = s; }

// SLIM-ARC FIX 2026-08-05: 记录 mmap 区域，供未来动态 MADV 切换使用。
void register_mmap_region(void * addr, size_t size) {
    std::lock_guard<std::mutex> lk(g_mmap_mtx);
    if (addr && size > 0) {
        g_mmap_regions.emplace_back(addr, size);
    }
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

// ---- SLIM-ARC FIX 2026-08-05: Phase 2a MoE expert prefetch ----
void prefetch_scheduler::register_expert_tensor(const char * name, void * addr, size_t size, int layer, int n_experts) {
    (void) name;
    if (addr == nullptr || size == 0 || n_experts < 1 || layer < 0) return;
    if ((size_t)layer >= experts_by_layer_.size()) {
        experts_by_layer_.resize(layer + 1);
    }
    experts_by_layer_[layer].push_back({addr, size, n_experts});
}

void prefetch_scheduler::cache_router_experts(int layer, const int * expert_ids, int n) {
    if (layer < 0 || expert_ids == nullptr || n <= 0) return;
    if ((size_t)layer >= cached_router_experts_.size()) {
        cached_router_experts_.resize(layer + 1);
    }
    cached_router_experts_[layer].assign(expert_ids, expert_ids + n);
}

const int * prefetch_scheduler::get_cached_experts(int layer, int * n) const {
    if (n) *n = 0;
    if (layer < 0 || (size_t)layer >= cached_router_experts_.size()) return nullptr;
    const auto & v = cached_router_experts_[layer];
    if (v.empty()) return nullptr;
    if (n) *n = (int) v.size();
    return v.data();
}

void prefetch_scheduler::prefetch_experts(int layer, const int * expert_ids, int n) {
    issue_expert_willneed(layer, expert_ids, n);
}

void prefetch_scheduler::issue_expert_willneed(int layer, const int * expert_ids, int n) {
    if (!enabled_.load()) return;
    if (layer < 0 || expert_ids == nullptr || n <= 0) return;
    if ((size_t)layer >= experts_by_layer_.size()) return;
    const auto & exps = experts_by_layer_[layer];
    if (exps.empty()) return;

    size_t bytes = 0;
    for (const auto & e : exps) {
        size_t per_expert = e.size / (size_t) e.n_experts;
        if (per_expert == 0) continue;
        for (int i = 0; i < n; ++i) {
            int eid = expert_ids[i];
            if (eid < 0 || eid >= e.n_experts) continue;
            size_t off = (size_t) eid * per_expert;
            (void) posix_madvise((uint8_t *) e.addr + off, per_expert, POSIX_MADV_WILLNEED);
            bytes += per_expert;
        }
    }
    if (bytes > 0) {
        total_bytes_.fetch_add(bytes);
    }
}

} // namespace slim_arc
