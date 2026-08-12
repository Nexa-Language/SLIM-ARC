#include "slim-arc-prefetch.h"

#include <cassert>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <limits>
#include <cstdlib>
#include <future>
#include <string>
#include <sys/mman.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {

void test_selection_skips_items_that_do_not_fit() {
    uint64_t requested{0};
    uint64_t skipped{0};
    const auto selected = slim_arc::select_prefetch_items({128, 512, 128}, 300, &requested, &skipped);
    assert((selected == std::vector<size_t>{0, 2}));
    assert(requested == 768);
    assert(skipped == 512);
}

void test_zero_and_exact_budgets() {
    uint64_t requested{0};
    uint64_t skipped{0};
    const auto none = slim_arc::select_prefetch_items({128, 512}, 0, &requested, &skipped);
    assert(none.empty());
    assert(requested == 640);
    assert(skipped == 640);

    const auto exact = slim_arc::select_prefetch_items({128, 512}, 640, &requested, &skipped);
    assert((exact == std::vector<size_t>{0, 1}));
    assert(requested == 640);
    assert(skipped == 0);
}

void test_totals_saturate_near_uint64_max() {
    constexpr uint64_t maximum = std::numeric_limits<uint64_t>::max();
    uint64_t requested{0};
    uint64_t skipped{0};
    const auto selected = slim_arc::select_prefetch_items({maximum - 10, 20}, maximum, &requested, &skipped);
    assert((selected == std::vector<size_t>{0}));
    assert(requested == maximum);
    assert(skipped == 20);
}

void wait_for_rounds(const slim_arc::prefetch_scheduler & scheduler, uint64_t expected) {
    for (int attempt = 0; attempt < 200; ++attempt) {
        if (static_cast<uint64_t>(scheduler.total_prefetch_calls()) >= expected) {
            return;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds{5});
    }
    assert(false && "prefetch worker did not complete");
}

void test_two_workers_claim_identical_layer_requests_exactly_once_each() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{2, 1};
        scheduler.register_tensor("blk.1.weight", mapping, page_size, 1);
        scheduler.set_memory_budget(page_size);
        scheduler.notify_layer_compute(0);
        scheduler.notify_layer_compute(0);
        wait_for_rounds(scheduler, 2);
        scheduler.shutdown();
        assert(scheduler.total_prefetch_calls() == 2);
        assert(scheduler.budget_stats().issued_bytes == 2 * page_size);
    }
    assert(munmap(mapping, page_size) == 0);
}

void test_two_workers_claim_distinguishable_layers_without_duplication() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 3 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{2, 1};
        scheduler.register_tensor("blk.1.first", mapping, page_size, 1);
        scheduler.register_tensor("blk.2.second", static_cast<uint8_t *>(mapping) + page_size, 2 * page_size, 2);
        scheduler.set_memory_budget(3 * page_size);
        scheduler.notify_layer_compute(0);
        scheduler.notify_layer_compute(1);
        wait_for_rounds(scheduler, 2);
        scheduler.shutdown();
        assert(scheduler.total_prefetch_calls() == 2);
        assert(scheduler.budget_stats().requested_bytes == 3 * page_size);
        assert(scheduler.budget_stats().issued_bytes == 3 * page_size);
    }
    assert(munmap(mapping, 3 * page_size) == 0);
}

void test_request_queue_is_bounded_and_drops_oldest_unclaimed() {
    std::promise<void> claimed;
    std::promise<void> release;
    std::atomic<bool> first{true};
    std::shared_future<void> release_gate = release.get_future().share();
    slim_arc::prefetch_scheduler scheduler{1, 1, [&] {
        if (first.exchange(false)) {
            claimed.set_value();
            release_gate.wait();
        }
    }};
    scheduler.set_memory_budget(0);
    for (int layer = 1; layer <= 66; ++layer) {
        scheduler.register_tensor("weight", reinterpret_cast<void *>(1), static_cast<size_t>(layer), layer);
    }
    scheduler.notify_layer_compute(0);
    claimed.get_future().wait();
    for (int layer = 1; layer <= 65; ++layer) {
        scheduler.notify_layer_compute(layer);
    }
    assert(scheduler.pending_request_count() == 64);
    assert(scheduler.dropped_request_count() == 1);
    release.set_value();
    wait_for_rounds(scheduler, 65);
    scheduler.shutdown();
    // Claimed target 0 issues size 1. Of queued targets 1..65, target 1
    // (size 2) is the oldest and must be the sole dropped request.
    assert(scheduler.budget_stats().requested_bytes == 1 + (3 + 66) * 64 / 2);
}

