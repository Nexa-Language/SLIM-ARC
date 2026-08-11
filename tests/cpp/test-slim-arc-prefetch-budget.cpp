#include "slim-arc-prefetch.h"

#include <cassert>
#include <chrono>
#include <cstdint>
#include <limits>
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
        scheduler.prefetch_experts(1, &expert_id, 1);
        assert(scheduler.expert_prefetch_bytes() == 0);
    }
    assert(munmap(mapping, page_size) == 0);
}

} // namespace

int main() {
    test_selection_skips_items_that_do_not_fit();
    test_zero_and_exact_budgets();
    test_totals_saturate_near_uint64_max();
    test_scheduler_enforces_budget_and_counts_success();
    test_scheduler_counts_madvise_failure_without_issuing_bytes();
    test_zero_expert_budget_disables_expert_prefetch();
    return 0;
}
