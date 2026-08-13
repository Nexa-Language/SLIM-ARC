// SLIM-ARC: Tensor-level asynchronous prefetch scheduler
//
// Implements layer-ahead prefetch on top of upstream llama.cpp's mmap.
// When computing layer N, async madvise(WILLNEED) for layers N+1..N+window.

#include "slim-arc-prefetch.h"

#include "slim-arc-expert-reclaim.h"
#include "slim-arc-page-range.h"

#include <algorithm>
#include <charconv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string_view>
#include <sys/mman.h>
#include <system_error>
#include <unistd.h>

namespace slim_arc {

namespace {
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

int parse_popularity_k(const char * raw) noexcept {
    if (raw == nullptr) return 0;
    const std::string_view value{raw};
    if (value.empty()) return 0;
    int parsed{0};
    const auto result = std::from_chars(value.data(), value.data() + value.size(), parsed);
    if (result.ec != std::errc{} || result.ptr != value.data() + value.size() || parsed < 0 || parsed > 64) {
        std::fprintf(stderr, "SLIM-ARC: invalid SLIM_ARC_EXPERT_POP; expected an integer in [0,64]\n");
        return 0;
    }
    return parsed;
}

int system_advice(void * address, size_t length, int advice) {
    return posix_madvise(address, length, advice);
}

long system_page_size() {
    return sysconf(_SC_PAGESIZE);
}

uint32_t ratio_permille(uint64_t numerator, uint64_t denominator) noexcept {
    if (denominator == 0 || numerator == 0) return 0;
    if (numerator >= denominator) return 1000;
    uint32_t low = 0;
    uint32_t high = 1000;
    while (low < high) {
        const uint32_t middle = low + (high - low + 1) / 2;
        const uint64_t whole = (denominator / 1000) * middle;
        const uint64_t remainder_product = (denominator % 1000) * middle;
        const uint64_t threshold = whole + (remainder_product + 999) / 1000;
        if (numerator >= threshold) {
            low = middle;
        } else {
            high = middle - 1;
        }
    }
    return low;
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

void prefetch_scheduler::set_phase(compute_phase phase) {
    if (stop_.load()) return;
    phase_.store(phase);
    const char * dyn = getenv("SLIM_ARC_DYNAMIC_MADV");
    if (dyn != nullptr && std::strcmp(dyn, "0") == 0) return;
    int advice = POSIX_MADV_SEQUENTIAL;
    if (phase == compute_phase::DECODE) {
        // SLIM-ARC FIX 2026-08-07: decode 阶段建议可配置（消融实验结论：RK3588
        // 45GB/8GB 极端比例下 RANDOM 反而拖慢 decode 5.4x，故默认改为 SEQUENTIAL，
        // 保留内核顺序预读以利用 SSD 顺序带宽；SLIM_ARC_DECODE_MADV=RANDOM/NORMAL
        // 可覆盖。内存相对充足（模型可部分常驻）的场景才适合 RANDOM）。
        const char * dec = getenv("SLIM_ARC_DECODE_MADV");
        if (dec != nullptr && std::strcmp(dec, "RANDOM") == 0) {
            advice = POSIX_MADV_RANDOM;
        } else if (dec != nullptr && std::strcmp(dec, "NORMAL") == 0) {
            advice = POSIX_MADV_NORMAL;
        }
    }
    std::vector<std::pair<void *, size_t>> regions;
    {
        std::lock_guard<std::mutex> lock(mtx_);
        regions = mmap_regions_;
    }
    for (const auto & region : regions) {
        (void) advice_(region.first, region.second, advice);
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

prefetch_scheduler::prefetch_scheduler(
    int n_threads,
    int window,
    std::function<void()> request_claim_hook,
    advice_fn advice,
    page_size_query_fn page_size_query)
    : n_threads_(std::max(1, n_threads))
    , window_(std::max(1, window))
    , request_claim_hook_(std::move(request_claim_hook))
    , advice_(advice ? std::move(advice) : advice_fn{system_advice})
    , page_size_query_(page_size_query ? std::move(page_size_query) : page_size_query_fn{system_page_size})
    , reclaim_waste_enabled_([] {
        const char * const value = std::getenv("SLIM_ARC_EXPERT_RECLAIM_WASTE");
        return value != nullptr && std::strcmp(value, "1") == 0;
    }())
    , expert_residency_enabled_([] {
        const char * const value = std::getenv("SLIM_ARC_EXPERT_RESIDENCY");
        return value != nullptr && std::strcmp(value, "1") == 0;
    }()) {
    const char * confidence = std::getenv("SLIM_ARC_EXPERT_CONF");
    conf_gating_ = confidence != nullptr && std::strcmp(confidence, "1") == 0;
    pop_k_ = parse_popularity_k(std::getenv("SLIM_ARC_EXPERT_POP"));
    workers_.reserve(n_threads_);
    for (int i = 0; i < n_threads_; ++i) {
        workers_.emplace_back([this] { worker_loop(); });
    }
}

prefetch_scheduler::~prefetch_scheduler() {
    shutdown();
    dump_metrics();
}

void prefetch_scheduler::shutdown() noexcept {
    std::lock_guard<std::mutex> shutdown_lock(shutdown_mtx_);
    {
        std::lock_guard<std::mutex> lk(mtx_);
        if (stop_.load()) return;
        enabled_.store(false);
        stop_.store(true);
        pending_requests_.clear();
    }
    cv_.notify_all();
    for (auto & t : workers_) {
        if (t.joinable()) t.join();
    }
}

void prefetch_scheduler::register_tensor(const char *, void * addr, size_t size, int layer) {
    if (layer < 0 || addr == nullptr || size == 0) return;
    std::lock_guard<std::mutex> lock(mtx_);
    if (stop_.load()) return;
    if ((size_t)layer >= tensors_by_layer_.size()) {
        tensors_by_layer_.resize(layer + 1);
    }
    tensors_by_layer_[layer].push_back({addr, size, layer, 0});
}

bool prefetch_scheduler::register_mapping(void * addr, size_t size) {
    if (addr == nullptr || size == 0) return false;
    {
        std::lock_guard<std::mutex> lock(mtx_);
        if (stop_.load()) return false;
        mmap_regions_.emplace_back(addr, size);
    }
    const char * dyn = std::getenv("SLIM_ARC_DYNAMIC_MADV");
    if (dyn == nullptr || std::strcmp(dyn, "0") != 0) {
        (void) advice_(addr, size, POSIX_MADV_SEQUENTIAL);
    }
    return true;
}

void prefetch_scheduler::notify_layer_compute(int current_layer) {
    if (!enabled_.load()) return;
    {
        std::lock_guard<std::mutex> lk(mtx_);
        if (stop_.load()) return;
        if (pending_requests_.size() == max_pending_requests) {
            pending_requests_.pop_front();
            atomic_saturating_add(dropped_requests_, uint64_t{1});
        }
        if (next_request_generation_ == std::numeric_limits<uint64_t>::max()) {
            atomic_saturating_add(dropped_requests_, uint64_t{1});
            return;
        }
        pending_requests_.push_back({++next_request_generation_, current_layer});
    }
    cv_.notify_one();
}

size_t prefetch_scheduler::pending_request_count() const {
    std::lock_guard<std::mutex> lock(mtx_);
    return pending_requests_.size();
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
        int target_layer;
        std::vector<tensor_prefetch_info> items;
        {
            std::unique_lock<std::mutex> lk(mtx_);
            cv_.wait(lk, [this] { return stop_.load() || !pending_requests_.empty(); });
            if (stop_) return;
            const prefetch_request request = pending_requests_.front();
            pending_requests_.pop_front();
            target_layer = request.layer;
            for (int w = 1; w <= window_; ++w) {
                const int layer = target_layer + w;
                if (layer < 0 || static_cast<size_t>(layer) >= tensors_by_layer_.size()) continue;
                for (const auto & tensor : tensors_by_layer_[layer]) {
                    if (tensor.addr != nullptr && tensor.size > 0) items.push_back(tensor);
                }
            }
        }
        if (request_claim_hook_) request_claim_hook_();
        std::vector<size_t> item_sizes;
        item_sizes.reserve(items.size());
        for (const auto & item : items) item_sizes.push_back(item.size);

        uint64_t requested{0};
        uint64_t skipped{0};
        const uint64_t budget = memory_budget_.load();
        const auto selected = select_prefetch_items(item_sizes, budget, &requested, &skipped);
        uint64_t issued{0};
        uint64_t failures{0};
        // SLIM-ARC FIX 2026-08-13: posix_madvise 要求页对齐地址。GGUF 张量地址通常
        // 带 2KB 偏移，直接对原始张量地址下发 WILLNEED 会 EINVAL，预取完全失效
        // （issued=0 回归）。先取内部整页区间（与 reclaim 路径同一规则）。
        const long raw_page_size = page_size_query_();
        const size_t page_size =
            raw_page_size > 0 ? static_cast<size_t>(raw_page_size) : 4096;
        for (const size_t index : selected) {
            const tensor_prefetch_info & tensor = items[index];
            const page_range range = interior_page_range(
                reinterpret_cast<uintptr_t>(tensor.addr), tensor.size, page_size);
            if (!range.valid || range.length == 0) {
                ++failures;
                continue;
            }
            void * const addr = reinterpret_cast<void *>(range.address);
            if (advice_(addr, range.length, POSIX_MADV_WILLNEED) == 0) {
                issued = saturating_add(issued, static_cast<uint64_t>(range.length));
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
    if (stop_.load()) return;
    std::vector<int> current;
    current.reserve(static_cast<size_t>(n));
    for (int i = 0; i < n; ++i) {
        append_unique_nonnegative(current, expert_ids[i]);
    }

    std::vector<int> prefetched;
    std::vector<expert_tensor_info> reclaim_tensors;
    {
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
                if (reclaim_waste_enabled_ && enabled_.load()) {
                    prefetched = it->expert_ids;
                    if (static_cast<size_t>(layer) < experts_by_layer_.size()) {
                        reclaim_tensors = experts_by_layer_[layer];
                    }
                }
                atomic_saturating_add(expert_hit_bytes_, hit_bytes);
                atomic_saturating_add(expert_waste_bytes_, waste_bytes);
                const uint64_t accounted = saturating_add(
                    static_cast<uint64_t>(hit_bytes), static_cast<uint64_t>(waste_bytes));
                if (accounted > 0) {
                    const uint32_t sample_milli = ratio_permille(static_cast<uint64_t>(waste_bytes), accounted);
                    expert_waste_ewma_milli_ = update_waste_ewma_milli(
                        expert_waste_ewma_milli_, sample_milli, expert_waste_ewma_initialized_);
                    expert_waste_ewma_initialized_ = true;
                    expert_waste_samples_ = saturating_add(expert_waste_samples_, uint64_t{1});
                    expert_waste_restricted_ = expert_waste_controller_.update(sample_milli);
                }
                pending.erase(it);
            } else {
                atomic_saturating_add(expert_unmatched_generations_, uint64_t{1});
            }
        } else if (generation != 0) {
            atomic_saturating_add(expert_unmatched_generations_, uint64_t{1});
        }
        atomic_saturating_add(router_samples_, uint64_t{1});
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
                expert_pop_counts_[layer][eid] = saturating_increment_popularity(expert_pop_counts_[layer][eid]);
            }
        }
        if (expert_residency_enabled_ && !current.empty()) ++popularity_samples_since_decay_;
        if (expert_residency_enabled_ && popularity_samples_since_decay_ == 64) {
            popularity_samples_since_decay_ = 0;
            for (auto & layer_counts : expert_pop_counts_) {
                for (uint32_t & count : layer_counts) count /= 2;
            }
            atomic_saturating_add(popularity_decay_count_, uint64_t{1});
        }
        cached_router_experts_[layer] = current;
    }
    if (!prefetched.empty()) {
        reclaim_wrong_expert_pages(prefetched, current, reclaim_tensors);
    }
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

expert_reclaim_stats prefetch_scheduler::expert_reclaim_statistics() const {
    return {
        reclaim_candidate_experts_.load(),
        reclaim_calls_.load(),
        reclaim_reclaimed_bytes_.load(),
        reclaim_skipped_bytes_.load(),
        reclaim_madvise_failures_.load(),
        reclaim_invalid_layouts_.load(),
        reclaim_invalid_ids_.load(),
    };
}

void prefetch_scheduler::set_expert_residency_pressure(
    expert_pressure_state pressure, size_t budget_bytes) {
    if (!expert_residency_enabled_) return;
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    expert_residency_budget_ = budget_bytes;
    expert_pressure_ = pressure;
    expert_residency_snapshot_set_ = true;
}

expert_pressure_state prefetch_scheduler::current_expert_pressure() const {
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    return expert_pressure_;
}

expert_residency_runtime_stats prefetch_scheduler::expert_residency_statistics() const noexcept {
    return {
        residency_samples_.load(),
        residency_admitted_experts_.load(),
        residency_admitted_bytes_.load(),
        residency_skipped_bytes_.load(),
        residency_fallbacks_.load(),
        residency_pressure_missing_.load(),
        residency_pressure_normal_.load(),
        residency_pressure_high_.load(),
        residency_pressure_critical_.load(),
    };
}

expert_runtime_metrics prefetch_scheduler::expert_runtime_statistics() const noexcept {
    return {
        router_samples_.load(),
        static_cast<uint64_t>(expert_prefetch_bytes_.load()),
        static_cast<uint64_t>(expert_hit_bytes_.load()),
        static_cast<uint64_t>(expert_waste_bytes_.load()),
    };
}

std::vector<uint32_t> prefetch_scheduler::expert_popularity_snapshot(int layer) const {
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    if (layer < 0 || static_cast<size_t>(layer) >= expert_pop_counts_.size()) return {};
    return expert_pop_counts_[layer];
}

uint32_t prefetch_scheduler::expert_waste_ewma_milli() const {
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    return expert_waste_ewma_milli_;
}

uint64_t prefetch_scheduler::expert_waste_sample_count() const {
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    return expert_waste_samples_;
}

bool prefetch_scheduler::expert_waste_restricted() const {
    std::lock_guard<std::mutex> lock(expert_state_mtx_);
    return expert_waste_restricted_;
}

void prefetch_scheduler::reclaim_wrong_expert_pages(
    const std::vector<int> & prefetched,
    const std::vector<int> & selected,
    const std::vector<expert_tensor_info> & tensors) {
    if (!reclaim_waste_enabled_ || !enabled_.load()) return;

    const std::vector<int> wasted = wasted_expert_ids(prefetched, selected);
    atomic_saturating_add(reclaim_candidate_experts_, static_cast<uint64_t>(wasted.size()));
    if (wasted.empty()) return;

    const long raw_page_size = page_size_query_();
    if (raw_page_size <= 0) {
        atomic_saturating_add(reclaim_invalid_layouts_, uint64_t{1});
        return;
    }

    std::vector<expert_tensor_view> tensor_views;
    tensor_views.reserve(tensors.size());
    for (const expert_tensor_info & tensor : tensors) {
        tensor_views.push_back({reinterpret_cast<uintptr_t>(tensor.addr), tensor.size, tensor.n_experts});
    }
    const expert_reclaim_plan plan = build_expert_reclaim_plan(
        tensor_views, wasted, static_cast<size_t>(raw_page_size));
    atomic_saturating_add(reclaim_skipped_bytes_, plan.skipped_bytes);
    atomic_saturating_add(reclaim_invalid_layouts_, plan.invalid_layouts);
    atomic_saturating_add(reclaim_invalid_ids_, plan.invalid_ids);

    for (const expert_reclaim_item & item : plan.items) {
        if (!enabled_.load()) return;
        if (item.length == 0) continue;
        atomic_saturating_add(reclaim_calls_, uint64_t{1});
        if (advice_(reinterpret_cast<void *>(item.address), item.length, POSIX_MADV_DONTNEED) == 0) {
            atomic_saturating_add(reclaim_reclaimed_bytes_, static_cast<uint64_t>(item.length));
        } else {
            atomic_saturating_add(reclaim_madvise_failures_, uint64_t{1});
        }
    }
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
    std::vector<uint32_t> population;
    expert_pressure_state pressure = expert_pressure_state::missing;
    uint64_t policy_budget = std::numeric_limits<uint64_t>::max();
    bool residency_snapshot_set = false;
    uint32_t waste_ewma = 0;
    bool waste_restricted = false;
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
        pressure = expert_pressure_;
        residency_snapshot_set = expert_residency_snapshot_set_;
        if (residency_snapshot_set) policy_budget = expert_residency_budget_;
        waste_ewma = expert_waste_ewma_milli_;
        waste_restricted = expert_waste_restricted_;
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
        std::vector<std::pair<int, uint32_t>> rank;
        for (int eid = 0; eid < static_cast<int>(population.size()); ++eid) {
            if (population[eid] > 0) rank.emplace_back(eid, population[eid]);
        }
        std::sort(rank.begin(), rank.end(),
                  [](const auto & a, const auto & b) { return a.second > b.second; });
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

    if (expert_residency_enabled_) {
        if (!residency_snapshot_set && expert_budget_enabled_.load()) {
            policy_budget = expert_budget_.load();
        }

        std::vector<int> candidate_ids = target;
        if (pressure != expert_pressure_state::missing) {
            candidate_ids = requested;
            std::vector<std::pair<int, uint32_t>> rank;
            for (int eid = 0; eid < static_cast<int>(population.size()); ++eid) {
                if (population[eid] > 0) rank.emplace_back(eid, population[eid]);
            }
            std::stable_sort(rank.begin(), rank.end(), [](const auto & left, const auto & right) {
                return left.second > right.second;
            });
            for (const auto & [eid, unused] : rank) {
                (void) unused;
                append_unique_nonnegative(candidate_ids, eid);
            }
        }

        size_t available_experts = 0;
        std::vector<expert_candidate> candidates;
        candidates.reserve(candidate_ids.size());
        uint64_t minimum_bytes = std::numeric_limits<uint64_t>::max();
        for (const expert_tensor_info & expert : exps) {
            if (expert.addr != nullptr && expert.n_experts > 0 &&
                expert.size % static_cast<size_t>(expert.n_experts) == 0) {
                available_experts = std::max(available_experts, static_cast<size_t>(expert.n_experts));
            }
        }
        for (const int eid : candidate_ids) {
            uint64_t bytes = 0;
            for (const expert_tensor_info & expert : exps) {
                if (expert.addr == nullptr || expert.n_experts <= 0 || eid >= expert.n_experts ||
                    expert.size % static_cast<size_t>(expert.n_experts) != 0) continue;
                bytes = saturating_add(bytes, static_cast<uint64_t>(
                    expert.size / static_cast<size_t>(expert.n_experts)));
            }
            if (bytes > 0) minimum_bytes = std::min(minimum_bytes, bytes);
            const uint32_t popularity = eid >= 0 && static_cast<size_t>(eid) < population.size()
                ? population[static_cast<size_t>(eid)] : 0;
            candidates.push_back({
                eid,
                bytes,
                popularity,
                std::find(requested.begin(), requested.end(), eid) != requested.end() &&
                    std::find(prev.begin(), prev.end(), eid) != prev.end(),
                std::find(requested.begin(), requested.end(), eid) != requested.end(),
            });
        }

        size_t max_experts = pressure == expert_pressure_state::missing ? target.size() : candidates.size();
        max_experts = std::min(max_experts, available_experts);
        max_experts = std::min(max_experts, candidates.size());
        if (minimum_bytes == std::numeric_limits<uint64_t>::max() || minimum_bytes == 0) {
            max_experts = 0;
        } else {
            const uint64_t budget_count = policy_budget / minimum_bytes;
            max_experts = std::min<uint64_t>(max_experts, budget_count);
        }

        const expert_residency_decision decision = select_resident_experts({
            pressure,
            policy_budget,
            max_experts,
            waste_ewma,
            std::move(candidates),
            waste_restricted,
        });
        atomic_saturating_add(residency_samples_, uint64_t{1});
        atomic_saturating_add(residency_admitted_experts_, static_cast<uint64_t>(decision.expert_ids.size()));
        atomic_saturating_add(residency_admitted_bytes_, decision.admitted_bytes);
        atomic_saturating_add(residency_skipped_bytes_, decision.skipped_bytes);
        if (decision.fallback) atomic_saturating_add(residency_fallbacks_, uint64_t{1});
        switch (pressure) {
            case expert_pressure_state::missing:
                atomic_saturating_add(residency_pressure_missing_, uint64_t{1});
                break;
            case expert_pressure_state::normal:
                atomic_saturating_add(residency_pressure_normal_, uint64_t{1});
                break;
            case expert_pressure_state::high:
                atomic_saturating_add(residency_pressure_high_, uint64_t{1});
                break;
            case expert_pressure_state::critical:
                atomic_saturating_add(residency_pressure_critical_, uint64_t{1});
                break;
        }
        target = std::move(decision.expert_ids);
    }
    if (target.empty()) return 0;
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

    const long raw_page_size = page_size_query_();
    const size_t page_size =
        raw_page_size > 0 ? static_cast<size_t>(raw_page_size) : 4096;
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
            // SLIM-ARC FIX 2026-08-13: posix_madvise 要求页对齐地址；专家切片继承
            // GGUF 张量的未对齐偏移，直接对切片地址下发 WILLNEED 会 EINVAL，
            // 导致 issued=0 回归。与 reclaim 路径一致，取内部整页区间下发。
            const page_range range = interior_page_range(address, per_expert, page_size);
            if (!range.valid || range.length == 0) continue;
            void * const addr = reinterpret_cast<void *>(range.address);
            if (advice_(addr, range.length, POSIX_MADV_WILLNEED) == 0) {
                expert_bytes = saturating_add(expert_bytes, range.length);
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
            "[SLIM-ARC-METRICS] expert prefetch: samples=%llu issued=%.1fMB "
            "hit=%.1fMB waste=%.1fMB hit_rate=%.2f%% (accounted %.1fMB)\n",
            static_cast<unsigned long long>(router_samples_.load()),
            issued / 1048576.0, hit / 1048576.0, waste / 1048576.0, hr,
            total / 1048576.0);
}

} // namespace slim_arc