void test_concurrent_shutdown_callers_return_only_after_join() {
    slim_arc::prefetch_scheduler scheduler{2, 1};
    std::promise<void> start;
    std::shared_future<void> gate = start.get_future().share();
    auto shutdown = [&] {
        gate.wait();
        scheduler.shutdown();
        assert(scheduler.pending_request_count() == 0);
    };
    std::thread first{shutdown};
    std::thread second{shutdown};
    start.set_value();
    first.join();
    second.join();
}

class scoped_env {
  public:
    scoped_env(const char * name, const char * value) : name_(name) {
        const char * old = std::getenv(name);
        if (old != nullptr) {
            had_previous_ = true;
            previous_ = old;
        }
        if (value == nullptr) unsetenv(name); else setenv(name, value, 1);
    }
    ~scoped_env() {
        if (!had_previous_) unsetenv(name_.c_str()); else setenv(name_.c_str(), previous_.c_str(), 1);
    }
  private:
    std::string name_;
    std::string previous_;
    bool had_previous_{false};
};

void test_confidence_flag_requires_exact_one() {
    for (const char * value : {"0", "", "false", "invalid"}) {
        scoped_env env{"SLIM_ARC_EXPERT_CONF", value};
        slim_arc::prefetch_scheduler scheduler{1, 1};
        assert(!scheduler.confidence_gating_enabled());
    }
    scoped_env env{"SLIM_ARC_EXPERT_CONF", "1"};
    slim_arc::prefetch_scheduler scheduler{1, 1};
    assert(scheduler.confidence_gating_enabled());
}

void test_popularity_accepts_only_complete_range_zero_to_sixty_four() {
    for (const auto & item : std::vector<std::pair<const char *, int>>{{"0", 0}, {"64", 64}, {"17", 17}}) {
        scoped_env env{"SLIM_ARC_EXPERT_POP", item.first};
        slim_arc::prefetch_scheduler scheduler{1, 1};
        assert(scheduler.popularity_k() == item.second);
    }
    for (const char * value : {"-1", "65", "", "7tail", "18446744073709551616"}) {
        scoped_env env{"SLIM_ARC_EXPERT_POP", value};
        slim_arc::prefetch_scheduler scheduler{1, 1};
        assert(scheduler.popularity_k() == 0);
    }
}

void test_scheduler_enforces_budget_and_counts_success() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_tensor("blk.1.first", mapping, page_size, 1);
        scheduler.register_tensor("blk.1.second", static_cast<uint8_t *>(mapping) + page_size, page_size, 1);
        scheduler.set_memory_budget(page_size);
        scheduler.notify_layer_compute(0);
        wait_for_rounds(scheduler, 1);
        const auto stats = scheduler.budget_stats();
        assert(stats.requested_bytes == 2 * page_size);
        assert(stats.issued_bytes == page_size);
        assert(stats.skipped_bytes == page_size);
        assert(stats.rounds_throttled == 1);
        assert(stats.madvise_failures == 0);
    }
    assert(munmap(mapping, 2 * page_size) == 0);
}

void test_scheduler_counts_madvise_failure_without_issuing_bytes() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    slim_arc::prefetch_scheduler scheduler{1, 1};
    scheduler.register_tensor("blk.1.invalid", reinterpret_cast<void *>(1), page_size, 1);
    scheduler.set_memory_budget(page_size);
    scheduler.notify_layer_compute(0);
    wait_for_rounds(scheduler, 1);
    const auto stats = scheduler.budget_stats();
    assert(stats.requested_bytes == page_size);
    assert(stats.issued_bytes == 0);
    assert(stats.madvise_failures == 1);
}

