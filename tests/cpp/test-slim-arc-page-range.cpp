#include "slim-arc-page-range.h"

#include <cassert>
#include <cstdint>
#include <limits>

namespace {

void assert_contained(uintptr_t address, size_t length, const slim_arc::page_range &range) {
    assert(range.valid);
    assert(range.address >= address);

    const size_t prefix_length = static_cast<size_t>(range.address - address);
    assert(prefix_length <= length);
    assert(range.length <= length - prefix_length);
}

} // namespace

int main() {
    const auto aligned = slim_arc::interior_page_range(0x2000, 0x2000, 0x1000);
    assert(aligned.valid);
    assert(aligned.address == 0x2000);
    assert(aligned.length == 0x2000);
    assert(aligned.skipped_bytes == 0);
    assert_contained(0x2000, 0x2000, aligned);

    const auto inward = slim_arc::interior_page_range(0x2003, 0x3000, 0x1000);
    assert(inward.valid);
    assert(inward.address == 0x3000);
    assert(inward.length == 0x2000);
    assert(inward.skipped_bytes == 0x1000);
    assert_contained(0x2003, 0x3000, inward);

    const auto subpage = slim_arc::interior_page_range(0x2003, 0x0ffc, 0x1000);
    assert(subpage.valid);
    assert(subpage.length == 0);
    assert(subpage.skipped_bytes == 0x0ffc);
    assert_contained(0x2003, 0x0ffc, subpage);

    const auto empty = slim_arc::interior_page_range(0x2003, 0, 0x1000);
    assert(empty.valid);
    assert(empty.length == 0);
    assert(empty.skipped_bytes == 0);
    assert_contained(0x2003, 0, empty);

    const auto zero_page_size = slim_arc::interior_page_range(0x2000, 0x1000, 0);
    assert(!zero_page_size.valid);

    const auto non_power_of_two_page_size = slim_arc::interior_page_range(0x2000, 0x1800, 0x1800);
    assert(!non_power_of_two_page_size.valid);

    const auto overflowing = slim_arc::interior_page_range(std::numeric_limits<uintptr_t>::max() - 3, 4, 0x1000);
    assert(!overflowing.valid);
}
