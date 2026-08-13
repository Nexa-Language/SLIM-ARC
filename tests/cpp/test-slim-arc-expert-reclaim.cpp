#include "slim-arc-expert-reclaim.h"

#include <cassert>
#include <cstdint>
#include <limits>
#include <vector>

namespace {

void test_wasted_ids_preserve_first_prefetch_order() {
    const auto wasted = slim_arc::wasted_expert_ids({4, 1, 4, 2, 7, 2, 1}, {2, 2, 9});
    assert((wasted == std::vector<int>{4, 1, 7}));
}

void test_plan_builds_a_page_aligned_expert_slice() {
    const slim_arc::expert_tensor_view tensor{0x1000, 4 * 4096, 4};
    const auto plan = slim_arc::build_expert_reclaim_plan({tensor}, {1}, 4096);
    assert(plan.items.size() == 1);
    assert(plan.items[0].expert_id == 1);
    assert(plan.items[0].address == 0x2000);
    assert(plan.items[0].length == 4096);
    assert(plan.items[0].skipped_bytes == 0);
    assert(plan.invalid_layouts == 0);
    assert(plan.invalid_ids == 0);
    assert(plan.skipped_bytes == 0);
}

void test_plan_counts_negative_and_out_of_range_ids() {
    const slim_arc::expert_tensor_view tensor{0x1000, 2 * 4096, 2};
    const auto plan = slim_arc::build_expert_reclaim_plan({tensor}, {-1, 2, 1}, 4096);
    assert(plan.items.size() == 1);
    assert(plan.items[0].expert_id == 1);
    assert(plan.invalid_ids == 2);
    assert(plan.invalid_layouts == 0);
}

void test_plan_rejects_a_zero_expert_layout() {
    const slim_arc::expert_tensor_view tensor{0x1000, 4096, 0};
    const auto plan = slim_arc::build_expert_reclaim_plan({tensor}, {0}, 4096);
    assert(plan.items.empty());
    assert(plan.invalid_layouts == 1);
    assert(plan.invalid_ids == 0);
}

void test_plan_rejects_a_non_divisible_layout() {
    const slim_arc::expert_tensor_view tensor{0x1000, 3 * 4096 + 1, 3};
    const auto plan = slim_arc::build_expert_reclaim_plan({tensor}, {1}, 4096);
    assert(plan.items.empty());
    assert(plan.invalid_layouts == 1);
    assert(plan.invalid_ids == 0);
}

void test_plan_keeps_tensor_view_order() {
    const slim_arc::expert_tensor_view first{0x1000, 2 * 4096, 2};
    const slim_arc::expert_tensor_view second{0x9000, 2 * 4096, 2};
    const auto plan = slim_arc::build_expert_reclaim_plan({first, second}, {1}, 4096);
    assert(plan.items.size() == 2);
    assert(plan.items[0].expert_id == 1);
    assert(plan.items[0].address == 0x2000);
    assert(plan.items[1].expert_id == 1);
    assert(plan.items[1].address == 0xa000);
}

void test_plan_rejects_a_tensor_view_that_overflows_its_address() {
    constexpr uintptr_t maximum = std::numeric_limits<uintptr_t>::max();
    const slim_arc::expert_tensor_view tensor{maximum - 4095, 2 * 4096, 2};
    const auto plan = slim_arc::build_expert_reclaim_plan({tensor}, {0}, 4096);
    assert(plan.items.empty());
    assert(plan.invalid_layouts == 1);
}

void test_plan_skips_a_sub_page_expert_slice() {
    const slim_arc::expert_tensor_view tensor{0x1003, 2 * 1024, 2};
    const auto plan = slim_arc::build_expert_reclaim_plan({tensor}, {1}, 4096);
    assert(plan.items.empty());
    assert(plan.invalid_layouts == 0);
    assert(plan.invalid_ids == 0);
    assert(plan.skipped_bytes == 1024);
}

} // namespace

int main() {
    test_wasted_ids_preserve_first_prefetch_order();
    test_plan_builds_a_page_aligned_expert_slice();
    test_plan_counts_negative_and_out_of_range_ids();
    test_plan_rejects_a_zero_expert_layout();
    test_plan_rejects_a_non_divisible_layout();
    test_plan_keeps_tensor_view_order();
    test_plan_rejects_a_tensor_view_that_overflows_its_address();
    test_plan_skips_a_sub_page_expert_slice();
    return 0;
}
