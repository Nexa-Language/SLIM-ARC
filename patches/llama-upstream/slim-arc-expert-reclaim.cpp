#include "slim-arc-expert-reclaim.h"

#include "slim-arc-page-range.h"

#include <limits>

namespace slim_arc {

namespace {

bool contains_id(const std::vector<int> & ids, int candidate) noexcept {
    for (const int id : ids) {
        if (id == candidate) {
            return true;
        }
    }
    return false;
}

bool checked_add(uintptr_t address, size_t length, uintptr_t * result) noexcept {
    const uintptr_t maximum = std::numeric_limits<uintptr_t>::max();
    if (length > maximum - address) {
        return false;
    }
    *result = address + static_cast<uintptr_t>(length);
    return true;
}

bool checked_multiply(size_t left, size_t right, size_t * result) noexcept {
    const size_t maximum = std::numeric_limits<size_t>::max();
    if (left != 0 && right > maximum / left) {
        return false;
    }
    *result = left * right;
    return true;
}

void saturating_add(uint64_t * total, uint64_t increment) noexcept {
    const uint64_t maximum = std::numeric_limits<uint64_t>::max();
    *total = increment > maximum - *total ? maximum : *total + increment;
}

} // namespace

std::vector<int> wasted_expert_ids(
    const std::vector<int> & prefetched,
    const std::vector<int> & selected) {
    std::vector<int> wasted;
    wasted.reserve(prefetched.size());
    for (const int expert_id : prefetched) {
        if (!contains_id(selected, expert_id) && !contains_id(wasted, expert_id)) {
            wasted.push_back(expert_id);
        }
    }
    return wasted;
}

expert_reclaim_plan build_expert_reclaim_plan(
    const std::vector<expert_tensor_view> & tensors,
    const std::vector<int> & wasted_ids,
    size_t page_size) {
    expert_reclaim_plan plan;

    for (const expert_tensor_view & tensor : tensors) {
        if (tensor.expert_count <= 0) {
            saturating_add(&plan.invalid_layouts, 1);
            continue;
        }

        const size_t expert_count = static_cast<size_t>(tensor.expert_count);
        if (tensor.total_bytes % expert_count != 0) {
            saturating_add(&plan.invalid_layouts, 1);
            continue;
        }

        uintptr_t tensor_end{0};
        if (!checked_add(tensor.address, tensor.total_bytes, &tensor_end)) {
            saturating_add(&plan.invalid_layouts, 1);
            continue;
        }
        (void) tensor_end;

        const size_t expert_bytes = tensor.total_bytes / expert_count;
        for (const int expert_id : wasted_ids) {
            if (expert_id < 0 || static_cast<size_t>(expert_id) >= expert_count) {
                saturating_add(&plan.invalid_ids, 1);
                continue;
            }

            size_t offset{0};
            if (!checked_multiply(static_cast<size_t>(expert_id), expert_bytes, &offset)) {
                saturating_add(&plan.invalid_layouts, 1);
                continue;
            }

            uintptr_t slice_address{0};
            uintptr_t slice_end{0};
            if (!checked_add(tensor.address, offset, &slice_address)
                || !checked_add(slice_address, expert_bytes, &slice_end)) {
                saturating_add(&plan.invalid_layouts, 1);
                continue;
            }
            (void) slice_end;

            const page_range range = interior_page_range(slice_address, expert_bytes, page_size);
            if (!range.valid) {
                saturating_add(&plan.invalid_layouts, 1);
                continue;
            }

            saturating_add(&plan.skipped_bytes, static_cast<uint64_t>(range.skipped_bytes));
            if (range.length == 0) {
                continue;
            }
            plan.items.push_back({expert_id, range.address, range.length, range.skipped_bytes});
        }
    }
    return plan;
}

} // namespace slim_arc
