#include "slim-arc-page-range.h"

#include <cassert>
#include <cstdint>
#include <limits>
#include <sys/mman.h>
#include <unistd.h>

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

    const auto covering_aligned = slim_arc::covering_page_range(0x2000, 0x2000, 0x1000);
    assert(covering_aligned.valid);
    assert(covering_aligned.address == 0x2000);
    assert(covering_aligned.length == 0x2000);
    assert(covering_aligned.extra_bytes == 0);

    const auto covering_unaligned = slim_arc::covering_page_range(0x2003, 0x1000, 0x1000);
    assert(covering_unaligned.valid);
    assert(covering_unaligned.address == 0x2000);
    assert(covering_unaligned.length == 0x2000);
    assert(covering_unaligned.extra_bytes == 0x1000);

    const auto covering_subpage = slim_arc::covering_page_range(0x2003, 0x0ffc, 0x1000);
    assert(covering_subpage.valid);
    assert(covering_subpage.address == 0x2000);
    assert(covering_subpage.length == 0x1000);
    assert(covering_subpage.extra_bytes == 4);

    const auto covering_to_page_end = slim_arc::covering_page_range(0x2003, 0x0ffd, 0x1000);
    assert(covering_to_page_end.valid);
    assert(covering_to_page_end.address == 0x2000);
    assert(covering_to_page_end.length == 0x1000);
    assert(covering_to_page_end.extra_bytes == 3);

    const auto covering_empty = slim_arc::covering_page_range(0x2003, 0, 0x1000);
    assert(covering_empty.valid);
    assert(covering_empty.address == 0x2003);
    assert(covering_empty.length == 0);
    assert(covering_empty.extra_bytes == 0);

    assert(!slim_arc::covering_page_range(0x2000, 0x1000, 0).valid);
    assert(!slim_arc::covering_page_range(0x2000, 0x1000, 0x1800).valid);
    assert(!slim_arc::covering_page_range(
        std::numeric_limits<uintptr_t>::max() - 3, 4, 0x1000).valid);
    assert(!slim_arc::covering_page_range(
        std::numeric_limits<uintptr_t>::max() - 0x0fff, 0x0fff, 0x1000).valid);

    const long system_page_size = sysconf(_SC_PAGESIZE);
    assert(system_page_size > 0);
    const size_t mapping_size = static_cast<size_t>(system_page_size) * 2;
    void * const mapping = mmap(
        nullptr,
        mapping_size,
        PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANONYMOUS,
        -1,
        0);
    assert(mapping != MAP_FAILED);
    const uintptr_t base = reinterpret_cast<uintptr_t>(mapping);
    const int unaligned_result = posix_madvise(
        reinterpret_cast<void *>(base + 32),
        static_cast<size_t>(system_page_size),
        POSIX_MADV_WILLNEED);
#if defined(__linux__)
    assert(unaligned_result != 0);
#else
    (void) unaligned_result;
#endif
    const auto real_covering = slim_arc::covering_page_range(
        base + 32,
        static_cast<size_t>(system_page_size),
        static_cast<size_t>(system_page_size));
    assert(real_covering.valid);
    assert(real_covering.address == base);
    assert(real_covering.length == mapping_size);
    assert(real_covering.address % static_cast<uintptr_t>(system_page_size) == 0);
    assert(real_covering.length % static_cast<size_t>(system_page_size) == 0);
    assert(posix_madvise(
        reinterpret_cast<void *>(real_covering.address),
        real_covering.length,
        POSIX_MADV_WILLNEED) == 0);
    assert(munmap(mapping, mapping_size) == 0);

    const auto empty_ranges = slim_arc::coalesce_page_ranges({});
    assert(empty_ranges.valid);
    assert(empty_ranges.input_ranges == 0);
    assert(empty_ranges.ranges.empty());

    const auto identical_ranges = slim_arc::coalesce_page_ranges({
        {0x2000, 0x1000, 0, true, 0},
        {0x2000, 0x1000, 0, true, 0},
    });
    assert(identical_ranges.valid);
    assert(identical_ranges.input_ranges == 2);
    assert(identical_ranges.ranges.size() == 1);
    assert(identical_ranges.ranges[0].address == 0x2000);
    assert(identical_ranges.ranges[0].length == 0x1000);

    const auto unsorted_adjacent_ranges = slim_arc::coalesce_page_ranges({
        {0x4000, 0x1000, 0, true, 0},
        {0x2000, 0x1000, 0, true, 0},
        {0x3000, 0x1000, 0, true, 0},
    });
    assert(unsorted_adjacent_ranges.valid);
    assert(unsorted_adjacent_ranges.input_ranges == 3);
    assert(unsorted_adjacent_ranges.ranges.size() == 1);
    assert(unsorted_adjacent_ranges.ranges[0].address == 0x2000);
    assert(unsorted_adjacent_ranges.ranges[0].length == 0x3000);

    const auto overlap_and_disjoint_ranges = slim_arc::coalesce_page_ranges({
        {0x2800, 0x1000, 0, true, 0},
        {0x5000, 0x1000, 0, true, 0},
        {0x2000, 0x1000, 0, true, 0},
    });
    assert(overlap_and_disjoint_ranges.valid);
    assert(overlap_and_disjoint_ranges.ranges.size() == 2);
    assert(overlap_and_disjoint_ranges.ranges[0].address == 0x2000);
    assert(overlap_and_disjoint_ranges.ranges[0].length == 0x1800);
    assert(overlap_and_disjoint_ranges.ranges[1].address == 0x5000);
    assert(overlap_and_disjoint_ranges.ranges[1].length == 0x1000);

    const auto ignores_empty_range = slim_arc::coalesce_page_ranges({
        {0x2003, 0, 0, true, 0},
        {0x3000, 0x1000, 0, true, 0},
    });
    assert(ignores_empty_range.valid);
    assert(ignores_empty_range.input_ranges == 2);
    assert(ignores_empty_range.ranges.size() == 1);
    assert(ignores_empty_range.ranges[0].address == 0x3000);

    assert(!slim_arc::coalesce_page_ranges({{0x2000, 0x1000, 0, false, 0}}).valid);
    assert(!slim_arc::coalesce_page_ranges({{
        std::numeric_limits<uintptr_t>::max() - 3, 4, 0, true, 0}}).valid);
}
