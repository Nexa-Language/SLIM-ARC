#include "slim-arc-pressure-budget.h"

#include <array>
#include <cassert>
#include <cstdint>
#include <limits>

namespace {

constexpr uint64_t mib{1ULL << 20};
constexpr uint64_t gib{1ULL << 30};

slim_arc::cgroup_memory_snapshot snapshot(uint64_t current, uint64_t maximum) {
    return {slim_arc::cgroup_memory_status::ok, current, maximum};
}

void test_table_driven_budgets() {
    struct test_case {
        uint64_t static_budget;
        uint64_t current;
        uint64_t maximum;
        uint64_t minimum_reserve;
        uint32_t reserve_basis_points;
        uint64_t expected_effective;
    };
    const std::array<test_case, 3> cases{{
        {gib, 3 * gib, 8 * gib, 512 * mib, 1000, gib},
        {gib, 7 * gib, 8 * gib, 512 * mib, 1000, 214748365ULL},
        {gib, 8 * gib, 8 * gib, 512 * mib, 1000, 0},
    }};
    for (const test_case & item : cases) {
        const auto result = slim_arc::compute_pressure_budget(
            item.static_budget, snapshot(item.current, item.maximum), item.minimum_reserve, item.reserve_basis_points);
        assert(result.pressure_data_valid);
        assert(result.static_budget_bytes == item.static_budget);
        assert(result.headroom_bytes == item.maximum - item.current);
        assert(result.effective_budget_bytes == item.expected_effective);
        assert(result.throttled == (item.expected_effective < item.static_budget));
    }
}

void test_invalid_and_unlimited_snapshots_fall_back() {
    const std::array<slim_arc::cgroup_memory_status, 4> statuses{
        slim_arc::cgroup_memory_status::unavailable,
        slim_arc::cgroup_memory_status::unlimited,
        slim_arc::cgroup_memory_status::invalid_value,
        slim_arc::cgroup_memory_status::io_error,
    };
    for (const auto status : statuses) {
        const slim_arc::cgroup_memory_snapshot value{status, 1, 2};
        const auto result = slim_arc::compute_pressure_budget(gib, value, 512 * mib, 1000);
        assert(!result.pressure_data_valid);
        assert(result.effective_budget_bytes == gib);
        assert(!result.throttled);
    }
}

void test_inconsistent_snapshot_falls_back() {
    const auto result = slim_arc::compute_pressure_budget(gib, snapshot(9, 8), 1, 1000);
    assert(!result.pressure_data_valid);
    assert(result.effective_budget_bytes == gib);
    assert(!result.throttled);
}

void test_zero_static_budget_stays_zero() {
    const auto result = slim_arc::compute_pressure_budget(0, snapshot(1, gib), 512 * mib, 1000);
    assert(result.pressure_data_valid);
    assert(result.effective_budget_bytes == 0);
    assert(!result.throttled);
}

void test_percentage_math_saturates_without_overflow() {
    constexpr uint64_t maximum = std::numeric_limits<uint64_t>::max();
    const auto result = slim_arc::compute_pressure_budget(maximum, snapshot(0, maximum), 0, 10000);
    assert(result.pressure_data_valid);
    assert(result.reserve_bytes == maximum);
    assert(result.headroom_bytes == maximum);
    assert(result.effective_budget_bytes == 0);
    assert(result.throttled);
}

void test_reserve_larger_than_maximum_yields_zero() {
    const auto result = slim_arc::compute_pressure_budget(gib, snapshot(0, gib), 2 * gib, 0);
    assert(result.pressure_data_valid);
    assert(result.reserve_bytes == 2 * gib);
    assert(result.effective_budget_bytes == 0);
    assert(result.throttled);
}

} // namespace

int main() {
    test_table_driven_budgets();
    test_invalid_and_unlimited_snapshots_fall_back();
    test_inconsistent_snapshot_falls_back();
    test_zero_static_budget_stays_zero();
    test_percentage_math_saturates_without_overflow();
    test_reserve_larger_than_maximum_yields_zero();
    return 0;
}
