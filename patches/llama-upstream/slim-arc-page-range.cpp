#include "slim-arc-page-range.h"

#include <cstdint>

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

} // namespace slim_arc