void test_zero_expert_budget_disables_expert_prefetch() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.1.exps", mapping, page_size, 1, 1);
        scheduler.set_expert_budget(0);
        const int expert_id{0};
        assert(scheduler.prefetch_experts(1, &expert_id, 1) == 0);
        assert(scheduler.expert_prefetch_bytes() == 0);
    }
    assert(munmap(mapping, page_size) == 0);
}

void test_cached_expert_snapshot_does_not_change_after_router_update() {
    slim_arc::prefetch_scheduler scheduler{1, 1};
    const int initial[] = {2, 4};
    scheduler.cache_router_experts(3, initial, 2);
    const std::vector<int> snapshot = scheduler.cached_experts_snapshot(3);

    const int updated[] = {7};
    scheduler.cache_router_experts(3, updated, 1);

    assert((snapshot == std::vector<int>{2, 4}));
    assert((scheduler.cached_experts_snapshot(3) == std::vector<int>{7}));
}

void test_duplicate_router_ids_do_not_overcount_hits_or_underflow_waste() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.1.exps", mapping, page_size, 1, 1);
        const int duplicate_selection[] = {0, 0};
        const uint64_t generation = scheduler.prefetch_experts(1, duplicate_selection, 2);
        assert(generation != 0);
        assert(scheduler.expert_prefetch_bytes() == page_size);

        scheduler.cache_router_experts(1, duplicate_selection, 2, generation);
        assert(scheduler.expert_hit_bytes() == page_size);
        assert(scheduler.expert_waste_bytes() == 0);
    }
    assert(munmap(mapping, page_size) == 0);
}

void test_partial_expert_advice_failure_accounts_only_successful_bytes() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.2.valid", mapping, page_size, 2, 1);
        scheduler.register_expert_tensor("blk.2.invalid", reinterpret_cast<void *>(1), page_size, 2, 1);
        const int expert_id{0};
        const uint64_t generation = scheduler.prefetch_experts(2, &expert_id, 1);
        assert(generation != 0);
        assert(scheduler.expert_prefetch_bytes() == page_size);

        scheduler.cache_router_experts(2, &expert_id, 1, generation);
        assert(scheduler.expert_hit_bytes() == page_size);
        assert(scheduler.expert_waste_bytes() == 0);
        assert(scheduler.expert_hit_bytes() + scheduler.expert_waste_bytes() == scheduler.expert_prefetch_bytes());
    }
    assert(munmap(mapping, page_size) == 0);
}

void test_same_layer_generations_settle_in_reverse_order_once() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.4.exps", mapping, 2 * page_size, 4, 2);
        const int first_selection{0};
        const int second_selection{1};
        const uint64_t first_generation = scheduler.prefetch_experts(4, &first_selection, 1);
        const uint64_t second_generation = scheduler.prefetch_experts(4, &second_selection, 1);
        assert(first_generation != 0);
        assert(second_generation > first_generation);

        scheduler.cache_router_experts(4, &second_selection, 1, second_generation);
        assert(scheduler.expert_hit_bytes() == page_size);
        scheduler.cache_router_experts(4, &first_selection, 1, first_generation);
        assert(scheduler.expert_hit_bytes() == 2 * page_size);
        assert(scheduler.expert_waste_bytes() == 0);

        scheduler.cache_router_experts(4, &first_selection, 1, first_generation);
        assert(scheduler.expert_hit_bytes() == 2 * page_size);
        assert(scheduler.expert_waste_bytes() == 0);
    }
    assert(munmap(mapping, 2 * page_size) == 0);
}

