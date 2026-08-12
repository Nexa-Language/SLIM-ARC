#pragma once

#include <cstdint>
#include <string>

namespace slim_arc {

enum class cgroup_memory_status {
    ok,
    unavailable,
    unlimited,
    invalid_value,
    io_error,
};

struct cgroup_memory_snapshot {
    cgroup_memory_status status{cgroup_memory_status::unavailable};
    uint64_t current_bytes{0};
    uint64_t max_bytes{0};
};

cgroup_memory_snapshot read_cgroup_memory(const std::string & root);

} // namespace slim_arc
