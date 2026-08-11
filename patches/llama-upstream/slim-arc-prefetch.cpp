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

// SLIM-ARC FIX 2026-08-05: mmap 区域注册表（供动态 MADV 切换；当前仅记录）。
std::mutex g_mmap_mtx;
std::vector<std::pair<void *, size_t>> g_mmap_regions;
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

// ---- SLIM-ARC FIX 2026-08-05: Phase 2a MoE expert prefetch ----
void prefetch_scheduler::register_expert_tensor(const char * name, void * addr, size_t size, int layer, int n_experts) {
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
    // SLIM-ARC FIX 2026-08-09: 命中率统计（改进 1）。
    // last_prefetched_experts_[layer] = 本 step 实际下发的预取集合；
    // expert_ids = 本 step 实际路由。hit = 预取∩实际，waste = 预取 - hit。
    if ((size_t)layer < last_prefetched_experts_.size()) {
        const auto & pref = last_prefetched_experts_[layer];
        if (!pref.empty()) {
            int hit = 0;
            for (int i = 0; i < n; ++i) {
                for (int p : pref) if (p == expert_ids[i]) { ++hit; break; }
            }
            size_t per_expert = 0;
            if ((size_t)layer < experts_by_layer_.size()) {
                for (const auto & e : experts_by_layer_[layer]) {
                    per_expert += e.size / (size_t) e.n_experts;
                }
            }
            expert_hit_bytes_.fetch_add(hit * per_expert);
            expert_waste_bytes_.fetch_add((pref.size() - (size_t) hit) * per_expert);
            // SLIM-ARC FIX 2026-08-09: 指标自洽修复——计数后清空，防止同一层
            // 多个 ffn_moe_topk 节点对同一预取集合重复计数（pref != hit+waste）。
            last_prefetched_experts_[layer].clear();
        }
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
    for (int i = 0; i < n; ++i) {
        int eid = expert_ids[i];
        if (eid >= 0 && eid < (int)expert_pop_counts_[layer].size()) {
            expert_pop_counts_[layer][eid]++;
        }
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

    // SLIM-ARC FIX 2026-08-09: 先构建"实际预取目标集合"。
    // 改进 2（置信度门控，文献 CommitMoE/DALI）：SLIM_ARC_EXPERT_CONF=1 时
    // 仅预取连续两 token 都激活的稳定专家（A_t ∩ A_{t-1}），低置信度不浪费 WILLNEED、
    // 依赖按需分页，减少无效 I/O。
    std::vector<int> target;
    target.reserve(n);
    if (conf_gating_ && (size_t)layer < prev_router_experts_.size() && !prev_router_experts_[layer].empty()) {
        const auto & prev = prev_router_experts_[layer];
        for (int i = 0; i < n; ++i) {
            int eid = expert_ids[i];
            if (eid < 0) continue;
            bool in_prev = false;
            for (int p : prev) if (p == eid) { in_prev = true; break; }
            if (!in_prev) continue;
            bool dup = false;
            for (int x : target) if (x == eid) { dup = true; break; }
            if (!dup) target.push_back(eid);
        }
    } else {
        for (int i = 0; i < n; ++i) {
            int eid = expert_ids[i];
            if (eid < 0) continue;
            bool dup = false;
            for (int x : target) if (x == eid) { dup = true; break; }
            if (!dup) target.push_back(eid);
        }
    }
    // SLIM-ARC FIX 2026-08-09: 改进 4——并集 top-K 热门专家（文献 ReMoE/DALI locality）。
    // 提高覆盖面，减少 miss；SLIM_ARC_EXPERT_POP=K 启用。
    if (pop_k_ > 0 && (size_t)layer < expert_pop_counts_.size() && !expert_pop_counts_[layer].empty()) {
        std::vector<std::pair<int, int>> rank;
        for (int eid = 0; eid < (int) expert_pop_counts_[layer].size(); ++eid) {
            if (expert_pop_counts_[layer][eid] > 0) rank.emplace_back(eid, expert_pop_counts_[layer][eid]);
        }
        std::sort(rank.begin(), rank.end(),
                  [](const std::pair<int, int> & a, const std::pair<int, int> & b) { return a.second > b.second; });
        int added = 0;
        for (const auto & pr : rank) {
            if (added >= pop_k_) break;
            int eid = pr.first;
            bool dup = false;
            for (int x : target) if (x == eid) { dup = true; break; }
            if (!dup) { target.push_back(eid); ++added; }
        }
    }
    // SLIM-ARC FIX 2026-08-09: 改进 3——每 step 统一 I/O 预算截断（文献 admission control）。
    // expert_budget_ > 0 时，本 graph_compute step 内专家 WILLNEED 累计不超过预算；
    // 预算耗尽则本层跳过（依赖按需分页）。unified tick 每 step 重置累计用量。
    size_t budget = expert_budget_.load();
    if (budget > 0) {
        size_t used = expert_budget_used_.load();
        if (used >= budget) return;
        size_t per_exp = 0;
        for (const auto & e : exps) per_exp += e.size / (size_t) e.n_experts;
        if (per_exp > 0) {
            size_t room = budget - used;
            size_t cap = room / per_exp;
            if (cap < target.size()) target.resize(cap);
            if (!target.empty()) {
                expert_budget_used_.fetch_add(target.size() * per_exp);
            }
        }
    }
    if (target.empty()) return;

    size_t bytes = 0;
    for (const auto & e : exps) {
        size_t per_expert = e.size / (size_t) e.n_experts;
        if (per_expert == 0) continue;
        for (int eid : target) {
            if (eid >= e.n_experts) continue;
            size_t off = (size_t) eid * per_expert;
            (void) posix_madvise((uint8_t *) e.addr + off, per_expert, POSIX_MADV_WILLNEED);
            bytes += per_expert;
        }
    }
    if ((size_t)layer >= last_prefetched_experts_.size()) {
        last_prefetched_experts_.resize(layer + 1);
    }
    last_prefetched_experts_[layer] = std::move(target);

    if (bytes > 0) {
        total_bytes_.fetch_add(bytes);
        expert_prefetch_bytes_.fetch_add(bytes);
    }
}

// SLIM-ARC FIX 2026-08-09: 专家预取可观测性指标汇总（改进 1）。
// issued = 实际 WILLNEED 下发字节（issue 侧）；hit/waste = 命中/浪费（cache 侧，按
// 实际路由对照预取集合）。命中率 = hit/(hit+waste)。两口径因预取/缓存两遍层覆盖
// 不完全一致而可能略有差异，命中率不受影响。
void prefetch_scheduler::dump_metrics() const {
    size_t issued = expert_prefetch_bytes_.load();
    size_t hit    = expert_hit_bytes_.load();
    size_t waste  = expert_waste_bytes_.load();
    size_t total  = hit + waste;
    double hr = total > 0 ? 100.0 * (double) hit / (double) total : 0.0;
    fprintf(stderr,
            "[SLIM-ARC-METRICS] expert prefetch: samples=%d issued=%.1fMB "
            "hit=%.1fMB waste=%.1fMB hit_rate=%.2f%% (accounted %.1fMB)\n",
            router_samples_.load(),
            issued / 1048576.0, hit / 1048576.0, waste / 1048576.0, hr,
            total / 1048576.0);
}

} // namespace slim_arc
