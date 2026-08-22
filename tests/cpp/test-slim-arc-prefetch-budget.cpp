#include "slim-arc-prefetch.h"

#include <cassert>
#include <algorithm>
#include <chrono>
#include <cstring>
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

void test_slow_storage_latest_generation_replaces_unclaimed_work() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(
        nullptr,
        3 * page_size,
        PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON,
        -1,
        0);
    assert(mapping != MAP_FAILED);
    scoped_env slow_storage{"SLIM_ARC_SLOW_STORAGE", "1"};
    std::promise<void> claimed;
    std::promise<void> release;
    std::atomic<bool> first{true};
    std::shared_future<void> release_gate = release.get_future().share();
    std::mutex advised_mtx;
    std::vector<uintptr_t> advised;
    {
        slim_arc::prefetch_scheduler scheduler{
            4,
            3,
            [&] {
                if (first.exchange(false)) {
                    claimed.set_value();
                    release_gate.wait();
                }
            },
            [&](void * address, size_t length, int advice) {
                assert(advice == POSIX_MADV_WILLNEED);
                assert(length == page_size);
                std::lock_guard<std::mutex> lock(advised_mtx);
                advised.push_back(reinterpret_cast<uintptr_t>(address));
                return 0;
            }};
        scheduler.register_tensor("blk.1.weight", mapping, page_size, 1);
        scheduler.register_tensor(
            "blk.2.weight",
            static_cast<uint8_t *>(mapping) + page_size,
            page_size,
            2);
        scheduler.register_tensor(
            "blk.3.weight",
            static_cast<uint8_t *>(mapping) + 2 * page_size,
            page_size,
            3);
        scheduler.set_memory_budget(page_size);
        scheduler.notify_layer_compute(0);
        claimed.get_future().wait();
        scheduler.notify_layer_compute(1);
        scheduler.notify_layer_compute(2);
        assert(scheduler.pending_request_count() == 1);
        release.set_value();
        wait_for_rounds(scheduler, 2);
        scheduler.shutdown();

        const auto stats = scheduler.budget_stats();
        assert(stats.stale_requests == 1);
        assert(stats.stale_bytes == page_size);
        assert(stats.inflight_peak_bytes <= page_size);
        assert(stats.requested_bytes == 2 * page_size);
        std::lock_guard<std::mutex> lock(advised_mtx);
        assert(advised.size() == 2);
        assert(advised[0] == reinterpret_cast<uintptr_t>(mapping));
        assert(advised[1] == reinterpret_cast<uintptr_t>(mapping) + 2 * page_size);
    }
    assert(munmap(mapping, 3 * page_size) == 0);
}

void test_slow_storage_same_layer_duplicate_is_coalesced() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(
        nullptr,
        2 * page_size,
        PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON,
        -1,
        0);
    assert(mapping != MAP_FAILED);
    scoped_env slow_storage{"SLIM_ARC_SLOW_STORAGE", "1"};
    std::promise<void> claimed;
    std::promise<void> release;
    std::atomic<bool> first{true};
    std::shared_future<void> release_gate = release.get_future().share();
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, [&] {
            if (first.exchange(false)) {
                claimed.set_value();
                release_gate.wait();
            }
        }};
        scheduler.register_tensor("blk.1.weight", mapping, page_size, 1);
        scheduler.register_tensor(
            "blk.2.weight",
            static_cast<uint8_t *>(mapping) + page_size,
            page_size,
            2);
        scheduler.set_memory_budget(page_size);
        scheduler.notify_layer_compute(0);
        claimed.get_future().wait();
        scheduler.notify_layer_compute(1);
        scheduler.notify_layer_compute(1);
        assert(scheduler.pending_request_count() == 1);
        release.set_value();
        wait_for_rounds(scheduler, 2);
        scheduler.shutdown();
        const auto stats = scheduler.budget_stats();
        assert(stats.stale_requests == 0);
        assert(stats.requested_bytes == 2 * page_size);
        assert(stats.inflight_peak_bytes <= page_size);
    }
    assert(munmap(mapping, 2 * page_size) == 0);
}

void test_router_prefetch_advises_only_always_used_router_weights() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 3 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env router_prefetch{"SLIM_ARC_ROUTER_PREFETCH", "1"};
    std::vector<std::pair<uintptr_t, size_t>> advised;
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void * address, size_t length, int advice) {
            assert(advice == POSIX_MADV_WILLNEED);
            advised.emplace_back(reinterpret_cast<uintptr_t>(address), length);
            return 0;
        }};
        scheduler.register_tensor("blk.0.attn_q.weight", mapping, page_size, 0);
        scheduler.register_tensor(
            "blk.1.ffn_gate_inp.weight",
            static_cast<uint8_t *>(mapping) + page_size,
            page_size,
            1);
        scheduler.register_tensor(
            "blk.2.ffn_gate_inp_shexp.weight",
            static_cast<uint8_t *>(mapping) + 2 * page_size,
            page_size,
            2);
        scheduler.set_memory_budget(2 * page_size);
        scheduler.notify_layer_compute(0);
        wait_for_rounds(scheduler, 1);
        scheduler.shutdown();
        const auto stats = scheduler.budget_stats();
        assert(stats.requested_bytes == 2 * page_size);
        assert(stats.issued_bytes == 2 * page_size);
    }
    assert(advised.size() == 1);
    assert(advised[0].first == reinterpret_cast<uintptr_t>(mapping) + page_size);
    assert(advised[0].second == 2 * page_size);
    assert(munmap(mapping, 3 * page_size) == 0);
}