void test_zero_generation_updates_predictor_without_settling_metrics() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    slim_arc::prefetch_scheduler scheduler{1, 1};
    scheduler.register_expert_tensor("blk.5.invalid", reinterpret_cast<void *>(1), page_size, 5, 1);
    const int expert_id{0};
    assert(scheduler.prefetch_experts(5, &expert_id, 1) == 0);
    scheduler.cache_router_experts(5, &expert_id, 1, 0);
    assert((scheduler.cached_experts_snapshot(5) == std::vector<int>{0}));
    assert(scheduler.expert_hit_bytes() == 0);
    assert(scheduler.expert_waste_bytes() == 0);
}

void test_pending_generations_are_bounded_before_advice() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.6.exps", mapping, page_size, 6, 1);
        const int expert_id{0};
        std::vector<uint64_t> generations;
        for (size_t index = 0; index < 64; ++index) {
            const uint64_t generation = scheduler.prefetch_experts(6, &expert_id, 1);
            assert(generation != 0);
            generations.push_back(generation);
        }
        assert(scheduler.pending_expert_records(6) == 64);
        scheduler.set_expert_budget(page_size);
        assert(scheduler.prefetch_experts(6, &expert_id, 1) == 0);
        assert(scheduler.pending_expert_records(6) == 64);

        scheduler.cache_router_experts(6, &expert_id, 1, generations.front());
        assert(scheduler.pending_expert_records(6) == 63);
        assert(scheduler.prefetch_experts(6, &expert_id, 1) != 0);
        assert(scheduler.pending_expert_records(6) == 64);
    }
    assert(munmap(mapping, page_size) == 0);
}

void test_cancelled_generation_counts_once_as_waste() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.7.exps", mapping, page_size, 7, 1);
        const int expert_id{0};
        const uint64_t generation = scheduler.prefetch_experts(7, &expert_id, 1);
        assert(generation != 0);
        assert(scheduler.pending_expert_records(7) == 1);

        scheduler.cancel_expert_prefetch(7, generation);
        assert(scheduler.pending_expert_records(7) == 0);
        assert(scheduler.expert_hit_bytes() == 0);
        assert(scheduler.expert_waste_bytes() == page_size);
        scheduler.cancel_expert_prefetch(7, generation);
        scheduler.cancel_expert_prefetch(7, 0);
        assert(scheduler.expert_waste_bytes() == page_size);
    }
    assert(munmap(mapping, page_size) == 0);
}

void test_prefetch_cancel_cycles_do_not_exhaust_pending_slots() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.8.exps", mapping, page_size, 8, 1);
        const int expert_id{0};
        for (size_t cycle = 0; cycle < 65; ++cycle) {
            const uint64_t generation = scheduler.prefetch_experts(8, &expert_id, 1);
            assert(generation != 0);
            scheduler.cancel_expert_prefetch(8, generation);
            assert(scheduler.pending_expert_records(8) == 0);
        }
        assert(scheduler.prefetch_experts(8, &expert_id, 1) != 0);
    }
    assert(munmap(mapping, page_size) == 0);
}

struct advice_call {
    void * address;
    size_t length;
    int advice;
};

void assert_zero_reclaim_stats(const slim_arc::expert_reclaim_stats & stats) {
    assert(stats.candidate_experts == 0);
    assert(stats.calls == 0);
    assert(stats.reclaimed_bytes == 0);
    assert(stats.skipped_bytes == 0);
    assert(stats.madvise_failures == 0);
    assert(stats.invalid_layouts == 0);
    assert(stats.invalid_ids == 0);
}

void test_reclaim_flag_off_preserves_legacy_settlement_without_dontneed() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "0"};
    std::vector<advice_call> calls;
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void * address, size_t length, int advice) {
            calls.push_back({address, length, advice});
            return 0;
        }};
        scheduler.register_expert_tensor("blk.9.exps", mapping, 2 * page_size, 9, 2);
        const int predicted[] = {0, 1};
        const int selected{0};
        const uint64_t generation = scheduler.prefetch_experts(9, predicted, 2);
        assert(generation != 0);
        scheduler.cache_router_experts(9, &selected, 1, generation);
        assert(scheduler.expert_waste_bytes() == page_size);
        assert_zero_reclaim_stats(scheduler.expert_reclaim_statistics());
    }
    assert(std::none_of(calls.begin(), calls.end(), [](const advice_call & call) {
        return call.advice == POSIX_MADV_DONTNEED;
    }));
    assert(munmap(mapping, 2 * page_size) == 0);
}

