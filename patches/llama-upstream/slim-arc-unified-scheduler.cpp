// SLIM-ARC: Unified I/O Bandwidth Budget Scheduler Implementation

#include "slim-arc-unified-scheduler.h"

#include <algorithm>
#include <cmath>

namespace slim_arc {

namespace {
unified_io_scheduler * g_unified_scheduler = nullptr;
}

unified_io_scheduler * get_global_unified_scheduler() { return g_unified_scheduler; }
void set_global_unified_scheduler(unified_io_scheduler * s) { g_unified_scheduler = s; }

// Static weight ratio table initialization
constexpr double unified_io_scheduler::WEIGHT_RATIOS[5][3];

unified_io_scheduler::unified_io_scheduler(size_t total_budget_bytes,
                                            prefetch_scheduler * weight_prefetcher,
                                            kv_eviction_manager * kv_manager)
    : total_budget_bytes_(total_budget_bytes)
    , weight_prefetcher_(weight_prefetcher)
    , kv_manager_(kv_manager) {
    current_budget_.total_bytes = total_budget_bytes;
}

unified_io_scheduler::~unified_io_scheduler() = default;

void unified_io_scheduler::update_stats(const io_stats & stats) {
    current_stats_ = stats;
}

io_budget unified_io_scheduler::allocate_budget() {
    int phase_idx = static_cast<int>(phase_.load());
    const double * ratios = WEIGHT_RATIOS[phase_idx];

    io_budget budget;
    budget.total_bytes  = total_budget_bytes_;
    budget.weight_bytes = (size_t)(total_budget_bytes_ * ratios[0]);
    budget.kv_bytes     = (size_t)(total_budget_bytes_ * ratios[1]);
    budget.expert_bytes = (size_t)(total_budget_bytes_ * ratios[2]);

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

void unified_io_scheduler::tick(int current_layer, int lookahead) {
    // 1. Allocate budget
    auto budget = allocate_budget();

    // 2. Issue prefetch requests within budget
    if (weight_prefetcher_) {
        weight_prefetcher_->set_memory_budget(budget.weight_bytes);
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
    std::lock_guard<std::mutex> lk(const_cast<std::mutex &>(history_mtx_));
    return history_;
}

} // namespace slim_arc