void test_no_expert_prefetch_keeps_router_observation_without_advice() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env no_expert_prefetch{"SLIM_ARC_NO_EXPERT_PREFETCH", "1"};
    size_t advice_calls = 0;
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int) {
            ++advice_calls;
            return 0;
        }};
        scheduler.register_expert_tensor("blk.1.ffn_down_exps.weight", mapping, 2 * page_size, 1, 2);
        const int selected = 1;
        scheduler.cache_router_experts(1, &selected, 1);
        assert(scheduler.prefetch_experts(1, &selected, 1) == 0);
        assert((scheduler.cached_experts_snapshot(1) == std::vector<int>{1}));
    }
    assert(advice_calls == 0);
    assert(munmap(mapping, 2 * page_size) == 0);
}

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

void test_scheduler_aligns_and_coalesces_overlapping_tensor_ranges() {
    const long raw_page_size = sysconf(_SC_PAGESIZE);
    assert(raw_page_size > 0);
    const size_t page_size = static_cast<size_t>(raw_page_size);
    void * const mapping = mmap(
        nullptr,
        3 * page_size,
        PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON,
        -1,
        0);
    assert(mapping != MAP_FAILED);
    const uintptr_t base = reinterpret_cast<uintptr_t>(mapping);
    std::atomic<size_t> callback_count{0};
    {
        slim_arc::prefetch_scheduler scheduler{
            1,
            1,
            {},
            [&](void * address, size_t length, int advice) {
                assert(advice == POSIX_MADV_WILLNEED);
                assert(reinterpret_cast<uintptr_t>(address) == base);
                assert(length == 2 * page_size);
                assert(reinterpret_cast<uintptr_t>(address) % page_size == 0);
                assert(length % page_size == 0);
                callback_count.fetch_add(1);
                return 0;
            },
            [raw_page_size] { return raw_page_size; }};
        scheduler.register_tensor(
            "blk.1.first",
            reinterpret_cast<void *>(base + 32),
            page_size,
            1);
        scheduler.register_tensor(
            "blk.1.second",
            reinterpret_cast<void *>(base + page_size + 128),
            page_size / 2,
            1);
        scheduler.set_memory_budget(2 * page_size);
        scheduler.notify_layer_compute(0);
        wait_for_rounds(scheduler, 1);
        scheduler.shutdown();

        const auto stats = scheduler.budget_stats();
        assert(callback_count.load() == 1);
        assert(stats.requested_bytes == page_size + page_size / 2);
        assert(stats.covered_bytes == 2 * page_size);
        assert(stats.issued_bytes == 2 * page_size);
        assert(stats.skipped_bytes == 0);
        assert(stats.advice_requests == 2);
        assert(stats.coalesced_ranges == 1);
        assert(stats.invalid_ranges == 0);
        assert(stats.madvise_failures == 0);
    }
    assert(munmap(mapping, 3 * page_size) == 0);
}

void test_scheduler_counts_aligned_advice_failure_without_issued_bytes() {
    constexpr long page_size = 4096;
    std::atomic<size_t> callback_count{0};
    slim_arc::prefetch_scheduler scheduler{
        1,
        1,
        {},
        [&](void * address, size_t length, int advice) {
            assert(advice == POSIX_MADV_WILLNEED);
            assert(reinterpret_cast<uintptr_t>(address) == 0x2000);
            assert(length == 0x2000);
            callback_count.fetch_add(1);
            return 22;
        },
        [] { return page_size; }};
    scheduler.register_tensor("blk.1.unaligned", reinterpret_cast<void *>(0x2003), 0x1000, 1);
    scheduler.set_memory_budget(0x2000);
    scheduler.notify_layer_compute(0);
    wait_for_rounds(scheduler, 1);
    scheduler.shutdown();

    const auto stats = scheduler.budget_stats();
    assert(callback_count.load() == 1);
    assert(stats.requested_bytes == 0x1000);
    assert(stats.covered_bytes == 0x2000);
    assert(stats.issued_bytes == 0);
    assert(stats.advice_requests == 1);
    assert(stats.coalesced_ranges == 1);
    assert(stats.invalid_ranges == 0);
    assert(stats.madvise_failures == 1);
}