void test_reclaim_flag_requires_exact_one() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    for (const char * value : {"0", "", "false", "true"}) {
        void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
        assert(mapping != MAP_FAILED);
        scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", value};
        int dontneed_count{0};
        {
            slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
                if (advice == POSIX_MADV_DONTNEED) ++dontneed_count;
                return 0;
            }};
            scheduler.register_expert_tensor("blk.9.exps", mapping, 2 * page_size, 9, 2);
            const int predicted[] = {0, 1};
            const int selected{0};
            const uint64_t generation = scheduler.prefetch_experts(9, predicted, 2);
            assert(generation != 0);
            scheduler.cache_router_experts(9, &selected, 1, generation);
            assert_zero_reclaim_stats(scheduler.expert_reclaim_statistics());
        }
        assert(dontneed_count == 0);
        assert(munmap(mapping, 2 * page_size) == 0);
    }
}

void test_reclaim_excludes_selected_experts_and_uses_only_dontneed() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 3 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "1"};
    std::vector<advice_call> calls;
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void * address, size_t length, int advice) {
            calls.push_back({address, length, advice});
            return 0;
        }};
        scheduler.register_expert_tensor("blk.10.exps", mapping, 3 * page_size, 10, 3);
        const int predicted[] = {0, 1, 2};
        const int selected[] = {0, 2};
        const uint64_t generation = scheduler.prefetch_experts(10, predicted, 3);
        assert(generation != 0);
        scheduler.cache_router_experts(10, selected, 2, generation);
        const auto stats = scheduler.expert_reclaim_statistics();
        assert(stats.candidate_experts == 1);
        assert(stats.calls == 1);
        assert(stats.reclaimed_bytes == page_size);
        assert(stats.skipped_bytes == 0);
        assert(stats.madvise_failures == 0);
        assert(stats.invalid_layouts == 0);
        assert(stats.invalid_ids == 0);
    }
    const auto dontneed = std::find_if(calls.begin(), calls.end(), [](const advice_call & call) {
        return call.advice == POSIX_MADV_DONTNEED;
    });
    assert(dontneed != calls.end());
    assert(dontneed->address == static_cast<uint8_t *>(mapping) + page_size);
    assert(dontneed->length == page_size);
    assert(std::count_if(calls.begin(), calls.end(), [](const advice_call & call) {
        return call.advice == POSIX_MADV_DONTNEED;
    }) == 1);
    assert(munmap(mapping, 3 * page_size) == 0);
}

void test_reclaim_counts_only_successful_dontneed_bytes() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const first = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    void * const second = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(first != MAP_FAILED && second != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "1"};
    int dontneed_count{0};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice != POSIX_MADV_DONTNEED) return 0;
            ++dontneed_count;
            return dontneed_count == 1 ? 0 : -1;
        }};
        scheduler.register_expert_tensor("blk.11.first", first, 2 * page_size, 11, 2);
        scheduler.register_expert_tensor("blk.11.second", second, 2 * page_size, 11, 2);
        const int predicted[] = {0, 1};
        const int selected{0};
        const uint64_t generation = scheduler.prefetch_experts(11, predicted, 2);
        assert(generation != 0);
        scheduler.cache_router_experts(11, &selected, 1, generation);
        const auto stats = scheduler.expert_reclaim_statistics();
        assert(dontneed_count == 2);
        assert(stats.candidate_experts == 1);
        assert(stats.calls == 2);
        assert(stats.reclaimed_bytes == page_size);
        assert(stats.madvise_failures == 1);
    }
    assert(munmap(first, 2 * page_size) == 0);
    assert(munmap(second, 2 * page_size) == 0);
}

