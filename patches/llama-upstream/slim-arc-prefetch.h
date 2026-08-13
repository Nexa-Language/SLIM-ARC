#pragma once

#include "slim-arc-expert-residency.h"
#include "slim-arc-page-range.h"

// SLIM-ARC: Tensor-level asynchronous prefetch scheduler
//
// This module implements layer-ahead prefetch on top of upstream llama.cpp's
// mmap infrastructure. When computing layer N, it asynchronously issues
// posix_madvise(WILLNEED) for tensors in layers N+1..N+window, allowing the
// kernel to overlap I/O with computation.

#include <atomic>
#include <climits>  // SLIM-ARC FIX 2026-08-05: 防护 INT_MAX 级联错误
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

namespace slim_arc {

// SLIM-ARC FIX 2026-08-05: 计算阶段枚举，供 graph_compute 中 set_phase() 使用。
// 当 unified_io_scheduler 未启用时，prefetch_scheduler 单独使用该阶段信息。
enum class compute_phase {
    PREFILL,
    DECODE,
};

struct tensor_prefetch_info {
    void *   addr;      // mmap address of tensor data
    size_t   size;      // tensor data size in bytes
    int      layer;     // layer index (or -1 for non-layer tensors)
    uint64_t signature; // monotonic counter to detect graph changes
};

// SLIM-ARC FIX 2026-08-05: MoE 专家张量注册信息（3D 合并张量 *_exps）。
// addr 指向整个 3D 张量数据，n_experts = ne[2]，每个专家大小为 size/n_experts。
struct expert_tensor_info {
    void * addr;        // mmap address of the merged 3D expert tensor
    size_t size;        // total bytes of the merged tensor
    int    n_experts;   // number of experts (ne[2])
};

struct prefetch_budget_stats {
    uint64_t requested_bytes{0};
    uint64_t issued_bytes{0};
    uint64_t skipped_bytes{0};
    uint64_t rounds_throttled{0};
    uint64_t madvise_failures{0};
    uint64_t advice_requests{0};
    uint64_t coalesced_ranges{0};
    uint64_t covered_bytes{0};
    uint64_t invalid_ranges{0};
    uint64_t stale_requests{0};
    uint64_t stale_bytes{0};
    uint64_t inflight_peak_bytes{0};
};

struct expert_reclaim_stats {
    uint64_t candidate_experts{0};
    uint64_t calls{0};
    uint64_t reclaimed_bytes{0};
    uint64_t skipped_bytes{0};
    uint64_t madvise_failures{0};
    uint64_t invalid_layouts{0};
    uint64_t invalid_ids{0};
};

struct expert_residency_runtime_stats {
    uint64_t samples{0};
    uint64_t admitted_experts{0};
    uint64_t admitted_bytes{0};
    uint64_t skipped_bytes{0};
    uint64_t fallbacks{0};
    uint64_t pressure_missing{0};
    uint64_t pressure_normal{0};
    uint64_t pressure_high{0};
    uint64_t pressure_critical{0};
};

struct expert_runtime_metrics {
    uint64_t samples{0};
    uint64_t issued_bytes{0};
    uint64_t hit_bytes{0};
    uint64_t waste_bytes{0};
    uint64_t advice_requests{0};
    uint64_t coalesced_ranges{0};
    uint64_t covered_bytes{0};
    uint64_t advice_failures{0};
    uint64_t invalid_ranges{0};
};

std::vector<size_t> select_prefetch_items(
    const std::vector<size_t> & item_sizes,
    uint64_t budget_bytes,
    uint64_t * requested_bytes,
    uint64_t * skipped_bytes);

class prefetch_scheduler {
  public:
    using advice_fn = std::function<int(void *, size_t, int)>;
    using page_size_query_fn = std::function<long()>;

    explicit prefetch_scheduler(
        int n_threads = 2,
        int window = 3,
        std::function<void()> request_claim_hook = {},
        advice_fn advice = {},
        page_size_query_fn page_size_query = {});
    ~prefetch_scheduler();
    prefetch_scheduler(const prefetch_scheduler &) = delete;
    prefetch_scheduler & operator=(const prefetch_scheduler &) = delete;
    void shutdown() noexcept;

    // Register a tensor for potential prefetch. Called during model load.
    void register_tensor(const char * name, void * addr, size_t size, int layer);
    bool register_mapping(void * addr, size_t size);

