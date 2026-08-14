#include "slim-arc-expert-transition.h"

#include <cassert>
#include <cstdint>
#include <vector>

namespace {

void test_cold_start_and_learning_filter_invalid_ids() {
    slim_arc::expert_transition_table table;
    assert(table.register_layer(3, 64));
    const int source[] = {7, 2, 7, -1, 99};
    assert(table.predict(3, source, 5, 2).empty());

    const int target[] = {11, 5, 11};
    table.observe(3, source, 5, target, 3);
    assert((table.predict(3, source, 5, 2) == std::vector<int>{5, 11}));

    const auto stats = table.statistics();
    assert(stats.updates == 1);
    assert(stats.prediction_rounds == 2);
    assert(stats.empty_rounds == 1);
    assert(stats.predicted_experts == 2);
}

void test_full_row_replaces_deterministic_low_score() {
    slim_arc::expert_transition_table table;
    assert(table.register_layer(0, 8));
    const int source[] = {0};
    const int first_four[] = {1, 2, 3, 4};
    table.observe(0, source, 1, first_four, 4);

    const int replacement[] = {5};
    table.observe(0, source, 1, replacement, 1);

    assert((table.predict(0, source, 1, 4) == std::vector<int>{5, 1, 2, 3}));
}

void test_result_metrics_count_unique_intersection() {
    slim_arc::expert_transition_table table;
    assert(table.register_layer(0, 8));
    const int source[] = {0};
    const int targets[] = {1, 2, 3, 4};
    table.observe(0, source, 1, targets, 4);
    const std::vector<int> predicted = table.predict(0, source, 1, 2);
    const int actual[] = {1, 7, 7, -1};
    table.record_result(predicted.data(), static_cast<int>(predicted.size()), actual, 4);

    const auto stats = table.statistics();
    assert(stats.prediction_rounds == 1);
    assert(stats.predicted_experts == 2);
    assert(stats.matched_experts == 1);
}

void test_decay_is_per_layer() {
    slim_arc::expert_transition_table table;
    assert(table.register_layer(0, 8));
    assert(table.register_layer(1, 8));
    const int source[] = {0};
    const int target[] = {5};
    for (int sample = 0; sample < 64; ++sample) {
        table.observe(0, source, 1, target, 1);
    }
    table.observe(1, source, 1, target, 1);

    assert(table.statistics().updates == 65);
    assert(table.statistics().decays == 1);
    assert((table.predict(1, source, 1, 64) == std::vector<int>{5}));
}

void test_registration_bounds_and_duplicate_registration() {
    slim_arc::expert_transition_table table;
    assert(!table.register_layer(-1, 8));
    assert(!table.register_layer(0, 0));
    assert(!table.register_layer(0, 65536));
    assert(table.register_layer(2, 8));

    const int source[] = {0};
    const int target[] = {3};
    table.observe(2, source, 1, target, 1);
    assert(table.register_layer(2, 8));
    assert(!table.register_layer(2, 7));
    assert((table.predict(2, source, 1, 64) == std::vector<int>{3}));
}

void test_target_model_state_stays_bounded() {
    slim_arc::expert_transition_table table;
    for (int layer = 0; layer < 48; ++layer) {
        assert(table.register_layer(layer, 512));
    }
    assert(table.allocated_bytes() <= (1U << 20));
}

} // namespace

int main() {
    test_cold_start_and_learning_filter_invalid_ids();
    test_full_row_replaces_deterministic_low_score();
    test_result_metrics_count_unique_intersection();
    test_decay_is_per_layer();
    test_registration_bounds_and_duplicate_registration();
    test_target_model_state_stays_bounded();
    return 0;
}
