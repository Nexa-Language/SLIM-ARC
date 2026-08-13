#include "slim-arc-expert-residency.h"

#include <cassert>
#include <cstdint>
#include <limits>
#include <vector>

namespace {

using slim_arc::expert_candidate;
using slim_arc::expert_pressure_sample;
using slim_arc::expert_pressure_state;
using slim_arc::expert_residency_input;

expert_candidate candidate(
    int expert_id,
    uint64_t bytes,
    uint32_t popularity = 0,
    bool stable = false,
    bool temporal = false) {
    return {expert_id, bytes, popularity, stable, temporal};
}

void test_pressure_hysteresis_and_invalid_samples() {
    slim_arc::expert_pressure_controller controller;
    assert(controller.update({true, 70, 100}) == expert_pressure_state::normal);
    assert(controller.update({true, 86, 100}) == expert_pressure_state::high);
    assert(controller.update({true, 96, 100}) == expert_pressure_state::critical);
    assert(controller.update({true, 89, 100}) == expert_pressure_state::critical);
    assert(controller.update({true, 89, 100}) == expert_pressure_state::high);
    assert(controller.update({true, 74, 100}) == expert_pressure_state::high);
    assert(controller.update({true, 74, 100}) == expert_pressure_state::normal);

    assert(controller.update({false, 0, 0}) == expert_pressure_state::missing);
    assert(controller.update({true, 1, 0}) == expert_pressure_state::missing);
    assert(controller.update({true, 101, 100}) == expert_pressure_state::missing);
    assert(controller.update({true, 90, 100}) == expert_pressure_state::high);
    assert(controller.update({true, 90, 100}) == expert_pressure_state::high);
}

void test_pressure_ratio_is_overflow_safe_at_uint64_limits() {
    slim_arc::expert_pressure_controller controller;
    constexpr uint64_t maximum = std::numeric_limits<uint64_t>::max();
    assert(controller.update({true, maximum - 1, maximum}) == expert_pressure_state::critical);
}

void test_pressure_thresholds_are_inclusive() {
    slim_arc::expert_pressure_controller controller;
    assert(controller.update({true, 85, 100}) == expert_pressure_state::high);
    assert(controller.update({true, 95, 100}) == expert_pressure_state::critical);
    assert(controller.update({true, 90, 100}) == expert_pressure_state::critical);
    assert(controller.update({true, 90, 100}) == expert_pressure_state::high);
    assert(controller.update({true, 75, 100}) == expert_pressure_state::high);
    assert(controller.update({true, 75, 100}) == expert_pressure_state::normal);
}

void test_new_pressure_controller_uses_exact_entry_boundaries() {
    slim_arc::expert_pressure_controller normal_controller;
    assert(normal_controller.update({true, 8499, 10000}) == expert_pressure_state::normal);

    slim_arc::expert_pressure_controller high_controller;
    assert(high_controller.update({true, 8500, 10000}) == expert_pressure_state::high);
    assert(high_controller.update({true, 9499, 10000}) == expert_pressure_state::high);
    assert(high_controller.update({true, 9500, 10000}) == expert_pressure_state::critical);
}

void test_waste_ewma_clamps_and_uses_flooring() {
    assert(slim_arc::update_waste_ewma_milli(999, 1234, false) == 1000);
    assert(slim_arc::update_waste_ewma_milli(999, 1001, true) == 999);
    assert(slim_arc::update_waste_ewma_milli(1, 2, true) == 1);
}

void test_waste_hysteresis_boundaries() {
    slim_arc::expert_waste_controller controller;
    assert(!controller.update(599));
    assert(controller.update(600));
    assert(controller.update(400));
    assert(controller.update(399));
    assert(!controller.update(399));
    assert(controller.update(1000));
    assert(controller.update(1001));
}

void test_popularity_saturates_and_decays_once_per_sixty_four_samples() {
    assert(slim_arc::saturating_increment_popularity(std::numeric_limits<uint32_t>::max())
           == std::numeric_limits<uint32_t>::max());
    assert(slim_arc::saturating_increment_popularity(41) == 42);

    slim_arc::expert_popularity_decay_controller controller;
    std::vector<uint32_t> counts{9, std::numeric_limits<uint32_t>::max()};
    for (int sample = 0; sample < 63; ++sample) {
        assert(!controller.observe_valid_router_sample(counts));
    }
    assert((counts == std::vector<uint32_t>{9, std::numeric_limits<uint32_t>::max()}));
    assert(controller.observe_valid_router_sample(counts));
    assert((counts == std::vector<uint32_t>{4, std::numeric_limits<uint32_t>::max() / 2}));
    for (int sample = 0; sample < 64; ++sample) {
        const bool decayed = controller.observe_valid_router_sample(counts);
        assert(decayed == (sample == 63));
    }
    assert((counts == std::vector<uint32_t>{2, std::numeric_limits<uint32_t>::max() / 4}));
}

void test_critical_admits_no_experts_and_counts_pressure_skips() {
    const expert_residency_input input{
        expert_pressure_state::critical,
        100,
        3,
        0,
        {candidate(1, 10, 7, true), candidate(2, 20, 9, false, true), candidate(3, 30, 11)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert(decision.expert_ids.empty());
    assert(decision.admitted_bytes == 0);
    assert(decision.skipped_bytes == 60);
    assert(!decision.fallback);
    assert(decision.reasons.pressure_filtered_candidates == 3);
}

void test_high_admits_only_stable_candidates_in_input_order() {
    const expert_residency_input input{
        expert_pressure_state::high,
        100,
        4,
        0,
        {candidate(3, 10, 100), candidate(1, 20, 1, true), candidate(2, 30, 100, false, true), candidate(4, 40, 1, true)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert((decision.expert_ids == std::vector<int>{1, 4}));
    assert(decision.admitted_bytes == 60);
    assert(decision.skipped_bytes == 40);
    assert(decision.reasons.pressure_filtered_candidates == 2);
}

void test_normal_orders_categories_stably_without_popularity_tie_reordering() {
    const expert_residency_input input{
        expert_pressure_state::normal,
        100,
        5,
        0,
        {candidate(8, 10, 99), candidate(5, 10, 1, false, true), candidate(4, 10, 0, true), candidate(7, 10, 500), candidate(3, 10, 2, true, true)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert((decision.expert_ids == std::vector<int>{4, 3, 5, 8, 7}));
    assert(decision.admitted_bytes == 50);
    assert(decision.skipped_bytes == 0);
}

void test_missing_is_compatibility_fallback_in_valid_input_order() {
    const expert_residency_input input{
        expert_pressure_state::missing,
        100,
        3,
        0,
        {candidate(8, 10), candidate(4, 10, 0, true), candidate(5, 10, 0, false, true)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert((decision.expert_ids == std::vector<int>{8, 4, 5}));
    assert(decision.fallback);
    assert(decision.reasons.fallback_decisions == 1);
}

void test_normal_waste_boundary_restricts_only_at_six_hundred_permille() {
    const std::vector<expert_candidate> candidates{
        candidate(1, 10, 0, true),
        candidate(2, 10, 0, false, true),
        candidate(3, 10),
    };
    const auto below_boundary = slim_arc::select_resident_experts(
        {expert_pressure_state::normal, 100, 3, 599, candidates});
    assert((below_boundary.expert_ids == std::vector<int>{1, 2, 3}));
    assert(!below_boundary.waste_restricted);
    assert(below_boundary.reasons.waste_filtered_candidates == 0);

    const auto at_boundary = slim_arc::select_resident_experts(
        {expert_pressure_state::normal, 100, 3, 600, candidates});
    assert((at_boundary.expert_ids == std::vector<int>{1}));
    assert(at_boundary.waste_restricted);
    assert(at_boundary.reasons.waste_filtered_candidates == 2);
    assert(at_boundary.reasons.pressure_filtered_candidates == 0);
}

void test_missing_pressure_ignores_raw_waste_and_keeps_compatibility_order() {
    const auto decision = slim_arc::select_resident_experts(
        {expert_pressure_state::missing, 100, 3, 800,
         {candidate(3, 10), candidate(1, 10, 0, true), candidate(2, 10, 0, false, true)}});
    assert((decision.expert_ids == std::vector<int>{3, 1, 2}));
    assert(decision.fallback);
    assert(!decision.waste_restricted);
    assert(decision.reasons.waste_filtered_candidates == 0);
}

void test_stateful_waste_controller_recovers_after_two_low_samples() {
    slim_arc::expert_residency_controller controller;
    const expert_residency_input input{
        expert_pressure_state::normal,
        100,
        3,
        0,
        {candidate(1, 10, 0, true), candidate(2, 10, 0, false, true), candidate(3, 10)},
    };
    auto decision = input;
    decision.waste_ratio_milli = 800;
    assert((controller.select(decision).expert_ids == std::vector<int>{1}));
    assert((controller.select(decision).expert_ids == std::vector<int>{1}));
    decision.waste_ratio_milli = 300;
    assert((controller.select(decision).expert_ids == std::vector<int>{1}));
    assert((controller.select(decision).expert_ids == std::vector<int>{1, 2, 3}));
}

void test_zero_budget_or_count_admits_nothing_without_overflow() {
    const std::vector<expert_candidate> candidates{candidate(1, 10, 0, true), candidate(2, 20)};
    for (const expert_residency_input & input : {
             expert_residency_input{expert_pressure_state::normal, 0, 2, 0, candidates},
             expert_residency_input{expert_pressure_state::normal, 100, 0, 0, candidates},
         }) {
        const auto decision = slim_arc::select_resident_experts(input);
        assert(decision.expert_ids.empty());
        assert(decision.admitted_bytes == 0);
        assert(decision.skipped_bytes == 30);
    }
}

void test_duplicates_invalid_candidates_and_whole_expert_budget_rejections() {
    const expert_residency_input input{
        expert_pressure_state::normal,
        25,
        2,
        0,
        {candidate(4, 10, 0, true), candidate(4, 99), candidate(-1, 9), candidate(6, 0), candidate(5, 20, 0, false, true), candidate(3, 10)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert((decision.expert_ids == std::vector<int>{4, 3}));
    assert(decision.admitted_bytes == 20);
    assert(decision.skipped_bytes == 128);
    assert(decision.reasons.duplicate_candidates == 1);
    assert(decision.reasons.invalid_candidates == 2);
    assert(decision.reasons.budget_rejected_candidates == 1);
}

void test_zero_byte_first_occurrence_blocks_later_duplicate() {
    const expert_residency_input input{
        expert_pressure_state::normal,
        100,
        3,
        0,
        {candidate(8, 0), candidate(8, 10), candidate(8, 20)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert(decision.expert_ids.empty());
    assert(decision.requested_bytes == 30);
    assert(decision.skipped_bytes == 30);
    assert(decision.reasons.invalid_candidates == 1);
    assert(decision.reasons.duplicate_candidates == 2);
}

void test_exact_fit_budget_admits_the_whole_expert() {
    const expert_residency_input input{
        expert_pressure_state::normal,
        30,
        2,
        0,
        {candidate(1, 10, 0, true), candidate(2, 20, 0, false, true)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert((decision.expert_ids == std::vector<int>{1, 2}));
    assert(decision.admitted_bytes == 30);
    assert(decision.skipped_bytes == 0);
}

void test_budget_bound_does_not_overflow_after_uint64_max_admission() {
    constexpr uint64_t maximum = std::numeric_limits<uint64_t>::max();
    const expert_residency_input input{
        expert_pressure_state::normal,
        maximum,
        3,
        0,
        {candidate(1, maximum, 0, true), candidate(2, maximum, 0, true)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert((decision.expert_ids == std::vector<int>{1}));
    assert(decision.requested_bytes == maximum);
    assert(decision.admitted_bytes == maximum);
    assert(decision.skipped_bytes == maximum);
    assert(decision.reasons.budget_rejected_candidates == 1);
}

void test_count_rejection_is_distinct_from_budget_rejection() {
    const expert_residency_input input{
        expert_pressure_state::normal,
        100,
        1,
        0,
        {candidate(1, 10, 0, true), candidate(2, 20, 0, true)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert((decision.expert_ids == std::vector<int>{1}));
    assert(decision.skipped_bytes == 20);
    assert(decision.reasons.count_rejected_candidates == 1);
    assert(decision.reasons.budget_rejected_candidates == 0);
}

void test_requested_and_skipped_bytes_saturate_at_uint64_limits() {
    constexpr uint64_t maximum = std::numeric_limits<uint64_t>::max();
    const expert_residency_input input{
        expert_pressure_state::critical,
        maximum,
        3,
        0,
        {candidate(1, maximum), candidate(2, maximum), candidate(3, maximum)},
    };
    const auto decision = slim_arc::select_resident_experts(input);
    assert(decision.requested_bytes == maximum);
    assert(decision.admitted_bytes == 0);
    assert(decision.skipped_bytes == maximum);
    assert(decision.reasons.pressure_filtered_candidates == 3);
}

} // namespace

int main() {
    test_pressure_hysteresis_and_invalid_samples();
    test_pressure_ratio_is_overflow_safe_at_uint64_limits();
    test_pressure_thresholds_are_inclusive();
    test_new_pressure_controller_uses_exact_entry_boundaries();
    test_waste_ewma_clamps_and_uses_flooring();
    test_waste_hysteresis_boundaries();
    test_popularity_saturates_and_decays_once_per_sixty_four_samples();
    test_critical_admits_no_experts_and_counts_pressure_skips();
    test_high_admits_only_stable_candidates_in_input_order();
    test_normal_orders_categories_stably_without_popularity_tie_reordering();
    test_missing_is_compatibility_fallback_in_valid_input_order();
    test_normal_waste_boundary_restricts_only_at_six_hundred_permille();
    test_missing_pressure_ignores_raw_waste_and_keeps_compatibility_order();
    test_stateful_waste_controller_recovers_after_two_low_samples();
    test_zero_budget_or_count_admits_nothing_without_overflow();
    test_duplicates_invalid_candidates_and_whole_expert_budget_rejections();
    test_zero_byte_first_occurrence_blocks_later_duplicate();
    test_exact_fit_budget_admits_the_whole_expert();
    test_budget_bound_does_not_overflow_after_uint64_max_admission();
    test_count_rejection_is_distinct_from_budget_rejection();
    test_requested_and_skipped_bytes_saturate_at_uint64_limits();
    return 0;
}