void test_scheduler_rejects_invalid_page_size_without_advice() {
    std::atomic<size_t> callback_count{0};
    slim_arc::prefetch_scheduler scheduler{
        1,
        1,
        {},
        [&](void *, size_t, int) {
            callback_count.fetch_add(1);
            return 0;
        },
        [] { return 0; }};
    scheduler.register_tensor("blk.1.weight", reinterpret_cast<void *>(0x2000), 0x1000, 1);
    scheduler.set_memory_budget(0x1000);
    scheduler.notify_layer_compute(0);
    wait_for_rounds(scheduler, 1);
    scheduler.shutdown();

    const auto stats = scheduler.budget_stats();
    assert(callback_count.load() == 0);
    assert(stats.requested_bytes == 0x1000);
    assert(stats.covered_bytes == 0);
    assert(stats.issued_bytes == 0);
    assert(stats.advice_requests == 1);
    assert(stats.coalesced_ranges == 0);
    assert(stats.invalid_ranges == 1);
    assert(stats.madvise_failures == 1);
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

void test_expert_prefetch_aligns_coalesces_and_attributes_successful_pages_once() {
    constexpr size_t page_size = 4096;
    constexpr size_t mapping_size = 7 * 1024 * 1024;
    constexpr size_t first_offset = 864;
    constexpr size_t second_offset = 3 * 1024 * 1024 + 1632;
    constexpr size_t third_offset = 5 * 1024 * 1024 + 2400;
    constexpr size_t first_slice = 860160;
    constexpr size_t other_slice = 589824;
    void * const mapping = mmap(
        nullptr,
        mapping_size,
        PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON,
        -1,
        0);
    assert(mapping != MAP_FAILED);
    const uintptr_t base = reinterpret_cast<uintptr_t>(mapping);
    const uintptr_t failed_range_address = base + 3 * 1024 * 1024;
    std::vector<std::pair<uintptr_t, size_t>> calls;
    {
        slim_arc::prefetch_scheduler scheduler{
            1,
            1,
            {},
            [&](void * address, size_t length, int advice) {
                assert(advice == POSIX_MADV_WILLNEED);
                const uintptr_t numeric_address = reinterpret_cast<uintptr_t>(address);
                assert(numeric_address % page_size == 0);
                assert(length % page_size == 0);
                calls.emplace_back(numeric_address, length);
                return numeric_address == failed_range_address ? 5 : 0;
            },
            [] { return static_cast<long>(page_size); }};
        scheduler.register_expert_tensor(
            "blk.3.down_exps",
            reinterpret_cast<void *>(base + first_offset),
            2 * first_slice,
            3,
            2);
        scheduler.register_expert_tensor(
            "blk.3.gate_exps",
            reinterpret_cast<void *>(base + second_offset),
            2 * other_slice,
            3,
            2);
        scheduler.register_expert_tensor(
            "blk.3.up_exps",
            reinterpret_cast<void *>(base + third_offset),
            2 * other_slice,
            3,
            2);

        const uint64_t all_covered_bytes =
            2 * first_slice + 4 * other_slice + 3 * page_size;
        scheduler.set_expert_budget(all_covered_bytes);
        const int expert_ids[] = {0, 1};
        const uint64_t generation = scheduler.prefetch_experts(3, expert_ids, 2);
        assert(generation != 0);
        assert(scheduler.pending_expert_records(3) == 1);

        assert(calls.size() == 3);
        assert(calls[0] == std::make_pair(base, 2 * first_slice + page_size));
        assert(calls[1] == std::make_pair(failed_range_address, 2 * other_slice + page_size));
        assert(calls[2] == std::make_pair(base + 5 * 1024 * 1024, 2 * other_slice + page_size));

        const uint64_t successful_issued = 2 * first_slice + 2 * other_slice + 2 * page_size;
        const auto metrics = scheduler.expert_runtime_statistics();
        assert(metrics.issued_bytes == successful_issued);
        assert(metrics.advice_requests == 6);
        assert(metrics.coalesced_ranges == 3);
        assert(metrics.covered_bytes == all_covered_bytes);
        assert(metrics.advice_failures == 1);
        assert(metrics.invalid_ranges == 0);

        const int selected_expert = 1;
        scheduler.cache_router_experts(3, &selected_expert, 1, generation);
        const uint64_t expected_hit = first_slice + other_slice;
        assert(scheduler.expert_hit_bytes() == expected_hit);
        assert(scheduler.expert_waste_bytes() == successful_issued - expected_hit);
        assert(scheduler.expert_hit_bytes() + scheduler.expert_waste_bytes() ==
               scheduler.expert_prefetch_bytes());
    }
    assert(munmap(mapping, mapping_size) == 0);
}

void test_expert_prefetch_rejects_invalid_page_size_without_advice() {
    std::atomic<size_t> callback_count{0};
    slim_arc::prefetch_scheduler scheduler{
        1,
        1,
        {},
        [&](void *, size_t, int) {
            callback_count.fetch_add(1);
            return 0;
        },
        [] { return 0; }};
    scheduler.register_expert_tensor(
        "blk.3.exps",
        reinterpret_cast<void *>(0x2003),
        0x2000,
        3,
        2);
    scheduler.set_expert_budget(0x2000);
    const int expert_id = 0;
    assert(scheduler.prefetch_experts(3, &expert_id, 1) == 0);
    assert(callback_count.load() == 0);
    assert(scheduler.pending_expert_records(3) == 0);
    const auto metrics = scheduler.expert_runtime_statistics();
    assert(metrics.issued_bytes == 0);
    assert(metrics.advice_requests == 1);
    assert(metrics.coalesced_ranges == 0);
    assert(metrics.covered_bytes == 0);
    assert(metrics.advice_failures == 1);
    assert(metrics.invalid_ranges == 1);
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
        const uint64_t generation = scheduler.prefetch_experts(14, predicted, 2);
        assert(generation == 0);
        const auto metrics = scheduler.expert_runtime_statistics();
        assert(metrics.advice_requests == 2);
        assert(metrics.invalid_ranges == 2);
        assert(metrics.advice_failures == 2);
        const auto stats = scheduler.expert_reclaim_statistics();
        assert(stats.candidate_experts == 0);
        assert(stats.calls == 0);
        assert(stats.invalid_layouts == 0);
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

void test_residency_flag_requires_exact_one_and_disabled_stats_stay_zero() {
    const char * values[] = {nullptr, "0", "", "false", "invalid"};
    for (const char * value : values) {
        scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", value};
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [](void *, size_t, int) { return 0; }};
        assert(!scheduler.expert_residency_enabled());
        scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::critical, 4096);
        const auto stats = scheduler.expert_residency_statistics();
        assert(stats.samples == 0);
        assert(stats.admitted_experts == 0);
        assert(stats.admitted_bytes == 0);
        assert(stats.skipped_bytes == 0);
        assert(stats.fallbacks == 0);
        assert(stats.pressure_normal == 0);
        assert(stats.pressure_high == 0);
        assert(stats.pressure_critical == 0);
    }
    scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", "1"};
    slim_arc::prefetch_scheduler scheduler{1, 1};
    assert(scheduler.expert_residency_enabled());
}

