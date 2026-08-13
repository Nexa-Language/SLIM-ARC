// SLIM-ARC: Unified I/O Bandwidth Budget Scheduler Implementation

#include "slim-arc-unified-scheduler.h"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <system_error>
#include <string_view>
#include <utility>

namespace slim_arc {

namespace {
constexpr uint32_t default_reserve_basis_points{1000};

template <typename T>
void atomic_saturating_add(std::atomic<T> & target, T increment) noexcept {
    T current = target.load();
    const T maximum = std::numeric_limits<T>::max();
    while (true) {
        const T updated = increment > maximum - current ? maximum : current + increment;
        if (target.compare_exchange_weak(current, updated)) return;
    }
}

bool parse_mebibytes(const char * raw, uint64_t & bytes) noexcept {
    if (raw == nullptr) {
        return false;
    }
    const std::string_view value{raw};
    if (value.empty()) {
        return false;
    }
    uint64_t mebibytes{0};
    const auto result = std::from_chars(value.data(), value.data() + value.size(), mebibytes);
    if (result.ec != std::errc{} || result.ptr != value.data() + value.size()) {
        return false;
    }
    constexpr uint64_t multiplier{1ULL << 20};
    if (mebibytes > std::numeric_limits<uint64_t>::max() / multiplier) {
        return false;
    }
    bytes = mebibytes * multiplier;
    return true;
}
}

// Static weight ratio table initialization
constexpr double unified_io_scheduler::WEIGHT_RATIOS[5][3];

unified_io_scheduler::unified_io_scheduler(size_t total_budget_bytes,
                                            prefetch_scheduler * weight_prefetcher,
                                            kv_eviction_manager * kv_manager,
                                            pressure_snapshot_provider pressure_provider)
    : total_budget_bytes_(total_budget_bytes)
    , weight_prefetcher_(weight_prefetcher)
    , kv_manager_(kv_manager)
    , pressure_provider_(pressure_provider ? std::move(pressure_provider) : pressure_snapshot_provider{[] {
        return read_cgroup_memory("/sys/fs/cgroup");
    }}) {
    current_budget_.total_bytes = total_budget_bytes;
    pressure_effective_bytes_.store(total_budget_bytes);
    const char * const residency = std::getenv("SLIM_ARC_EXPERT_RESIDENCY");
    expert_residency_enabled_ = residency != nullptr && std::strcmp(residency, "1") == 0;
    const char * const enabled = std::getenv("SLIM_ARC_PRESSURE_ADMISSION");
    if (enabled == nullptr) {
        return;
    }
    if (std::strcmp(enabled, "1") != 0) {
        std::fprintf(stderr, "SLIM-ARC pressure admission disabled: SLIM_ARC_PRESSURE_ADMISSION must equal 1\n");
        return;
    }
    pressure_admission_enabled_ = true;
    const char * const reserve = std::getenv("SLIM_ARC_PRESSURE_RESERVE_MB");
    if (reserve != nullptr && !parse_mebibytes(reserve, pressure_minimum_reserve_bytes_)) {
        std::fprintf(stderr, "SLIM-ARC pressure admission disabled: invalid SLIM_ARC_PRESSURE_RESERVE_MB\n");
        pressure_admission_enabled_ = false;
    }
}

unified_io_scheduler::~unified_io_scheduler() {
    if (weight_prefetcher_ != nullptr) {
        const expert_runtime_metrics expert = weight_prefetcher_->expert_runtime_statistics();
        const prefetch_budget_stats weight = weight_prefetcher_->budget_stats();
        const expert_reclaim_stats reclaim = weight_prefetcher_->expert_reclaim_statistics();
        const expert_residency_runtime_stats residency = weight_prefetcher_->expert_residency_statistics();
        std::fprintf(
            stderr,
            "[SLIM-ARC-RUNTIME] schema=3 expert_samples=%llu expert_issued_bytes=%llu expert_hit_bytes=%llu expert_waste_bytes=%llu expert_advice_requests=%llu expert_coalesced_ranges=%llu expert_covered_bytes=%llu expert_advice_failures=%llu expert_invalid_ranges=%llu weight_requested_bytes=%llu weight_covered_bytes=%llu weight_issued_bytes=%llu weight_skipped_bytes=%llu weight_advice_requests=%llu weight_coalesced_ranges=%llu weight_invalid_ranges=%llu weight_advice_failures=%llu weight_rounds_throttled=%llu weight_stale_requests=%llu weight_stale_bytes=%llu weight_inflight_peak_bytes=%llu reclaim_candidates=%llu reclaim_calls=%llu reclaimed_bytes=%llu reclaim_skipped_bytes=%llu reclaim_failures=%llu residency_samples=%llu residency_admitted_experts=%llu residency_admitted_bytes=%llu residency_skipped_bytes=%llu residency_fallbacks=%llu pressure_normal=%llu pressure_high=%llu pressure_critical=%llu\n",
            static_cast<unsigned long long>(expert.samples),
            static_cast<unsigned long long>(expert.issued_bytes),
            static_cast<unsigned long long>(expert.hit_bytes),
            static_cast<unsigned long long>(expert.waste_bytes),
            static_cast<unsigned long long>(expert.advice_requests),
            static_cast<unsigned long long>(expert.coalesced_ranges),
            static_cast<unsigned long long>(expert.covered_bytes),
            static_cast<unsigned long long>(expert.advice_failures),
            static_cast<unsigned long long>(expert.invalid_ranges),
            static_cast<unsigned long long>(weight.requested_bytes),
            static_cast<unsigned long long>(weight.covered_bytes),
            static_cast<unsigned long long>(weight.issued_bytes),
            static_cast<unsigned long long>(weight.skipped_bytes),
            static_cast<unsigned long long>(weight.advice_requests),
            static_cast<unsigned long long>(weight.coalesced_ranges),
            static_cast<unsigned long long>(weight.invalid_ranges),
            static_cast<unsigned long long>(weight.madvise_failures),
            static_cast<unsigned long long>(weight.rounds_throttled),
            static_cast<unsigned long long>(weight.stale_requests),
            static_cast<unsigned long long>(weight.stale_bytes),
            static_cast<unsigned long long>(weight.inflight_peak_bytes),
            static_cast<unsigned long long>(reclaim.candidate_experts),
            static_cast<unsigned long long>(reclaim.calls),
            static_cast<unsigned long long>(reclaim.reclaimed_bytes),
            static_cast<unsigned long long>(reclaim.skipped_bytes),
            static_cast<unsigned long long>(reclaim.madvise_failures),
            static_cast<unsigned long long>(residency.samples),
            static_cast<unsigned long long>(residency.admitted_experts),
            static_cast<unsigned long long>(residency.admitted_bytes),
            static_cast<unsigned long long>(residency.skipped_bytes),
            static_cast<unsigned long long>(residency.fallbacks),
            static_cast<unsigned long long>(residency.pressure_normal),
            static_cast<unsigned long long>(residency.pressure_high),
            static_cast<unsigned long long>(residency.pressure_critical));
    }
    if (!pressure_admission_enabled_) {
        return;
    }
    const pressure_admission_stats pressure = pressure_stats();
    const prefetch_budget_stats prefetch = weight_prefetcher_ == nullptr ? prefetch_budget_stats{} : weight_prefetcher_->budget_stats();
    std::fprintf(
        stderr,
        "[SLIM-ARC-PRESSURE] samples=%llu throttled=%llu fallback=%llu static=%llu effective=%llu requested=%llu issued=%llu skipped=%llu failures=%llu\n",
        static_cast<unsigned long long>(pressure.samples),
        static_cast<unsigned long long>(pressure.throttled_samples),
        static_cast<unsigned long long>(pressure.fallback_samples),
        static_cast<unsigned long long>(pressure.static_bytes),
        static_cast<unsigned long long>(pressure.effective_bytes),
        static_cast<unsigned long long>(prefetch.requested_bytes),
        static_cast<unsigned long long>(prefetch.issued_bytes),
        static_cast<unsigned long long>(prefetch.skipped_bytes),
        static_cast<unsigned long long>(prefetch.madvise_failures));
}

void unified_io_scheduler::update_stats(const io_stats & stats) {
    current_stats_ = stats;
}

io_budget unified_io_scheduler::allocate_budget_for_total(size_t total_budget_bytes) {
    int phase_idx = static_cast<int>(phase_.load());
    const double * ratios = WEIGHT_RATIOS[phase_idx];

    io_budget budget;
    budget.total_bytes  = total_budget_bytes;
    budget.weight_bytes = static_cast<size_t>(total_budget_bytes * ratios[0]);
    budget.kv_bytes     = static_cast<size_t>(total_budget_bytes * ratios[1]);
    budget.expert_bytes = static_cast<size_t>(total_budget_bytes * ratios[2]);

    // Dynamic adaptation: adjust based on runtime statistics
    if (current_stats_.weight_stalls > 0) {
        // Weight prefetch is stalling compute → increase weight budget
        double adjustment = std::min(0.1, current_stats_.weight_stalls * 0.02);
        budget.weight_bytes = (size_t)(budget.weight_bytes * (1.0 + adjustment));
        budget.expert_bytes = (size_t)(budget.expert_bytes * (1.0 - adjustment * 0.5));
        budget.kv_bytes     = (size_t)(budget.kv_bytes * (1.0 - adjustment * 0.5));
    }

    if (current_stats_.kv_page_faults > 10) {
        // KV cache page faults → increase KV budget
        double adjustment = std::min(0.15, current_stats_.kv_page_faults * 0.005);
        budget.kv_bytes     = (size_t)(budget.kv_bytes * (1.0 + adjustment));
        budget.weight_bytes = (size_t)(budget.weight_bytes * (1.0 - adjustment * 0.5));
        budget.expert_bytes = (size_t)(budget.expert_bytes * (1.0 - adjustment * 0.5));
    }

    if (current_stats_.expert_miss_rate > 0.2) {
        // Expert prediction missing too often → increase expert budget
        double adjustment = std::min(0.2, current_stats_.expert_miss_rate * 0.3);
        budget.expert_bytes = (size_t)(budget.expert_bytes * (1.0 + adjustment));
        budget.weight_bytes = (size_t)(budget.weight_bytes * (1.0 - adjustment * 0.5));
        budget.kv_bytes     = (size_t)(budget.kv_bytes * (1.0 - adjustment * 0.5));
    }

    current_budget_ = budget;
    return budget;
}

io_budget unified_io_scheduler::allocate_budget() {
    return allocate_budget_for_total(total_budget_bytes_);
}

void unified_io_scheduler::tick(int current_layer, int lookahead) {
    size_t effective_total = total_budget_bytes_;
    cgroup_memory_snapshot snapshot;
    const bool sample_pressure = pressure_admission_enabled_ || expert_residency_enabled_;
    if (sample_pressure) {
        snapshot = pressure_provider_();
    }
    if (pressure_admission_enabled_) {
        const pressure_budget_result pressure = compute_pressure_budget(
            total_budget_bytes_, snapshot, pressure_minimum_reserve_bytes_, default_reserve_basis_points);
        effective_total = static_cast<size_t>(pressure.effective_budget_bytes);
        atomic_saturating_add(pressure_samples_, uint64_t{1});
        pressure_effective_bytes_.store(pressure.effective_budget_bytes);
        if (!pressure.pressure_data_valid) {
            atomic_saturating_add(pressure_fallback_samples_, uint64_t{1});
        }
        if (pressure.throttled) {
            atomic_saturating_add(pressure_throttled_samples_, uint64_t{1});
        }
    }
    auto budget = allocate_budget_for_total(effective_total);

    // 2. Issue prefetch requests within budget
    if (weight_prefetcher_) {
        weight_prefetcher_->set_memory_budget(budget.weight_bytes);
        if (expert_residency_enabled_) {
            const expert_pressure_sample sample{
                snapshot.status == cgroup_memory_status::ok,
                snapshot.current_bytes,
                snapshot.max_bytes,
            };
            expert_pressure_state pressure;
            {
                std::lock_guard<std::mutex> lock(pressure_controller_mtx_);
                pressure = expert_pressure_controller_.update(sample);
            }
            weight_prefetcher_->set_expert_residency_pressure(pressure, budget.expert_bytes);
        }
        // SLIM-ARC FIX 2026-08-09: 改进 3——把统一 I/O 预算的专家额度下发到 prefetch
        // scheduler（文献 admission control：按 expert budget 限流，防止 ~959MB 全层
        // 突发抢占 I/O）。SLIM_ARC_EXPERT_BUDGET=1 时启用（MOE_DECODE 专家占比 60%）。
        const bool expert_budget_on = getenv("SLIM_ARC_EXPERT_BUDGET") != nullptr;
        if (pressure_admission_enabled_ || expert_budget_on || expert_residency_enabled_) {
            weight_prefetcher_->set_expert_budget(budget.expert_bytes);
            weight_prefetcher_->reset_expert_budget_usage();  // 每 step 重置累计用量
        }
        weight_prefetcher_->notify_layer_compute(current_layer);
    }

    if (kv_manager_) {
        kv_manager_->run_eviction();
        kv_manager_->prefetch_cold_blocks(current_layer, lookahead);
    }

    // 3. Record adaptation history every 10 ticks
    if (++tick_count_ % 10 == 0) {
        std::lock_guard<std::mutex> lk(history_mtx_);
        history_.push_back({
            phase_.load(),
            current_budget_,
            current_stats_,
            std::chrono::steady_clock::now()
        });
        // Keep last 1000 records
        if (history_.size() > 1000) {
            history_.erase(history_.begin());
        }
    }
}

runtime_phase unified_io_scheduler::detect_phase(bool is_prefill, bool is_moe, size_t context_len) {
    if (is_moe && !is_prefill) return runtime_phase::MOE_DECODE;
    if (is_prefill) {
        return context_len > 4096 ? runtime_phase::PREFILL_LONG : runtime_phase::PREFILL_SHORT;
    }
    return context_len > 4096 ? runtime_phase::DECODE_LONG : runtime_phase::DECODE_SHORT;
}

void unified_io_scheduler::adapt_allocation() {
    // This is called implicitly through allocate_budget() via stats feedback
    // The adaptation logic is embedded in the budget allocation
}

std::vector<unified_io_scheduler::adaptation_record> unified_io_scheduler::adaptation_history() const {
    std::lock_guard<std::mutex> lk(history_mtx_);
    return history_;
}

pressure_admission_stats unified_io_scheduler::pressure_stats() const {
    return {
        pressure_samples_.load(),
        pressure_throttled_samples_.load(),
        pressure_fallback_samples_.load(),
        total_budget_bytes_,
        pressure_effective_bytes_.load(),
    };
}

} // namespace slim_arc
