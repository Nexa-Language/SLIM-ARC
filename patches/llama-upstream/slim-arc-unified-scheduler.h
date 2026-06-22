// SLIM-ARC: Unified I/O Bandwidth Budget Scheduler
//
// Core innovation: coordinates weight prefetch, KV cache swap, and MoE expert
// prefetch to share NVMe bandwidth optimally based on runtime phase.
//
// Unlike FlexInfer (weights only), DUAL-BLADE (KV only), or MobileMoE (experts
// only), SLIM-ARC unifies all three I/O domains under a single budget allocator.

#pragma once

#include "slim-arc-prefetch.h"
#include "slim-arc-kv-eviction.h"

#include <atomic>
#include <chrono>
#include <cstddef>
#include <mutex>

namespace slim_arc {

enum class runtime_phase {
    PREFILL_SHORT,   // short context prefill (compute-bound)
    PREFILL_LONG,    // long context prefill (KV growing)
    DECODE_SHORT,    // short context decode (weight-bound)
    DECODE_LONG,     // long context decode (KV-bound)
    MOE_DECODE,      // MoE model decode (expert-bound)
};

struct io_budget {
    size_t weight_bytes;  // budget for weight prefetch
    size_t kv_bytes;      // budget for KV cache swap
    size_t expert_bytes;  // budget for expert prefetch
    size_t total_bytes;   // total I/O budget per cycle
};

struct io_stats {
    double weight_latency;       // avg weight prefetch latency (ms)
    double kv_latency;           // avg KV swap latency (ms)
    double expert_miss_rate;     // expert prediction miss rate (0-1)
    double bandwidth_utilization;// actual / budget (0-1)
    int    weight_stalls;        // compute stalls waiting for weights
    int    kv_page_faults;       // KV cache page faults
};

class unified_io_scheduler {
  public:
    explicit unified_io_scheduler(size_t total_budget_bytes,
                                   prefetch_scheduler * weight_prefetcher,
                                   kv_eviction_manager * kv_manager);
    ~unified_io_scheduler();

    // Called at the start of each graph compute cycle
    void set_phase(runtime_phase phase) { phase_.store(phase); }

    // Called after each layer to update runtime statistics
    void update_stats(const io_stats & stats);

    // Allocate bandwidth budget for current cycle based on phase and stats
    io_budget allocate_budget();

    // Execute one scheduling tick:
    // 1. Allocate budget
    // 2. Issue prefetch requests within budget
    // 3. Monitor and adapt
    void tick(int current_layer, int lookahead);

    // Get current effective budget allocation
    io_budget current_budget() const { return current_budget_; }

    // Get adaptation history (for debugging/visualization)
    struct adaptation_record {
        runtime_phase phase;
        io_budget budget;
        io_stats stats;
        std::chrono::steady_clock::time_point timestamp;
    };
    std::vector<adaptation_record> adaptation_history() const;

  private:
    size_t total_budget_bytes_;
    prefetch_scheduler * weight_prefetcher_;
    kv_eviction_manager * kv_manager_;

    std::atomic<runtime_phase> phase_{runtime_phase::PREFILL_SHORT};
    io_budget current_budget_{};
    io_stats current_stats_{};

    std::mutex history_mtx_;
    std::vector<adaptation_record> history_;
    int tick_count_ = 0;

    // Weight allocation table: [phase] -> (weight%, kv%, expert%)
    static constexpr double WEIGHT_RATIOS[5][3] = {
        // {weight, kv, expert}
        {0.60, 0.10, 0.30},  // PREFILL_SHORT
        {0.50, 0.20, 0.30},  // PREFILL_LONG
        {0.70, 0.20, 0.10},  // DECODE_SHORT
        {0.30, 0.60, 0.10},  // DECODE_LONG
        {0.20, 0.20, 0.60},  // MOE_DECODE
    };

    void adapt_allocation();
    runtime_phase detect_phase(bool is_prefill, bool is_moe, size_t context_len);
};

} // namespace slim_arc