void test_residency_pressure_selects_stable_then_temporal_and_accounts_once() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 4 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", "1"};
    std::vector<int> advised;
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void * addr, size_t, int advice) {
            if (advice == POSIX_MADV_WILLNEED) {
                advised.push_back(static_cast<int>((static_cast<uint8_t *>(addr) - static_cast<uint8_t *>(mapping)) / page_size));
            }
            return 0;
        }};
        scheduler.register_expert_tensor("blk.18.exps", mapping, 4 * page_size, 18, 4);
        const int first[] = {1, 3};
        const int second[] = {1, 2};
        scheduler.cache_router_experts(18, first, 2);
        scheduler.cache_router_experts(18, second, 2);

        scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::critical, 2 * page_size);
        assert(scheduler.prefetch_experts(18, second, 2) == 0);
        assert(advised.empty());

        scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::high, 2 * page_size);
        const uint64_t high = scheduler.prefetch_experts(18, second, 2);
        assert(high != 0);
        assert((advised == std::vector<int>{1}));
        scheduler.cancel_expert_prefetch(18, high);

        advised.clear();
        scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::normal, 2 * page_size);
        const uint64_t normal = scheduler.prefetch_experts(18, second, 2);
        assert(normal != 0);
        assert((advised == std::vector<int>{1}));
        scheduler.cancel_expert_prefetch(18, normal);

        const auto stats = scheduler.expert_residency_statistics();
        assert(stats.samples == 3);
        assert(stats.admitted_experts == 3);
        assert(stats.admitted_bytes == 3 * page_size);
        assert(stats.pressure_critical == 1);
        assert(stats.pressure_high == 1);
        assert(stats.pressure_normal == 1);
    }
    assert(munmap(mapping, 4 * page_size) == 0);
}

void test_missing_pressure_preserves_legacy_order_and_counts_fallback() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 4 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", "1"};
    std::vector<int> advised;
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void * addr, size_t, int advice) {
            if (advice == POSIX_MADV_WILLNEED) advised.push_back(static_cast<int>(
                (static_cast<uint8_t *>(addr) - static_cast<uint8_t *>(mapping)) / page_size));
            return 0;
        }};
        scheduler.register_expert_tensor("blk.19.exps", mapping, 4 * page_size, 19, 4);
        const int requested[] = {2, 1};
        scheduler.set_expert_budget(2 * page_size);
        scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::missing, 2 * page_size);
        const uint64_t generation = scheduler.prefetch_experts(19, requested, 2);
        assert(generation != 0);
        assert((advised == std::vector<int>{1}));
        const auto stats = scheduler.expert_residency_statistics();
        assert(stats.samples == 1);
        assert(stats.fallbacks == 1);
        assert(stats.pressure_missing == 1);
    }
    assert(munmap(mapping, 4 * page_size) == 0);
}

void test_popularity_saturates_and_decays_once_at_global_sixty_fourth_sample() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 4 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", "1"};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.20.exps", mapping, 2 * page_size, 20, 2);
        scheduler.register_expert_tensor("blk.21.exps", static_cast<uint8_t *>(mapping) + 2 * page_size, 2 * page_size, 21, 2);
        const int zero = 0;
        for (int sample = 0; sample < 63; ++sample) {
            scheduler.cache_router_experts(sample % 2 == 0 ? 20 : 21, &zero, 1);
        }
        const int invalid = -1;
        scheduler.cache_router_experts(20, &invalid, 1);
        const auto before20 = scheduler.expert_popularity_snapshot(20);
        const auto before21 = scheduler.expert_popularity_snapshot(21);
        assert(before20[0] == 32);
        assert(before21[0] == 31);
        scheduler.cache_router_experts(21, &zero, 1);
        const auto after20 = scheduler.expert_popularity_snapshot(20);
        const auto after21 = scheduler.expert_popularity_snapshot(21);
        assert(after20[0] == 16);
        assert(after21[0] == 16);
        assert(scheduler.popularity_decay_count() == 1);
    }
    assert(munmap(mapping, 4 * page_size) == 0);
}

void test_successful_generation_settlement_updates_waste_ewma_once() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 10 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", "1"};
    {
        size_t advice_calls{0};
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice == POSIX_MADV_WILLNEED) ++advice_calls;
            return 0;
        }};
        scheduler.register_expert_tensor("blk.22.exps", mapping, 10 * page_size, 22, 10);
        const int predicted[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
        scheduler.cache_router_experts(22, predicted, 10);
        struct sample_expectation {
            int hits;
            uint32_t ewma;
            bool restricted;
        };
        const std::vector<sample_expectation> samples{
            {2, 800, true}, {2, 800, true}, {7, 675, true}, {7, 581, false},
        };
        const std::vector<size_t> expected_normal_advice{1, 1, 1, 1};
        const std::vector<uint64_t> expected_normal_experts{2, 2, 2, 10};
        for (size_t index = 0; index < samples.size(); ++index) {
            const sample_expectation & sample = samples[index];
            scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::missing, 10 * page_size);
            const uint64_t generation = scheduler.prefetch_experts(22, predicted, 10);
            assert(generation != 0);
            scheduler.cache_router_experts(22, predicted, sample.hits, generation);
            assert(scheduler.expert_waste_ewma_milli() == sample.ewma);
            assert(scheduler.expert_waste_restricted() == sample.restricted);
            advice_calls = 0;
            scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::normal, 10 * page_size);
            const uint64_t admitted_before = scheduler.expert_residency_statistics().admitted_experts;
            const uint64_t selection = scheduler.prefetch_experts(22, predicted, sample.hits);
            assert(selection != 0);
            assert(advice_calls == expected_normal_advice[index]);
            assert(scheduler.expert_residency_statistics().admitted_experts - admitted_before ==
                   expected_normal_experts[index]);
            scheduler.cancel_expert_prefetch(22, selection);
        }
        assert(scheduler.expert_waste_sample_count() == 4);
    }
    assert(munmap(mapping, 10 * page_size) == 0);
}