    // Notify that we are about to compute layer `current_layer`.
    // This triggers async madvise(WILLNEED) for layers
    // [current_layer+1, current_layer+window].
    void notify_layer_compute(int current_layer);

    // Disable prefetch (e.g., when memory budget exceeded).
    void set_enabled(bool enabled) { enabled_.store(enabled); }

    // Collect statistics
    size_t total_prefetched_bytes() const { return total_bytes_.load(); }
    int    total_prefetch_calls()   const { return total_calls_.load(); }

    // ---- SLIM-ARC FIX 2026-08-05: 补齐 Pi5 端修复所需接口 ----
    // 设置计算阶段（prefill / decode）
    // SLIM-ARC FIX 2026-08-07: 触发动态 MADV 切换（PREFILL->SEQUENTIAL / DECODE->RANDOM）
    void set_phase(compute_phase phase);
    // 当前预取窗口大小（供 graph_compute 计算待预取层范围）
    int  effective_window() const { return window_; }
    // 内存预算（供 unified_io_scheduler 分配权重预取额度）
    void set_memory_budget(size_t bytes) { memory_budget_.store(bytes); }
    prefetch_budget_stats budget_stats() const;

    // Phase 2a: 注册 MoE 专家张量（3D 合并张量 *_exps）
    void register_expert_tensor(const char * name, void * addr, size_t size, int layer, int n_experts);
    // 缓存该层路由器选中的专家 ID（用于跨层预测）
    void cache_router_experts(int layer, const int * expert_ids, int n);
    // 结算指定预取代次；generation 为 0 时只更新预测器，不结算指标。
    void cache_router_experts(int layer, const int * expert_ids, int n, uint64_t generation);
    // 终止指定预取代次，并将其成功 issued bytes 一次性记为 waste。
    void cancel_expert_prefetch(int layer, uint64_t generation);
    // 获取某层最近缓存的路由专家 ID 的独立副本。
    std::vector<int> cached_experts_snapshot(int layer) const;
    // 对指定层的给定专家发起 WILLNEED 预取，并返回不可复用的结算代次。
    // 0 表示没有可结算的成功预取。
    uint64_t prefetch_experts(int layer, const int * expert_ids, int n);

    // ---- SLIM-ARC FIX 2026-08-09: 专家预取可观测性指标（文献 1：先可观测再优化）----
    // 输出命中率/浪费字节等汇总（析构时调用）
    void dump_metrics() const;
    size_t expert_prefetch_bytes() const { return expert_prefetch_bytes_.load(); }
    size_t expert_hit_bytes()     const { return expert_hit_bytes_.load(); }
    size_t expert_waste_bytes()   const { return expert_waste_bytes_.load(); }
    size_t pending_expert_records(int layer) const;
    expert_reclaim_stats expert_reclaim_statistics() const;
    bool expert_residency_enabled() const noexcept { return expert_residency_enabled_; }
    void set_expert_residency_pressure(expert_pressure_state pressure, size_t budget_bytes);
    expert_pressure_state current_expert_pressure() const;
    expert_residency_runtime_stats expert_residency_statistics() const noexcept;
    expert_runtime_metrics expert_runtime_statistics() const noexcept;
    std::vector<uint32_t> expert_popularity_snapshot(int layer) const;
    uint64_t popularity_decay_count() const noexcept { return popularity_decay_count_.load(); }
    uint32_t expert_waste_ewma_milli() const;
    uint64_t expert_waste_sample_count() const;
    bool expert_waste_restricted() const;
    size_t pending_request_count() const;
    uint64_t dropped_request_count() const { return dropped_requests_.load(); }
    bool confidence_gating_enabled() const { return conf_gating_; }
    int popularity_k() const { return pop_k_; }
    // 统一 I/O 预算下发与每步重置（改进 3，供 unified_io_scheduler::tick 调用）
    void set_expert_budget(size_t bytes) {
        expert_budget_.store(bytes);
        expert_budget_enabled_.store(true);
    }
    void reset_expert_budget_usage() { expert_budget_used_.store(0); }

  private:
    void worker_loop();
    uint64_t issue_expert_willneed(int layer, const int * expert_ids, int n);
    void reclaim_wrong_expert_pages(
        const std::vector<int> & prefetched,
        const std::vector<int> & selected,
        const std::vector<expert_tensor_info> & tensors);

