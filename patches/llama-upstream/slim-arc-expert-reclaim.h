#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace slim_arc {

struct expert_tensor_view {
    uintptr_t address{0};
    size_t total_bytes{0};
    int expert_count{0};
};

struct expert_reclaim_item {
    int expert_id{-1};
    uintptr_t address{0};
    size_t length{0};
    size_t skipped_bytes{0};
};

struct expert_reclaim_plan {
    std::vector<expert_reclaim_item> items;
    uint64_t invalid_layouts{0};
    uint64_t invalid_ids{0};
    uint64_t skipped_bytes{0};
};

std::vector<int> wasted_expert_ids(
    const std::vector<int> & prefetched,
    const std::vector<int> & selected);

expert_reclaim_plan build_expert_reclaim_plan(
    const std::vector<expert_tensor_view> & tensors,
    const std::vector<int> & wasted_ids,
    size_t page_size);

} // namespace slim_arc