std::vector<int> capture_legacy_target(const char * residency_value) {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 4 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", residency_value};
    scoped_env popularity{"SLIM_ARC_EXPERT_POP", "1"};
    std::vector<int> advised;
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void * addr, size_t, int advice) {
            if (advice == POSIX_MADV_WILLNEED) advised.push_back(static_cast<int>(
                (static_cast<uint8_t *>(addr) - static_cast<uint8_t *>(mapping)) / page_size));
            return 0;
        }};
        scheduler.register_expert_tensor("blk.23.exps", mapping, 4 * page_size, 23, 4);
        const int hot = 3;
        scheduler.cache_router_experts(23, &hot, 1);
        const int requested[] = {2, 1};
        if (residency_value != nullptr && std::string{residency_value} == "1") {
            scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::missing, 3 * page_size);
        }
        const uint64_t generation = scheduler.prefetch_experts(23, requested, 2);
        assert(generation != 0);
    }
    assert(munmap(mapping, 4 * page_size) == 0);
    return advised;
}

void test_flag_off_target_and_advice_order_equal_legacy_path() {
    const std::vector<int> legacy = capture_legacy_target(nullptr);
    assert((legacy == std::vector<int>{1}));
    for (const char * value : {"0", "", "false"}) {
        assert(capture_legacy_target(value) == legacy);
    }
    assert(capture_legacy_target("1") == legacy);
}

void test_residency_advice_callback_can_read_expert_state_without_deadlock() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 2 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    scoped_env residency{"SLIM_ARC_EXPERT_RESIDENCY", "1"};
    slim_arc::prefetch_scheduler * scheduler_ptr{nullptr};
    bool callback_read_state{false};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1, {}, [&](void *, size_t, int advice) {
            if (advice == POSIX_MADV_WILLNEED) {
                assert(scheduler_ptr != nullptr);
                assert(scheduler_ptr->current_expert_pressure() == slim_arc::expert_pressure_state::normal);
                assert(!scheduler_ptr->expert_popularity_snapshot(24).empty());
                assert(scheduler_ptr->expert_residency_statistics().samples == 1);
                callback_read_state = true;
            }
            return 0;
        }};
        scheduler_ptr = &scheduler;
        scheduler.register_expert_tensor("blk.24.exps", mapping, 2 * page_size, 24, 2);
        const int selected = 1;
        scheduler.cache_router_experts(24, &selected, 1);
        scheduler.set_expert_residency_pressure(slim_arc::expert_pressure_state::normal, page_size);
        auto prefetch = std::async(std::launch::async, [&] {
            return scheduler.prefetch_experts(24, &selected, 1);
        });
        assert(prefetch.wait_for(std::chrono::seconds{2}) == std::future_status::ready);
        assert(prefetch.get() != 0);
        assert(callback_read_state);
    }
    assert(munmap(mapping, 2 * page_size) == 0);
}

void test_expert_hot_cache_requires_stability_and_respects_budget() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    const size_t expert_bytes = 48 * page_size;
    const size_t tensor_bytes = 2 * expert_bytes;
    void * const first = mmap(nullptr, tensor_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    void * const second = mmap(nullptr, tensor_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(first != MAP_FAILED);
    assert(second != MAP_FAILED);
    std::memset(first, 1, tensor_bytes);
    std::memset(second, 1, tensor_bytes);

    scoped_env hot_budget{"SLIM_ARC_EXPERT_HOT_MB", "1"};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.25.exps", first, tensor_bytes, 25, 2);
        scheduler.register_expert_tensor("blk.26.exps", second, tensor_bytes, 26, 2);
        const int expert_zero = 0;
        scheduler.cache_router_experts(25, &expert_zero, 1);
        assert(scheduler.expert_hot_cache_statistics().locked_bytes == 0);
        scheduler.cache_router_experts(25, &expert_zero, 1);
        const auto admitted = scheduler.expert_hot_cache_statistics();
        assert(admitted.admissions == 1);
        assert(admitted.locked_bytes == expert_bytes);
        assert(admitted.locked_bytes <= admitted.budget_bytes);

        scheduler.cache_router_experts(25, &expert_zero, 1);
        assert(scheduler.expert_hot_cache_statistics().hits == 1);
        scheduler.cache_router_experts(26, &expert_zero, 1);
        scheduler.cache_router_experts(26, &expert_zero, 1);
        const auto full = scheduler.expert_hot_cache_statistics();
        assert(full.admissions == 1);
        assert(full.budget_rejections == 1);
        assert(full.locked_bytes == expert_bytes);

        const int expert_one = 1;
        scheduler.cache_router_experts(25, &expert_one, 1);
        scheduler.cache_router_experts(25, &expert_one, 1);
        const auto replaced = scheduler.expert_hot_cache_statistics();
        assert(replaced.admissions == 2);
        assert(replaced.evictions == 1);
        assert(replaced.locked_bytes == expert_bytes);
    }
    assert(munmap(first, tensor_bytes) == 0);
    assert(munmap(second, tensor_bytes) == 0);
}

void test_expert_hot_cache_accepts_one_gib_budget_boundary() {
    {
        scoped_env hot_budget{"SLIM_ARC_EXPERT_HOT_MB", "1024"};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(scheduler.expert_hot_cache_statistics().budget_bytes == (1ULL << 30));
    }
    {
        scoped_env hot_budget{"SLIM_ARC_EXPERT_HOT_MB", "1025"};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(scheduler.expert_hot_cache_statistics().budget_bytes == 0);
    }
}

