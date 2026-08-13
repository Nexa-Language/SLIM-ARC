#include "slim-arc-page-range.h"

#include <algorithm>
#include <cstdint>
#include <limits>

namespace slim_arc {

page_range interior_page_range(uintptr_t address, size_t length, size_t page_size) noexcept {
    if (page_size == 0 || (page_size & (page_size - 1)) != 0) {
        return {};
    }
    if (length > UINTPTR_MAX - address) {
        return {};
    }

    const uintptr_t end = address + length;
    const uintptr_t page_mask = static_cast<uintptr_t>(page_size - 1);
    const uintptr_t misalignment = address & page_mask;
    uintptr_t first_page = address;

    if (misalignment != 0) {
        const uintptr_t advance = static_cast<uintptr_t>(page_size) - misalignment;
        if (advance > end - address) {
            return {end, 0, length, true};
        }
        first_page = address + advance;
    }

    const uintptr_t last_page_end = end & ~page_mask;
    if (first_page > last_page_end) {
        return {end, 0, length, true};
    }

    const size_t interior_length = static_cast<size_t>(last_page_end - first_page);
    const size_t skipped_bytes = length - interior_length;
    return {first_page, interior_length, skipped_bytes, true};
}

page_range covering_page_range(uintptr_t address, size_t length, size_t page_size) noexcept {
    if (page_size == 0 || (page_size & (page_size - 1)) != 0) {
        return {};
    }
    if (length == 0) {
        return {address, 0, 0, true, 0};
    }
    if (length > UINTPTR_MAX - address) {
        return {};
    }

    const uintptr_t page_mask = static_cast<uintptr_t>(page_size - 1);
    const uintptr_t first_page = address & ~page_mask;
    const uintptr_t end = address + length;
    uintptr_t last_page_end = end;
    const uintptr_t end_misalignment = end & page_mask;
    if (end_misalignment != 0) {
        const uintptr_t advance = static_cast<uintptr_t>(page_size) - end_misalignment;
        if (advance > UINTPTR_MAX - end) {
            return {};
        }
        last_page_end = end + advance;
    }
    if (last_page_end < first_page) {
        return {};
    }

    const uintptr_t covered = last_page_end - first_page;
    if (covered > std::numeric_limits<size_t>::max()) {
        return {};
    }
    const size_t covered_length = static_cast<size_t>(covered);
    if (covered_length < length) {
        return {};
    }
    return {first_page, covered_length, 0, true, covered_length - length};
}

page_range_set coalesce_page_ranges(std::vector<page_range> ranges) noexcept {
    const size_t input_ranges = ranges.size();
    std::vector<page_range> nonempty;
    nonempty.reserve(ranges.size());
    for (const page_range & range : ranges) {
        if (!range.valid || range.length > UINTPTR_MAX - range.address) {
            return {{}, input_ranges, false};
        }
        if (range.length == 0) {
            continue;
        }
        nonempty.push_back({range.address, range.length, 0, true, 0});
    }

    std::sort(nonempty.begin(), nonempty.end(), [](const page_range & left, const page_range & right) {
        if (left.address != right.address) return left.address < right.address;
        return left.length < right.length;
    });

    std::vector<page_range> merged;
    merged.reserve(nonempty.size());
    for (const page_range & range : nonempty) {
        if (merged.empty()) {
            merged.push_back(range);
            continue;
        }
        page_range & previous = merged.back();
        const uintptr_t previous_end = previous.address + previous.length;
        if (range.address > previous_end) {
            merged.push_back(range);
            continue;
        }
        const uintptr_t range_end = range.address + range.length;
        if (range_end > previous_end) {
            previous.length = static_cast<size_t>(range_end - previous.address);
        }
    }
    return {std::move(merged), input_ranges, true};
}

} // namespace slim_arc
