#include "slim-arc-pressure-budget.h"

#include <algorithm>
#include <cstdint>
#include <limits>

namespace slim_arc {
namespace {

constexpr uint64_t basis_points_denominator{10000};

uint64_t saturating_add(uint64_t left, uint64_t right) noexcept {
    const uint64_t maximum = std::numeric_limits<uint64_t>::max();
    return right > maximum - left ? maximum : left + right;
}

uint64_t saturating_multiply(uint64_t left, uint64_t right) noexcept {
    const uint64_t maximum = std::numeric_limits<uint64_t>::max();
    if (left == 0 || right == 0) {
        return 0;
    }
    return right > maximum / left ? maximum : left * right;
}

uint64_t percentage_reserve(uint64_t maximum, uint32_t basis_points) noexcept {
    const uint64_t whole = saturating_multiply(maximum / basis_points_denominator, basis_points);
    const uint64_t remainder = maximum % basis_points_denominator;
    const uint64_t fraction = saturating_multiply(remainder, basis_points) / basis_points_denominator;
    return saturating_add(whole, fraction);
}

pressure_budget_result static_fallback(uint64_t static_budget_bytes) noexcept {
    return {false, static_budget_bytes, 0, 0, static_budget_bytes, false};
}

} // namespace

pressure_budget_result compute_pressure_budget(
    uint64_t static_budget_bytes,
    const cgroup_memory_snapshot & snapshot,
    uint64_t minimum_reserve_bytes,
    uint32_t reserve_basis_points) {
    if (snapshot.status != cgroup_memory_status::ok || snapshot.current_bytes > snapshot.max_bytes) {
        return static_fallback(static_budget_bytes);
    }

    const uint64_t headroom = snapshot.max_bytes - snapshot.current_bytes;
    const uint64_t reserve = std::max(minimum_reserve_bytes, percentage_reserve(snapshot.max_bytes, reserve_basis_points));
    const uint64_t available = headroom > reserve ? headroom - reserve : 0;
    const uint64_t effective = std::min(static_budget_bytes, available);
    return {true, static_budget_bytes, reserve, headroom, effective, effective < static_budget_bytes};
}

} // namespace slim_arc