void test_expert_hot_lru_retains_gap_reuse_and_evicts_oldest_entry() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    const size_t expert_bytes = 24 * page_size;
    void * const first = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    void * const second = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    void * const third = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(first != MAP_FAILED);
    assert(second != MAP_FAILED);
    assert(third != MAP_FAILED);
    std::memset(first, 1, expert_bytes);
    std::memset(second, 1, expert_bytes);
    std::memset(third, 1, expert_bytes);

    scoped_env hot_budget{"SLIM_ARC_EXPERT_HOT_MB", "1"};
    scoped_env hot_lru{"SLIM_ARC_EXPERT_HOT_LRU", "1"};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.25.exps", first, expert_bytes, 25, 1);
        scheduler.register_expert_tensor("blk.26.exps", second, expert_bytes, 26, 1);
        scheduler.register_expert_tensor("blk.27.exps", third, expert_bytes, 27, 1);
        const int expert_zero = 0;

        scheduler.cache_router_experts(25, &expert_zero, 1);
        scheduler.cache_router_experts(25, &expert_zero, 1);
        scheduler.cache_router_experts(26, &expert_zero, 1);
        scheduler.cache_router_experts(26, &expert_zero, 1);
        scheduler.cache_router_experts(25, &expert_zero, 1);

        scheduler.cache_router_experts(27, &expert_zero, 1);
        scheduler.cache_router_experts(27, &expert_zero, 1);
        const auto after_eviction = scheduler.expert_hot_cache_statistics();
        assert(after_eviction.admissions == 3);
        assert(after_eviction.hits == 1);
        assert(after_eviction.evictions == 1);
        assert(after_eviction.entries == 2);
        assert(after_eviction.locked_bytes == 2 * expert_bytes);

        scheduler.cache_router_experts(25, &expert_zero, 1);
        assert(scheduler.expert_hot_cache_statistics().hits == 2);
        scheduler.cache_router_experts(26, &expert_zero, 1);
        const auto reloaded_oldest = scheduler.expert_hot_cache_statistics();
        assert(reloaded_oldest.admissions == 4);
        assert(reloaded_oldest.evictions == 2);
        assert(reloaded_oldest.entries == 2);
        assert(reloaded_oldest.locked_bytes == 2 * expert_bytes);
    }
    assert(munmap(first, expert_bytes) == 0);
    assert(munmap(second, expert_bytes) == 0);
    assert(munmap(third, expert_bytes) == 0);
}

void test_expert_hot_lfru_requires_exact_pair() {
    for (const char * value : {"0", "01", "true", ""}) {
        scoped_env hot_lru{"SLIM_ARC_EXPERT_HOT_LRU", "1"};
        scoped_env hot_lfru{"SLIM_ARC_EXPERT_HOT_LFRU", value};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(!scheduler.expert_hot_lfru_enabled());
    }
    {
        scoped_env hot_lru{"SLIM_ARC_EXPERT_HOT_LRU", "0"};
        scoped_env hot_lfru{"SLIM_ARC_EXPERT_HOT_LFRU", "1"};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(!scheduler.expert_hot_lfru_enabled());
    }
    {
        scoped_env hot_lru{"SLIM_ARC_EXPERT_HOT_LRU", "1"};
        scoped_env hot_lfru{"SLIM_ARC_EXPERT_HOT_LFRU", "1"};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(scheduler.expert_hot_lfru_enabled());
    }
}

void test_expert_hot_lfru_retains_frequent_idle_entry() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    const size_t budget_bytes = 1ULL << 20;
    const size_t expert_bytes = budget_bytes / 2 / page_size * page_size;
    assert(expert_bytes > 0);

    const auto run = [&](bool lfru_enabled) {
        void * const first = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
        void * const second = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
        void * const third = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
        assert(first != MAP_FAILED);
        assert(second != MAP_FAILED);
        assert(third != MAP_FAILED);
        std::memset(first, 1, expert_bytes);
        std::memset(second, 1, expert_bytes);
        std::memset(third, 1, expert_bytes);

        scoped_env hot_budget{"SLIM_ARC_EXPERT_HOT_MB", "1"};
        scoped_env hot_lru{"SLIM_ARC_EXPERT_HOT_LRU", "1"};
        scoped_env hot_lfru{"SLIM_ARC_EXPERT_HOT_LFRU", lfru_enabled ? "1" : "0"};
        {
            slim_arc::prefetch_scheduler scheduler{1, 1};
            scheduler.register_expert_tensor("blk.25.exps", first, expert_bytes, 25, 1);
            scheduler.register_expert_tensor("blk.26.exps", second, expert_bytes, 26, 1);
            scheduler.register_expert_tensor("blk.27.exps", third, expert_bytes, 27, 1);
            const int expert_zero = 0;

            scheduler.cache_router_experts(25, &expert_zero, 1);
            scheduler.cache_router_experts(25, &expert_zero, 1);
            scheduler.cache_router_experts(25, &expert_zero, 1);
            scheduler.cache_router_experts(25, &expert_zero, 1);
            scheduler.cache_router_experts(25, &expert_zero, 1);
            scheduler.cache_router_experts(26, &expert_zero, 1);
            scheduler.cache_router_experts(26, &expert_zero, 1);
            const auto full = scheduler.expert_hot_cache_statistics();
            assert(full.admissions == 2);
            assert(full.hits == 3);
            assert(full.evictions == 0);
            assert(full.entries == 2);
            assert(full.locked_bytes == budget_bytes);

            scheduler.cache_router_experts(27, &expert_zero, 1);
            scheduler.cache_router_experts(27, &expert_zero, 1);
            const auto replaced = scheduler.expert_hot_cache_statistics();
            assert(replaced.admissions == 3);
            assert(replaced.hits == 3);
            assert(replaced.evictions == 1);
            assert(replaced.entries == 2);
            assert(replaced.locked_bytes == budget_bytes);

            scheduler.cache_router_experts(25, &expert_zero, 1);
            const auto after_frequent = scheduler.expert_hot_cache_statistics();
            assert(after_frequent.admissions == (lfru_enabled ? 3 : 4));
            assert(after_frequent.hits == (lfru_enabled ? 4 : 3));
            assert(after_frequent.evictions == (lfru_enabled ? 1 : 2));

            scheduler.cache_router_experts(26, &expert_zero, 1);
            const auto after_recent = scheduler.expert_hot_cache_statistics();
            assert(after_recent.admissions == (lfru_enabled ? 4 : 5));
            assert(after_recent.hits == (lfru_enabled ? 4 : 3));
            assert(after_recent.evictions == (lfru_enabled ? 2 : 3));
            assert(after_recent.entries == 2);
            assert(after_recent.locked_bytes == budget_bytes);
        }

        assert(munmap(first, expert_bytes) == 0);
        assert(munmap(second, expert_bytes) == 0);
        assert(munmap(third, expert_bytes) == 0);
    };

    run(false);
    run(true);
}