    const bool slow_storage_enabled_;
    const bool router_prefetch_enabled_;
    const bool router_mlock_enabled_;
    const bool expert_prefetch_disabled_;
    const bool expert_random_madv_enabled_;
    const bool expert_normal_madv_enabled_;
    int n_threads_;
    int window_;
    std::atomic<compute_phase> phase_{compute_phase::DECODE};
    std::atomic<size_t> memory_budget_{0};
    std::atomic<bool>       enabled_{true};
    std::atomic<bool>       stop_{false};
    std::atomic<size_t>     total_bytes_{0};
    std::atomic<int>        total_calls_{0};
    std::atomic<uint64_t>   budget_requested_bytes_{0};
    std::atomic<uint64_t>   budget_issued_bytes_{0};
    std::atomic<uint64_t>   budget_skipped_bytes_{0};
    std::atomic<uint64_t>   budget_rounds_throttled_{0};
    std::atomic<uint64_t>   budget_madvise_failures_{0};
    std::atomic<uint64_t>   budget_advice_requests_{0};
    std::atomic<uint64_t>   budget_coalesced_ranges_{0};
    std::atomic<uint64_t>   budget_covered_bytes_{0};
    std::atomic<uint64_t>   budget_invalid_ranges_{0};
    std::atomic<uint64_t>   budget_stale_requests_{0};
    std::atomic<uint64_t>   budget_stale_bytes_{0};
    std::atomic<uint64_t>   budget_inflight_bytes_{0};
    std::atomic<uint64_t>   budget_inflight_peak_bytes_{0};

    // ---- SLIM-ARC FIX 2026-08-09: 专家预取可观测性指标（改进 1）----
    std::atomic<size_t>     expert_prefetch_bytes_{0};  // 实际 WILLNEED 下发字节
    std::atomic<size_t>     expert_hit_bytes_{0};       // 预取且下一 token 使用的字节
    std::atomic<size_t>     expert_waste_bytes_{0};     // 预取但未使用的字节
    std::atomic<uint64_t>   router_samples_{0};         // 统计采样数
    std::atomic<uint64_t>   expert_advice_requests_{0};
    std::atomic<uint64_t>   expert_coalesced_ranges_{0};
    std::atomic<uint64_t>   expert_covered_bytes_{0};
    std::atomic<uint64_t>   expert_advice_failures_{0};
    std::atomic<uint64_t>   expert_invalid_ranges_{0};

    std::vector<std::thread>          workers_;
    std::function<void()>             request_claim_hook_;
    const advice_fn                   advice_;
    const page_size_query_fn          page_size_query_;
    const bool                        reclaim_waste_enabled_;
    const bool                        expert_residency_enabled_;
    std::mutex                        shutdown_mtx_;
    mutable std::mutex                mtx_;
    std::condition_variable           cv_;
    struct prefetch_request {
        uint64_t generation{0};
        int layer{-1};
        uint64_t memory_budget{0};
        uint64_t requested_bytes{0};
        uint64_t advice_requests{0};
        uint64_t invalid_ranges{0};
        uint64_t covered_bytes{0};
        size_t page_size{0};
        std::vector<page_range> ranges;
    };
    prefetch_request plan_request(int current_layer);
    std::deque<prefetch_request>      pending_requests_;
    uint64_t                          next_request_generation_{0};
    static constexpr size_t           max_pending_requests{64};
    std::atomic<uint64_t>             dropped_requests_{0};

