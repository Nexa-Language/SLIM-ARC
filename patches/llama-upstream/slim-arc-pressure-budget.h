#pragma once

#include "slim-arc-cgroup-memory.h"

#include <cstdint>

namespace slim_arc {

struct pressure_budget_result {
    bool pressure_data_valid{false};
    uint64_t static_budget_bytes{0};
    uint64_t reserve_bytes{0};
    uint64_t headroom_bytes{0};
    uint64_t effective_budget_bytes{0};
    bool throttled{false};
};

pressure_budget_result compute_pressure_budget(
    uint64_t static_budget_bytes,
    const cgroup_memory_snapshot & snapshot,
    uint64_t minimum_reserve_bytes,
    uint32_t reserve_basis_points);

} // namespace slim_arc