void test_expert_hot_admission_filters_only_after_cache_saturates() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    const size_t budget_bytes = 1ULL << 20;
    const size_t expert_bytes = budget_bytes / 2 / page_size * page_size;
    void * const first = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    void * const second = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    void * const third = mmap(nullptr, expert_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(first != MAP_FAILED);
    assert(second != MAP_FAILED);
    assert(third != MAP_FAILED);
    std::memset(first, 1, expert_bytes);
    std::memset(second, 1, expert_bytes);
    std::memset(third, 1, expert_bytes);

    scoped_env hot_budget{"SLIM_ARC_EXPERT_HOT_MB", "1"};
    scoped_env hot_lru{"SLIM_ARC_EXPERT_HOT_LRU", "1"};
    scoped_env admission_hits{"SLIM_ARC_EXPERT_HOT_ADMIT_HITS", "2"};
    {
        slim_arc::prefetch_scheduler scheduler{1, 1};
        scheduler.register_expert_tensor("blk.25.exps", first, expert_bytes, 25, 1);
        scheduler.register_expert_tensor("blk.26.exps", second, expert_bytes, 26, 1);
        scheduler.register_expert_tensor("blk.27.exps", third, expert_bytes, 27, 1);
        const int expert_zero = 0;

        scheduler.set_phase(slim_arc::compute_phase::PREFILL);
        scheduler.cache_router_experts(25, &expert_zero, 1);
        scheduler.cache_router_experts(25, &expert_zero, 1);
        scheduler.cache_router_experts(26, &expert_zero, 1);
        scheduler.cache_router_experts(26, &expert_zero, 1);
        const auto warmed = scheduler.expert_hot_cache_statistics();
        assert(warmed.admission_threshold == 2);
        assert(warmed.admission_skips == 0);
        assert(warmed.admissions == 2);
        assert(warmed.locked_bytes == budget_bytes);

        scheduler.cache_router_experts(27, &expert_zero, 1);
        scheduler.cache_router_experts(27, &expert_zero, 1);
        const auto observed_once = scheduler.expert_hot_cache_statistics();
        assert(observed_once.admission_skips == 1);
        assert(observed_once.admissions == 2);
        assert(observed_once.evictions == 0);
        assert(observed_once.nonresident_bytes == 0);

        scheduler.cache_router_experts(27, &expert_zero, 1);
        const auto admitted = scheduler.expert_hot_cache_statistics();
        assert(admitted.admission_skips == 1);
        assert(admitted.admissions == 3);
        assert(admitted.evictions == 1);
        assert(admitted.locked_bytes == budget_bytes);
    }
    assert(munmap(first, expert_bytes) == 0);
    assert(munmap(second, expert_bytes) == 0);
    assert(munmap(third, expert_bytes) == 0);
}

void test_expert_hot_admission_invalid_threshold_uses_legacy_one_hit() {
    for (const char * value : {"", "0", "65", "true"}) {
        scoped_env admission_hits{"SLIM_ARC_EXPERT_HOT_ADMIT_HITS", value};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(scheduler.expert_hot_cache_statistics().admission_threshold == 1);
    }
}

void test_cross_layer_transition_flag_requires_exact_pair() {
    for (const char * value : {"0", "01", "true", ""}) {
        scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", value};
        scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", "2"};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(!scheduler.cross_layer_transition_enabled());
    }
    for (const char * value : {"0", "65", "2x"}) {
        scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", "1"};
        scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", value};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(!scheduler.cross_layer_transition_enabled());
    }
    {
        scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", "1"};
        scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", nullptr};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(!scheduler.cross_layer_transition_enabled());
    }
    {
        scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", nullptr};
        scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", "2"};
        slim_arc::prefetch_scheduler scheduler{0, 1};
        assert(!scheduler.cross_layer_transition_enabled());
    }
}

void test_scheduler_learns_and_accounts_cross_layer_transition() {
    scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", "1"};
    scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", "2"};
    slim_arc::prefetch_scheduler scheduler{0, 1};
    std::vector<unsigned char> tensor(64 * 4096);
    scheduler.register_expert_tensor("blk.2.ffn_down_exps", tensor.data(), tensor.size(), 2, 64);
    scheduler.register_expert_tensor("blk.3.ffn_down_exps", tensor.data(), tensor.size(), 3, 64);
    assert(scheduler.cross_layer_transition_enabled());
    assert(scheduler.cross_layer_transition_topk() == 2);
    assert(scheduler.predict_expert_transition(2, {1, 2}).empty());

    scheduler.observe_expert_transition(2, {1, 2}, {9, 4});
    const std::vector<int> predicted = scheduler.predict_expert_transition(2, {1, 2});
    assert((predicted == std::vector<int>{4, 9}));
    scheduler.record_expert_transition_result(predicted, {4, 7, 7});

    const auto stats = scheduler.expert_transition_statistics();
    assert(stats.updates == 1);
    assert(stats.prediction_rounds == 2);
    assert(stats.empty_rounds == 1);
    assert(stats.predicted_experts == 2);
    assert(stats.matched_experts == 1);
}

