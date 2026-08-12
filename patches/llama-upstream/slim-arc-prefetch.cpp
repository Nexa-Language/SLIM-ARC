// SLIM-ARC: Tensor-level asynchronous prefetch scheduler
//
// Implements layer-ahead prefetch on top of upstream llama.cpp's mmap.
// When computing layer N, async madvise(WILLNEED) for layers N+1..N+window.

#include "slim-arc-prefetch.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <limits>
#include <sys/mman.h>

namespace slim_arc {

namespace {
prefetch_scheduler * g_scheduler = nullptr;

// SLIM-ARC FIX 2026-08-05: mmap 区域注册表（供动态 MADV 切换；当前仅记录）。
std::mutex g_mmap_mtx;
std::vector<std::pair<void *, size_t>> g_mmap_regions;

template <typename T>
T saturating_add(T left, T right) noexcept {
    const T maximum = std::numeric_limits<T>::max();
    return right > maximum - left ? maximum : left + right;
}

template <typename T>
void atomic_saturating_add(std::atomic<T> & target, T increment) noexcept {
    T current = target.load();
    while (!target.compare_exchange_weak(current, saturating_add(current, increment))) {
    }
}

void append_unique_nonnegative(std::vector<int> & ids, int id) {
    if (id >= 0 && std::find(ids.begin(), ids.end(), id) == ids.end()) {
        ids.push_back(id);
    }
}
}

std::vector<size_t> select_prefetch_items(
    const std::vector<size_t> & item_sizes,
    uint64_t budget_bytes,
    uint64_t * requested_bytes,
    uint64_t * skipped_bytes) {
    uint64_t requested{0};
    uint64_t skipped{0};
    uint64_t remaining = budget_bytes;
    std::vector<size_t> selected;
    selected.reserve(item_sizes.size());
    for (size_t index = 0; index < item_sizes.size(); ++index) {
        const uint64_t size = item_sizes[index];
        requested = saturating_add(requested, size);
        if (size > 0 && size <= remaining) {
            selected.push_back(index);
            remaining -= size;
        } else {
            skipped = saturating_add(skipped, size);
        }
    }
    if (requested_bytes != nullptr) {
        *requested_bytes = requested;
    }
    if (skipped_bytes != nullptr) {
        *skipped_bytes = skipped;
    }
    return selected;
}

prefetch_scheduler * get_global_prefetch_scheduler() { return g_scheduler; }
void set_global_prefetch_scheduler(prefetch_scheduler * s) { g_scheduler = s; }

// SLIM-ARC FIX 2026-08-05: 记录 mmap 区域，供动态 MADV 切换使用。
// SLIM-ARC FIX 2026-08-07: 启用动态 MADV 阶段切换。
//   加载时初始设为 MADV_SEQUENTIAL（保住 prefill 顺序预读，消除端侧负优化），
//   后续由 set_phase() 在 decode 阶段切换到 MADV_RANDOM（按需加载 MoE 专家页）。
//   通过环境变量 SLIM_ARC_DYNAMIC_MADV 控制（默认启用）；设 0 则回退到旧的
//   静态全量 MADV_RANDOM 行为。
void register_mmap_region(void * addr, size_t size) {
    std::lock_guard<std::mutex> lk(g_mmap_mtx);
    if (addr && size > 0) {
        g_mmap_regions.emplace_back(addr, size);
        const char * dyn = getenv("SLIM_ARC_DYNAMIC_MADV");
        bool dynamic = dyn == nullptr || std::strcmp(dyn, "0") != 0;
        // 动态模式：初始用 SEQUENTIAL（prefill 顺序访问受益）
        if (dynamic) {
            (void) posix_madvise(addr, size, POSIX_MADV_SEQUENTIAL);
        }
    }
}

// SLIM-ARC FIX 2026-08-07: 对所有已注册 mmap 区域设置指定 MADV 建议。
// 供 set_phase() 在 prefill/decode 阶段切换时调用。
static void apply_madvice_to_regions(int advice) {
    std::lock_guard<std::mutex> lk(g_mmap_mtx);
    for (const auto & r : g_mmap_regions) {
        if (r.first && r.second > 0) {
            (void) posix_madvise(r.first, r.second, advice);
        }
    }
}

// SLIM-ARC FIX 2026-08-07: 动态 MADV 阶段切换。
//   PREFILL -> MADV_SEQUENTIAL（顺序预读，加速 prefill）
//   DECODE  -> MADV_RANDOM（按需分页，MoE 专家随机访问）
//   由 graph_compute 的 set_phase() 调用。SLIM_ARC_DYNAMIC_MADV=0 时禁用。
void apply_dynamic_madv(compute_phase phase) {
    const char * dyn = getenv("SLIM_ARC_DYNAMIC_MADV");
    if (dyn != nullptr && std::strcmp(dyn, "0") == 0) return;
    if (phase == compute_phase::PREFILL) {
        apply_madvice_to_regions(POSIX_MADV_SEQUENTIAL);
    } else {
        // SLIM-ARC FIX 2026-08-07: decode 阶段建议可配置（消融实验结论：RK3588
        // 45GB/8GB 极端比例下 RANDOM 反而拖慢 decode 5.4x，故默认改为 SEQUENTIAL，
        // 保留内核顺序预读以利用 SSD 顺序带宽；SLIM_ARC_DECODE_MADV=RANDOM/NORMAL
        // 可覆盖。内存相对充足（模型可部分常驻）的场景才适合 RANDOM）。
        const char * dec = getenv("SLIM_ARC_DECODE_MADV");
        int advice = POSIX_MADV_SEQUENTIAL;
        if (dec != nullptr && std::strcmp(dec, "RANDOM") == 0) {
            advice = POSIX_MADV_RANDOM;
        } else if (dec != nullptr && std::strcmp(dec, "NORMAL") == 0) {
            advice = POSIX_MADV_NORMAL;
        }
        apply_madvice_to_regions(advice);
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
    // SLIM-ARC FIX 2026-08-09: 置信度门控开关（改进 2，文献 CommitMoE/DALI 思路）
    conf_gating_ = getenv("SLIM_ARC_EXPERT_CONF") != nullptr;
    // SLIM-ARC FIX 2026-08-09: 热门专家组合（改进 4，文献 ReMoE/DALI locality）
    const char * pop = getenv("SLIM_ARC_EXPERT_POP");
    if (pop != nullptr) pop_k_ = atoi(pop);
}

prefetch_scheduler::~prefetch_scheduler() {
    // SLIM-ARC FIX 2026-08-09: 退出时输出专家预取指标（改进 1）
    dump_metrics();
    {
        std::lock_guard<std::mutex> lk(mtx_);
        stop_ = true;
    }
    cv_.notify_all();
    for (auto & t : workers_) {
        if (t.joinable()) t.join();
    }
}

void prefetch_scheduler::register_tensor(const char *, void * addr, size_t size, int layer) {
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

prefetch_budget_stats prefetch_scheduler::budget_stats() const {
    return {
        budget_requested_bytes_.load(),
        budget_issued_bytes_.load(),
        budget_skipped_bytes_.load(),
        budget_rounds_throttled_.load(),
        budget_madvise_failures_.load(),
    };
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

        std::vector<const tensor_prefetch_info *> items;
        std::vector<size_t> item_sizes;
        for (int w = 1; w <= window_; ++w) {
            int layer = target_layer + w;
            if (layer < 0 || (size_t)layer >= tensors_by_layer_.size()) continue;
            for (const auto & t : tensors_by_layer_[layer]) {
                if (t.addr == nullptr || t.size == 0) continue;
                items.push_back(&t);
                item_sizes.push_back(t.size);
            }
        }

        uint64_t requested{0};
        uint64_t skipped{0};
        const uint64_t budget = memory_budget_.load();
        const auto selected = select_prefetch_items(item_sizes, budget, &requested, &skipped);
        uint64_t issued{0};
        uint64_t failures{0};
        for (const size_t index : selected) {
            const tensor_prefetch_info & tensor = *items[index];
            if (posix_madvise(tensor.addr, tensor.size, POSIX_MADV_WILLNEED) == 0) {
                issued = saturating_add(issued, static_cast<uint64_t>(tensor.size));
            } else {
                ++failures;
            }
        }

        atomic_saturating_add(budget_requested_bytes_, requested);
        atomic_saturating_add(budget_issued_bytes_, issued);
        atomic_saturating_add(budget_skipped_bytes_, skipped);
        atomic_saturating_add(budget_madvise_failures_, failures);
        if (skipped > 0) {
            atomic_saturating_add(budget_rounds_throttled_, uint64_t{1});
        }
        total_bytes_.fetch_add(static_cast<size_t>(issued));
        total_calls_.fetch_add(1);
    }
}

// ---- SLIM-ARC FIX 2026-08-05: Phase 2a MoE expert prefetch ----
void prefetch_scheduler::register_expert_tensor(const char *, void * addr, size_t size, int layer, int n_experts) {
    if (addr == nullptr || size == 0 || n_experts < 1 || layer < 0) return;
    if (size % static_cast<size_t>(n_experts) != 0) return;
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    if ((size_t)layer >= experts_by_layer_.size()) {
        experts_by_layer_.resize(layer + 1);
    }
    experts_by_layer_[layer].push_back({addr, size, n_experts});
}

void prefetch_scheduler::cache_router_experts(int layer, const int * expert_ids, int n) {
    cache_router_experts(layer, expert_ids, n, 0);
}

void prefetch_scheduler::cache_router_experts(
    int layer, const int * expert_ids, int n, uint64_t generation) {
    if (layer < 0 || expert_ids == nullptr || n <= 0) return;
    std::vector<int> current;
    current.reserve(static_cast<size_t>(n));
    for (int i = 0; i < n; ++i) {
        append_unique_nonnegative(current, expert_ids[i]);
    }

    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    if ((size_t)layer >= cached_router_experts_.size()) {
        cached_router_experts_.resize(layer + 1);
    }
    // 每个 router 观察只能结算调用方携带的精确预取代次；token 0 仅更新预测器。
    if (generation != 0 && static_cast<size_t>(layer) < pending_expert_prefetches_.size()) {
        std::vector<expert_prefetch_record> & pending = pending_expert_prefetches_[layer];
        const auto it = std::find_if(pending.begin(), pending.end(), [generation](const auto & record) {
            return record.generation == generation;
        });
        if (it != pending.end()) {
            size_t hit_bytes = 0;
            size_t waste_bytes = 0;
            for (size_t index = 0; index < it->expert_ids.size(); ++index) {
                if (std::find(current.begin(), current.end(), it->expert_ids[index]) != current.end()) {
                    hit_bytes = saturating_add(hit_bytes, it->issued_bytes[index]);
                } else {
                    waste_bytes = saturating_add(waste_bytes, it->issued_bytes[index]);
                }
            }
            atomic_saturating_add(expert_hit_bytes_, hit_bytes);
            atomic_saturating_add(expert_waste_bytes_, waste_bytes);
            pending.erase(it);
        } else {
            atomic_saturating_add(expert_unmatched_generations_, uint64_t{1});
        }
    } else if (generation != 0) {
        atomic_saturating_add(expert_unmatched_generations_, uint64_t{1});
    }
    ++router_samples_;
    // SLIM-ARC FIX 2026-08-09: 2-token 历史滑动（改进 2 门控用）
    // prev = 旧 cached（t-2），cached = 新路由（t-1）
    if ((size_t)layer >= prev_router_experts_.size()) {
        prev_router_experts_.resize(cached_router_experts_.size());
    }
    prev_router_experts_[layer] = cached_router_experts_[layer];
    // SLIM-ARC FIX 2026-08-09: 热门专家频次累加（改进 4）
    if ((size_t)layer >= expert_pop_counts_.size()) {
        expert_pop_counts_.resize(cached_router_experts_.size());
    }
    int n_experts = 0;
    if ((size_t)layer < experts_by_layer_.size()) {
        for (const auto & e : experts_by_layer_[layer]) {
            n_experts = std::max(n_experts, e.n_experts);
        }
    }
    if ((int)expert_pop_counts_[layer].size() < n_experts) {
        expert_pop_counts_[layer].resize(n_experts, 0);
    }
    for (int eid : current) {
        if (eid >= 0 && eid < (int)expert_pop_counts_[layer].size()) {
            expert_pop_counts_[layer][eid]++;
        }
    }
    cached_router_experts_[layer] = std::move(current);
}

void prefetch_scheduler::cancel_expert_prefetch(int layer, uint64_t generation) {
    if (generation == 0) return;

    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    if (layer < 0 || static_cast<size_t>(layer) >= pending_expert_prefetches_.size()) {
        atomic_saturating_add(expert_unmatched_generations_, uint64_t{1});
        return;
    }

    std::vector<expert_prefetch_record> & pending = pending_expert_prefetches_[layer];
    const auto it = std::find_if(pending.begin(), pending.end(), [generation](const auto & record) {
        return record.generation == generation;
    });
    if (it == pending.end()) {
        atomic_saturating_add(expert_unmatched_generations_, uint64_t{1});
        return;
    }

    size_t waste_bytes = 0;
    for (size_t issued_bytes : it->issued_bytes) {
        waste_bytes = saturating_add(waste_bytes, issued_bytes);
    }
    atomic_saturating_add(expert_waste_bytes_, waste_bytes);
    pending.erase(it);
}

std::vector<int> prefetch_scheduler::cached_experts_snapshot(int layer) const {
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    if (layer < 0 || static_cast<size_t>(layer) >= cached_router_experts_.size()) {
        return {};
    }
    return cached_router_experts_[layer];
}

size_t prefetch_scheduler::pending_expert_records(int layer) const {
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    if (layer < 0 || static_cast<size_t>(layer) >= pending_expert_prefetches_.size()) {
        return 0;
    }
    return pending_expert_prefetches_[layer].size();
}

uint64_t prefetch_scheduler::prefetch_experts(int layer, const int * expert_ids, int n) {
    return issue_expert_willneed(layer, expert_ids, n);
}

uint64_t prefetch_scheduler::issue_expert_willneed(int layer, const int * expert_ids, int n) {
    if (!enabled_.load()) return 0;
    if (layer < 0 || expert_ids == nullptr || n <= 0) return 0;

    std::vector<int> requested;
    requested.reserve(static_cast<size_t>(n));
    for (int i = 0; i < n; ++i) {
        append_unique_nonnegative(requested, expert_ids[i]);
    }
    if (requested.empty()) return 0;

    std::vector<expert_tensor_info> exps;
    std::vector<int> prev;
    std::vector<int> population;
    {
        std::lock_guard<std::mutex> lock(expert_state_mtx_);
        if (static_cast<size_t>(layer) >= experts_by_layer_.size()) return 0;
        exps = experts_by_layer_[layer];
        if (static_cast<size_t>(layer) < prev_router_experts_.size()) {
            prev = prev_router_experts_[layer];
        }
        if (static_cast<size_t>(layer) < expert_pop_counts_.size()) {
            population = expert_pop_counts_[layer];
        }
    }
    if (exps.empty()) return 0;

    // SLIM-ARC FIX 2026-08-09: 先构建"实际预取目标集合"。
    // 改进 2（置信度门控，文献 CommitMoE/DALI）：SLIM_ARC_EXPERT_CONF=1 时
    // 仅预取连续两 token 都激活的稳定专家（A_t ∩ A_{t-1}），低置信度不浪费 WILLNEED、
    // 依赖按需分页，减少无效 I/O。
    std::vector<int> target;
    target.reserve(requested.size());
    if (conf_gating_ && !prev.empty()) {
        for (int eid : requested) {
            if (std::find(prev.begin(), prev.end(), eid) != prev.end()) {
                append_unique_nonnegative(target, eid);
            }
        }
    } else {
        for (int eid : requested) {
            append_unique_nonnegative(target, eid);
        }
    }
    // SLIM-ARC FIX 2026-08-09: 改进 4——并集 top-K 热门专家（文献 ReMoE/DALI locality）。
    // 提高覆盖面，减少 miss；SLIM_ARC_EXPERT_POP=K 启用。
    if (pop_k_ > 0 && !population.empty()) {
        std::vector<std::pair<int, int>> rank;
        for (int eid = 0; eid < static_cast<int>(population.size()); ++eid) {
            if (population[eid] > 0) rank.emplace_back(eid, population[eid]);
        }
        std::sort(rank.begin(), rank.end(),
                  [](const std::pair<int, int> & a, const std::pair<int, int> & b) { return a.second > b.second; });
        int added = 0;
        for (const auto & pr : rank) {
            if (added >= pop_k_) break;
            int eid = pr.first;
            if (std::find(target.begin(), target.end(), eid) == target.end()) {
                target.push_back(eid);
                ++added;
            }
        }
    }
    target.erase(std::remove_if(target.begin(), target.end(), [&exps](int eid) {
        return std::none_of(exps.begin(), exps.end(), [eid](const expert_tensor_info & expert) {
            return expert.addr != nullptr && expert.n_experts > 0 &&
                   expert.size % static_cast<size_t>(expert.n_experts) == 0 &&
                   eid < expert.n_experts && expert.size / static_cast<size_t>(expert.n_experts) > 0;
        });
    }), target.end());
    uint64_t generation = 0;
    {
        std::lock_guard<std::mutex> lock(expert_state_mtx_);
        if (next_expert_generation_ == 0 ||
            next_expert_generation_ == std::numeric_limits<uint64_t>::max()) {
            return 0;
        }
        if (static_cast<size_t>(layer) >= pending_expert_prefetches_.size()) {
            pending_expert_prefetches_.resize(static_cast<size_t>(layer) + 1);
        }
        std::vector<expert_prefetch_record> & pending = pending_expert_prefetches_[layer];
        if (pending.size() >= max_pending_expert_records_) {
            atomic_saturating_add(expert_pending_rejected_generations_, uint64_t{1});
            return 0;
        }
        // Reserve the I/O budget only after the bounded pending slot is known
        // available, so a rejected generation cannot consume this step's budget.
        if (expert_budget_enabled_.load()) {
            const size_t budget = expert_budget_.load();
            size_t per_expert_total = 0;
            for (const expert_tensor_info & expert : exps) {
                const size_t item_size = expert.size / static_cast<size_t>(expert.n_experts);
                per_expert_total = saturating_add(per_expert_total, item_size);
            }
            if (budget == 0 || per_expert_total == 0) return 0;

            size_t used = expert_budget_used_.load();
            while (true) {
                if (used >= budget) return 0;
                const size_t capacity = (budget - used) / per_expert_total;
                if (capacity == 0) return 0;
                if (capacity < target.size()) target.resize(capacity);
                if (target.empty()) return 0;
                const size_t reservation = target.size() * per_expert_total;
                if (expert_budget_used_.compare_exchange_weak(used, used + reservation)) {
                    break;
                }
            }
        }
        generation = next_expert_generation_++;
        pending.push_back({generation, {}, {}});
    }

    size_t bytes = 0;
    std::vector<int> issued_experts;
    std::vector<size_t> issued_expert_bytes;
    issued_experts.reserve(target.size());
    issued_expert_bytes.reserve(target.size());
    for (int eid : target) {
        bool issued = false;
        size_t expert_bytes = 0;
        for (const expert_tensor_info & e : exps) {
            if (e.addr == nullptr || e.n_experts <= 0 ||
                e.size % static_cast<size_t>(e.n_experts) != 0) continue;
            const size_t per_expert = e.size / static_cast<size_t>(e.n_experts);
            if (per_expert == 0 || eid >= e.n_experts) continue;
            if (static_cast<size_t>(eid) > std::numeric_limits<size_t>::max() / per_expert) continue;
            const size_t off = static_cast<size_t>(eid) * per_expert;
            const uintptr_t base = reinterpret_cast<uintptr_t>(e.addr);
            if (off > std::numeric_limits<uintptr_t>::max() - base) continue;
            const uintptr_t address = base + off;
            if (per_expert > std::numeric_limits<uintptr_t>::max() - address) continue;
            void * const addr = reinterpret_cast<void *>(address);
            if (posix_madvise(addr, per_expert, POSIX_MADV_WILLNEED) == 0) {
                expert_bytes = saturating_add(expert_bytes, per_expert);
                issued = true;
            }
        }
        if (issued) {
            issued_experts.push_back(eid);
            issued_expert_bytes.push_back(expert_bytes);
            bytes = saturating_add(bytes, expert_bytes);
        }
    }
    {
        std::lock_guard<std::mutex> lock(expert_state_mtx_);
        std::vector<expert_prefetch_record> & pending = pending_expert_prefetches_[layer];
        const auto it = std::find_if(pending.begin(), pending.end(), [generation](const auto & record) {
            return record.generation == generation;
        });
        if (it == pending.end()) {
            atomic_saturating_add(expert_unmatched_generations_, uint64_t{1});
            return 0;
        }
        if (issued_experts.empty()) {
            pending.erase(it);
            return 0;
        }
        it->expert_ids = std::move(issued_experts);
        it->issued_bytes = std::move(issued_expert_bytes);
    }

    if (bytes > 0) {
        atomic_saturating_add(total_bytes_, bytes);
        atomic_saturating_add(expert_prefetch_bytes_, bytes);
    }
    return generation;
}

// SLIM-ARC FIX 2026-08-09: 专家预取可观测性指标汇总（改进 1）。
// issued = 实际 WILLNEED 下发字节（issue 侧）；hit/waste = 命中/浪费（cache 侧，按
// 实际路由对照预取集合）。命中率 = hit/(hit+waste)。两口径因预取/缓存两遍层覆盖
// 不完全一致而可能略有差异，命中率不受影响。
void prefetch_scheduler::dump_metrics() const {
    size_t issued = expert_prefetch_bytes_.load();
    size_t hit    = expert_hit_bytes_.load();
    size_t waste  = expert_waste_bytes_.load();
    size_t total  = saturating_add(hit, waste);
    double hr = total > 0 ? 100.0 * (double) hit / (double) total : 0.0;
    fprintf(stderr,
            "[SLIM-ARC-METRICS] expert prefetch: samples=%d issued=%.1fMB "
            "hit=%.1fMB waste=%.1fMB hit_rate=%.2f%% (accounted %.1fMB)\n",
            router_samples_.load(),
            issued / 1048576.0, hit / 1048576.0, waste / 1048576.0, hr,
            total / 1048576.0);
}

} // namespace slim_arc