void test_reclaim_propagates_invalid_ids_from_mismatched_tensor_views() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const triple = mmap(nullptr, 3 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    void * const pair = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(triple != MAP_FAILED && pair != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "1"};
    int dontneed_count{0};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice == POSIX_MADV_DONTNEED) ++dontneed_count;
            return 0;
        }};
        scheduler.register_expert_tensor("blk.16.triple", triple, 3 * page_size, 16, 3);
        scheduler.register_expert_tensor("blk.16.pair", pair, 2 * page_size, 16, 2);
        const int predicted{2};
        const int selected{0};
        const uint64_t generation = scheduler.prefetch_experts(16, &predicted, 1);
        assert(generation != 0);
        scheduler.cache_router_experts(16, &selected, 1, generation);
        const auto stats = scheduler.expert_reclaim_statistics();
        assert(dontneed_count == 1);
        assert(stats.candidate_experts == 1);
        assert(stats.calls == 1);
        assert(stats.reclaimed_bytes == page_size);
        assert(stats.invalid_layouts == 0);
        assert(stats.invalid_ids == 1);
    }
    assert(munmap(triple, 3 * page_size) == 0);
    assert(munmap(pair, 2 * page_size) == 0);
}

void test_reclaim_advice_callback_can_read_scheduler_state() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "1"};
    slim_arc::prefetch_scheduler * scheduler_ptr{nullptr};
    bool callback_read_state{false};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice == POSIX_MADV_DONTNEED) {
                assert(scheduler_ptr != nullptr);
                assert((scheduler_ptr->cached_experts_snapshot(17) == std::vector<int>{0}));
                assert(scheduler_ptr->expert_reclaim_statistics().candidate_experts == 1);
                callback_read_state = true;
            }
            return 0;
        }};
        scheduler_ptr = &scheduler;
        scheduler.register_expert_tensor("blk.17.exps", mapping, 2 * page_size, 17, 2);
        const int predicted[] = {0, 1};
        const int selected{0};
        const uint64_t generation = scheduler.prefetch_experts(17, predicted, 2);
        assert(generation != 0);
        scheduler.cache_router_experts(17, &selected, 1, generation);
        assert(callback_read_state);
    }
    assert(munmap(mapping, 2 * page_size) == 0);
}

void test_reclaim_consumes_only_exact_successful_generation_once() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "1"};
    int dontneed_count{0};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice == POSIX_MADV_DONTNEED) ++dontneed_count;
            return 0;
        }};
        scheduler.register_expert_tensor("blk.12.exps", mapping, 2 * page_size, 12, 2);
        const int predicted[] = {0, 1};
        const int selected{0};
        const uint64_t settled = scheduler.prefetch_experts(12, predicted, 2);
        assert(settled != 0);
        scheduler.cache_router_experts(12, &selected, 1, settled);
        scheduler.cache_router_experts(12, &selected, 1, settled);
        scheduler.cache_router_experts(12, &selected, 1, settled + 1000);
        const uint64_t cancelled = scheduler.prefetch_experts(12, predicted, 2);
        assert(cancelled != 0);
        scheduler.cancel_expert_prefetch(12, cancelled);
        scheduler.cache_router_experts(12, &selected, 1, cancelled);
        scheduler.cache_router_experts(12, &selected, 1, 0);
        assert(dontneed_count == 1);
        const auto stats = scheduler.expert_reclaim_statistics();
        assert(stats.candidate_experts == 1);
        assert(stats.calls == 1);
    }
    assert(munmap(mapping, 2 * page_size) == 0);
}