void test_cross_layer_transition_calls_are_thread_safe() {
    scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", "1"};
    scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", "2"};
    slim_arc::prefetch_scheduler scheduler{0, 1};
    std::vector<unsigned char> tensor(8 * 4096);
    scheduler.register_expert_tensor("blk.4.ffn_down_exps", tensor.data(), tensor.size(), 4, 8);

    auto observe = std::async(std::launch::async, [&] {
        scheduler.observe_expert_transition(4, {1, 2}, {3, 4});
    });
    auto predict = std::async(std::launch::async, [&] {
        return scheduler.predict_expert_transition(4, {1, 2});
    });
    assert(observe.wait_for(std::chrono::seconds{2}) == std::future_status::ready);
    assert(predict.wait_for(std::chrono::seconds{2}) == std::future_status::ready);
    observe.get();
    (void) predict.get();
    assert(scheduler.expert_transition_statistics().updates == 1);
}

struct file_advice_call {
    int fd;
    uint64_t offset;
    size_t length;
};

void test_selected_expert_file_advice_uses_exact_mapping_offset() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(
        nullptr,
        6 * page_size,
        PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON,
        -1,
        0);
    assert(mapping != MAP_FAILED);
    scoped_env enabled{"SLIM_ARC_EXPERT_FADVISE", "1"};
    std::vector<file_advice_call> calls;
    {
        slim_arc::prefetch_scheduler scheduler{
            0,
            1,
            {},
            {},
            {},
            [&](int fd, uint64_t offset, size_t length) {
                calls.push_back({fd, offset, length});
                return 0;
            }};
        assert(scheduler.register_mapping(mapping, 6 * page_size, 17));
        scheduler.register_expert_tensor(
            "blk.28.exps",
            static_cast<uint8_t *>(mapping) + page_size,
            4 * page_size,
            28,
            4);
        const int selected = 2;
        scheduler.cache_router_experts(28, &selected, 1);
        const int invalid = -1;
        scheduler.cache_router_experts(28, &invalid, 1);

        assert(calls.size() == 1);
        assert(calls[0].fd == 17);
        assert(calls[0].offset == 3 * page_size);
        assert(calls[0].length == page_size);
        const auto stats = scheduler.expert_file_advice_statistics();
        assert(stats.calls == 1);
        assert(stats.issued_bytes == page_size);
        assert(stats.failures == 0);
        assert(stats.invalid_ranges == 0);
    }
    assert(munmap(mapping, 6 * page_size) == 0);
}

void test_selected_expert_file_advice_is_strictly_opt_in() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    const char * const values[] = {nullptr, "0", "01", "true", ""};
    for (const char * value : values) {
        scoped_env enabled{"SLIM_ARC_EXPERT_FADVISE", value};
        int calls = 0;
        slim_arc::prefetch_scheduler scheduler{
            0,
            1,
            {},
            {},
            {},
            [&](int, uint64_t, size_t) {
                ++calls;
                return 0;
            }};
        assert(scheduler.register_mapping(mapping, page_size, 19));
        scheduler.register_expert_tensor("blk.29.exps", mapping, page_size, 29, 1);
        const int selected = 0;
        scheduler.cache_router_experts(29, &selected, 1);
        assert(calls == 0);
        const auto stats = scheduler.expert_file_advice_statistics();
        assert(stats.calls == 0);
        assert(stats.issued_bytes == 0);
        assert(stats.failures == 0);
        assert(stats.invalid_ranges == 0);
    }
    assert(munmap(mapping, page_size) == 0);
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
    test_slow_storage_latest_generation_replaces_unclaimed_work();
    test_slow_storage_same_layer_duplicate_is_coalesced();
    test_router_prefetch_advises_only_always_used_router_weights();
    test_no_expert_prefetch_keeps_router_observation_without_advice();
    test_confidence_flag_requires_exact_one();
    test_popularity_accepts_only_complete_range_zero_to_sixty_four();
    test_scheduler_enforces_budget_and_counts_success();
    test_scheduler_aligns_and_coalesces_overlapping_tensor_ranges();
    test_scheduler_counts_aligned_advice_failure_without_issued_bytes();
    test_scheduler_rejects_invalid_page_size_without_advice();
    test_scheduler_counts_madvise_failure_without_issuing_bytes();
    test_zero_expert_budget_disables_expert_prefetch();
    test_cached_expert_snapshot_does_not_change_after_router_update();
    test_duplicate_router_ids_do_not_overcount_hits_or_underflow_waste();
    test_partial_expert_advice_failure_accounts_only_successful_bytes();
    test_expert_prefetch_aligns_coalesces_and_attributes_successful_pages_once();
    test_expert_prefetch_rejects_invalid_page_size_without_advice();
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
    test_residency_flag_requires_exact_one_and_disabled_stats_stay_zero();
    test_residency_pressure_selects_stable_then_temporal_and_accounts_once();
    test_missing_pressure_preserves_legacy_order_and_counts_fallback();
    test_popularity_saturates_and_decays_once_at_global_sixty_fourth_sample();
    test_successful_generation_settlement_updates_waste_ewma_once();
    test_flag_off_target_and_advice_order_equal_legacy_path();
    test_residency_advice_callback_can_read_expert_state_without_deadlock();
    test_expert_hot_cache_requires_stability_and_respects_budget();
    test_expert_hot_cache_accepts_one_gib_budget_boundary();
    test_expert_hot_lru_retains_gap_reuse_and_evicts_oldest_entry();
    test_expert_hot_lfru_requires_exact_pair();
    test_expert_hot_lfru_retains_frequent_idle_entry();
    test_expert_hot_admission_filters_only_after_cache_saturates();
    test_expert_hot_admission_invalid_threshold_uses_legacy_one_hit();
    test_cross_layer_transition_flag_requires_exact_pair();
    test_scheduler_learns_and_accounts_cross_layer_transition();
    test_cross_layer_transition_calls_are_thread_safe();
    test_selected_expert_file_advice_uses_exact_mapping_offset();
    test_selected_expert_file_advice_is_strictly_opt_in();
    return 0;
}