    // tensor registry indexed by layer
    std::vector<std::vector<tensor_prefetch_info>> tensors_by_layer_;
    // Small, always-used MoE router path. Kept separate from speculative weights.
    std::vector<tensor_prefetch_info>              router_tensors_;
    std::vector<page_range>                        router_locked_ranges_;
    std::atomic<uint64_t>                          router_locked_bytes_{0};
    std::atomic<uint64_t>                          router_lock_failures_{0};
    std::vector<std::pair<void *, size_t>>         mmap_regions_;
    std::vector<page_range>                        expert_madv_ranges_;
    std::atomic<uint64_t>                          expert_madv_advice_calls_{0};
    std::atomic<uint64_t>                          expert_madv_advice_bytes_{0};
    std::atomic<uint64_t>                          expert_madv_advice_failures_{0};
    // MoE expert registry indexed by layer
    std::vector<std::vector<expert_tensor_info>>   experts_by_layer_;
    // Guards the expert registry and router predictor/accounting state.
    mutable std::mutex                              expert_state_mtx_;
    // Router-selected expert IDs per layer (for next-layer prediction)
    std::vector<std::vector<int>>                  cached_router_experts_;
    struct expert_prefetch_record {
        uint64_t generation;
        std::vector<int> expert_ids;
        std::vector<size_t> issued_bytes;
    };
    // 每层按 generation 保存有界、尚未结算的预取记录（advice 前占位）。
    std::vector<std::vector<expert_prefetch_record>> pending_expert_prefetches_;
    uint64_t                                        next_expert_generation_{1};
    static constexpr size_t                         max_pending_expert_records_{64};
    std::atomic<uint64_t>                           expert_pending_rejected_generations_{0};
    std::atomic<uint64_t>                           expert_unmatched_generations_{0};
    std::atomic<uint64_t>                           reclaim_candidate_experts_{0};
    std::atomic<uint64_t>                           reclaim_calls_{0};
    std::atomic<uint64_t>                           reclaim_reclaimed_bytes_{0};
    std::atomic<uint64_t>                           reclaim_skipped_bytes_{0};
    std::atomic<uint64_t>                           reclaim_madvise_failures_{0};
    std::atomic<uint64_t>                           reclaim_invalid_layouts_{0};
    std::atomic<uint64_t>                           reclaim_invalid_ids_{0};
    // ---- SLIM-ARC FIX 2026-08-09: 置信度门控（改进 2）----
    // 上一步（t-2）路由，用于"连续两 token 稳定专家"高置信度过滤
    std::vector<std::vector<int>>                  prev_router_experts_;
    // SLIM_ARC_EXPERT_CONF=1 时启用 2-token 稳定性门控
    bool                                           conf_gating_ = false;

    // ---- SLIM-ARC FIX 2026-08-09: 统一 I/O 预算限制（改进 3，文献 admission control）----
    // set_expert_budget() 被调用后严格执行预算；0 表示禁用本 step 的专家预取。
    std::atomic<size_t>                            expert_budget_{0};
    std::atomic<bool>                              expert_budget_enabled_{false};
    // 本 step 已用专家预算（每 graph_compute 由 unified tick 重置）
    std::atomic<size_t>                            expert_budget_used_{0};

    // ---- SLIM-ARC FIX 2026-08-09: 组合预测器（改进 4，文献 ReMoE/DALI locality）----
    // SLIM_ARC_EXPERT_POP=K：预取 temporal 并集 top-K 热门专家
    int                                            pop_k_ = 0;
    // 每层专家激活频次计数（近窗口）
    std::vector<std::vector<uint32_t>>             expert_pop_counts_;
    uint8_t                                         popularity_samples_since_decay_{0};
    std::atomic<uint64_t>                           popularity_decay_count_{0};
    uint32_t                                        expert_waste_ewma_milli_{0};
    bool                                            expert_waste_ewma_initialized_{false};
    uint64_t                                        expert_waste_samples_{0};
    expert_pressure_state                           expert_pressure_{expert_pressure_state::missing};
    size_t                                          expert_residency_budget_{0};
    bool                                            expert_residency_snapshot_set_{false};
    expert_waste_controller                         expert_waste_controller_;
    bool                                            expert_waste_restricted_{false};
    std::atomic<uint64_t>                           residency_samples_{0};
    std::atomic<uint64_t>                           residency_admitted_experts_{0};
    std::atomic<uint64_t>                           residency_admitted_bytes_{0};
    std::atomic<uint64_t>                           residency_skipped_bytes_{0};
    std::atomic<uint64_t>                           residency_fallbacks_{0};
    std::atomic<uint64_t>                           residency_pressure_missing_{0};
    std::atomic<uint64_t>                           residency_pressure_normal_{0};
    std::atomic<uint64_t>                           residency_pressure_high_{0};
    std::atomic<uint64_t>                           residency_pressure_critical_{0};
};

// Helper: extract layer index from tensor name (blk.%d.*)
int tensor_layer_from_name(const char * name);

} // namespace slim_arc
