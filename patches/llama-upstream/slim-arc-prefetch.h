#pragma once

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

// SLIM-ARC FIX 2026-08-07: 动态 MADV 阶段切换前置声明。
// 供 prefetch_scheduler::set_phase() 内联调用（定义在 slim-arc-prefetch.cpp）。
// PREFILL -> MADV_SEQUENTIAL（顺序预读）；DECODE -> MADV_RANDOM（按需分页）。
// SLIM_ARC_DYNAMIC_MADV=0 禁用。
void apply_dynamic_madv(compute_phase phase);

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
};

std::vector<size_t> select_prefetch_items(
    const std::vector<size_t> & item_sizes,
    uint64_t budget_bytes,
    uint64_t * requested_bytes,
    uint64_t * skipped_bytes);

class prefetch_scheduler {
  public:
    explicit prefetch_scheduler(int n_threads = 2, int window = 3);
    ~prefetch_scheduler();

    // Register a tensor for potential prefetch. Called during model load.
    void register_tensor(const char * name, void * addr, size_t size, int layer);

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
    void set_phase(compute_phase phase) {
        phase_.store(phase);
        apply_dynamic_madv(phase);
    }
    // 当前预取窗口大小（供 graph_compute 计算待预取层范围）
    int  effective_window() const { return window_; }
    // 内存预算（供 unified_io_scheduler 分配权重预取额度）
    void set_memory_budget(size_t bytes) { memory_budget_.store(bytes); }
    prefetch_budget_stats budget_stats() const;

    // Phase 2a: 注册 MoE 专家张量（3D 合并张量 *_exps）
    void register_expert_tensor(const char * name, void * addr, size_t size, int layer, int n_experts);
    // 缓存该层路由器选中的专家 ID（用于跨层预测）
    void cache_router_experts(int layer, const int * expert_ids, int n);
    // 获取某层最近缓存的路由专家 ID
    const int * get_cached_experts(int layer, int * n) const;
    // 对指定层的给定专家发起 WILLNEED 预取
    void prefetch_experts(int layer, const int * expert_ids, int n);

    // ---- SLIM-ARC FIX 2026-08-09: 专家预取可观测性指标（文献 1：先可观测再优化）----
    // 输出命中率/浪费字节等汇总（析构时调用）
    void dump_metrics() const;
    size_t expert_prefetch_bytes() const { return expert_prefetch_bytes_.load(); }
    size_t expert_hit_bytes()     const { return expert_hit_bytes_.load(); }
    size_t expert_waste_bytes()   const { return expert_waste_bytes_.load(); }
    // 统一 I/O 预算下发与每步重置（改进 3，供 unified_io_scheduler::tick 调用）
    void set_expert_budget(size_t bytes) {
        expert_budget_.store(bytes);
        expert_budget_enabled_.store(true);
    }
    void reset_expert_budget_usage() { expert_budget_used_.store(0); }

  private:
    void worker_loop();
    void issue_expert_willneed(int layer, const int * expert_ids, int n);

    int n_threads_;
    int window_;
    std::atomic<compute_phase> phase_{compute_phase::DECODE};
    std::atomic<size_t> memory_budget_{0};
    std::atomic<bool>       enabled_{true};
    std::atomic<bool>       stop_{false};
    std::atomic<int>        current_layer_{-1};
    std::atomic<uint64_t>   signature_{0};
    std::atomic<size_t>     total_bytes_{0};
    std::atomic<int>        total_calls_{0};
    std::atomic<uint64_t>   budget_requested_bytes_{0};
    std::atomic<uint64_t>   budget_issued_bytes_{0};
    std::atomic<uint64_t>   budget_skipped_bytes_{0};
    std::atomic<uint64_t>   budget_rounds_throttled_{0};
    std::atomic<uint64_t>   budget_madvise_failures_{0};

    // ---- SLIM-ARC FIX 2026-08-09: 专家预取可观测性指标（改进 1）----
    std::atomic<size_t>     expert_prefetch_bytes_{0};  // 实际 WILLNEED 下发字节
    std::atomic<size_t>     expert_hit_bytes_{0};       // 预取且下一 token 使用的字节
    std::atomic<size_t>     expert_waste_bytes_{0};     // 预取但未使用的字节
    std::atomic<int>        router_samples_{0};         // 统计采样数

    std::vector<std::thread>          workers_;
    std::mutex                        mtx_;
    std::condition_variable           cv_;
    int                               target_layer_{-1};
    uint64_t                          target_signature_{0};

    // tensor registry indexed by layer
    std::vector<std::vector<tensor_prefetch_info>> tensors_by_layer_;
    // MoE expert registry indexed by layer
    std::vector<std::vector<expert_tensor_info>>   experts_by_layer_;
    // Router-selected expert IDs per layer (for next-layer prediction)
    mutable std::vector<std::vector<int>>          cached_router_experts_;
    // 最近一次实际下发的预取专家集合（每层，供命中率统计，改进 1）
    mutable std::vector<std::vector<int>>          last_prefetched_experts_;
    // ---- SLIM-ARC FIX 2026-08-09: 置信度门控（改进 2）----
    // 上一步（t-2）路由，用于"连续两 token 稳定专家"高置信度过滤
    mutable std::vector<std::vector<int>>          prev_router_experts_;
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
    mutable std::vector<std::vector<int>>          expert_pop_counts_;
};

// Global singleton (set by llama_context during init)
prefetch_scheduler * get_global_prefetch_scheduler();
void set_global_prefetch_scheduler(prefetch_scheduler * s);

// Helper: extract layer index from tensor name (blk.%d.*)
int tensor_layer_from_name(const char * name);

// SLIM-ARC FIX 2026-08-05: mmap 区域注册表（供动态 MADV 切换）。
// 在 init_mappings 中为 >6GB 模型设置 MADV 建议时调用。
// SLIM-ARC FIX 2026-08-07: 初始建议由 register_mmap_region 改为 MADV_SEQUENTIAL，
// 配合 apply_dynamic_madv() 在 prefill/decode 阶段动态切换。
void register_mmap_region(void * addr, size_t size);

} // namespace slim_arc
