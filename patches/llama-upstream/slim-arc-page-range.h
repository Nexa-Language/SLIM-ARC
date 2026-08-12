#pragma once

#include <cstddef>
#include <cstdint>

namespace slim_arc {

struct page_range {
    uintptr_t address{0};
    size_t length{0};
    size_t skipped_bytes{0};
    bool valid{false};
};

page_range interior_page_range(
    uintptr_t address,
    size_t length,
    size_t page_size) noexcept;

} // namespace slim_arc