void test_reclaim_skips_subpage_unaligned_ranges_and_rejects_invalid_page_size() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 3 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "1"};
    int dontneed_count{0};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice == POSIX_MADV_DONTNEED) ++dontneed_count;
            return 0;
        }};
        scheduler.register_expert_tensor("blk.13.exps", static_cast<uint8_t *>(mapping) + 1, 2 * page_size, 13, 2);
        const int predicted[] = {0, 1};
        const int selected{0};
        const uint64_t generation = scheduler.prefetch_experts(13, predicted, 2);
        assert(generation != 0);
        scheduler.cache_router_experts(13, &selected, 1, generation);
        const auto stats = scheduler.expert_reclaim_statistics();
        assert(dontneed_count == 0);
        assert(stats.candidate_experts == 1);
        assert(stats.calls == 0);
        assert(stats.skipped_bytes == page_size);
    }
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [](void *, size_t, int) { return 0; }, [] { return -1L; }};
        scheduler.register_expert_tensor("blk.14.exps", mapping, 2 * page_size, 14, 2);
        const int predicted[] = {0, 1};
        const int selected{0};
        const uint64_t generation = scheduler.prefetch_experts(14, predicted, 2);
        assert(generation != 0);
        scheduler.cache_router_experts(14, &selected, 1, generation);
        const auto stats = scheduler.expert_reclaim_statistics();
        assert(stats.candidate_experts == 1);
        assert(stats.calls == 0);
        assert(stats.invalid_layouts == 1);
    }
    assert(munmap(mapping, 3 * page_size) == 0);
}

void test_reclaim_never_advises_after_shutdown() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env reclaim{"SLIM_ARC_EXPERT_RECLAIM_WASTE", "1"};
    int dontneed_count{0};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice == POSIX_MADV_DONTNEED) ++dontneed_count;
            return 0;
        }};
        scheduler.register_expert_tensor("blk.15.exps", mapping, 2 * page_size, 15, 2);
        const int predicted[] = {0, 1};
        const int selected{0};
        const uint64_t generation = scheduler.prefetch_experts(15, predicted, 2);
        assert(generation != 0);
        scheduler.shutdown();
        scheduler.cache_router_experts(15, &selected, 1, generation);
        assert(scheduler.pending_expert_records(15) == 1);
        assert(dontneed_count == 0);
        assert_zero_reclaim_stats(scheduler.expert_reclaim_statistics());
    }
    assert(munmap(mapping, 2 * page_size) == 0);
}

} // namespace

int main() {
    test_selection_skips_items_that_do_not_fit();
    test_zero_and_exact_budgets();
    test_totals_saturate_near_uint64_max();
    test_two_workers_claim_identical_layer_requests_exactly_once_each();
    test_two_workers_claim_distinguishable_layers_without_duplication();
    test_request_queue_is_bounded_and_drops_oldest_unclaimed();
    test_concurrent_shutdown_callers_return_only_after_join();
    test_confidence_flag_requires_exact_one();
    test_popularity_accepts_only_complete_range_zero_to_sixty_four();
    test_scheduler_enforces_budget_and_counts_success();
    test_scheduler_counts_madvise_failure_without_issuing_bytes();
    test_zero_expert_budget_disables_expert_prefetch();
    test_cached_expert_snapshot_does_not_change_after_router_update();
    test_duplicate_router_ids_do_not_overcount_hits_or_underflow_waste();
    test_partial_expert_advice_failure_accounts_only_successful_bytes();
    test_same_layer_generations_settle_in_reverse_order_once();
    test_zero_generation_updates_predictor_without_settling_metrics();
    test_pending_generations_are_bounded_before_advice();
    test_cancelled_generation_counts_once_as_waste();
    test_prefetch_cancel_cycles_do_not_exhaust_pending_slots();
    test_reclaim_flag_off_preserves_legacy_settlement_without_dontneed();
    test_reclaim_flag_requires_exact_one();
    test_reclaim_excludes_selected_experts_and_uses_only_dontneed();
    test_reclaim_counts_only_successful_dontneed_bytes();
    test_reclaim_propagates_invalid_ids_from_mismatched_tensor_views();
    test_reclaim_advice_callback_can_read_scheduler_state();
    test_reclaim_consumes_only_exact_successful_generation_once();
    test_reclaim_skips_subpage_unaligned_ranges_and_rejects_invalid_page_size();
    test_reclaim_never_advises_after_shutdown();
    return 0;
}
