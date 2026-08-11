#include "slim-arc-cgroup-memory.h"

#include <array>
#include <charconv>
#include <fstream>
#include <string>
#include <string_view>
#include <system_error>

namespace slim_arc {
namespace {

constexpr size_t max_content_bytes{128};

struct file_read_result {
    cgroup_memory_status status{cgroup_memory_status::unavailable};
    std::string content{};
};

bool is_ascii_whitespace(char value) noexcept {
    return value == ' ' || value == '\t' || value == '\n' || value == '\r' || value == '\f' || value == '\v';
}

std::string_view trim_ascii_whitespace(std::string_view value) noexcept {
    while (!value.empty() && is_ascii_whitespace(value.front())) {
        value.remove_prefix(1);
    }
    while (!value.empty() && is_ascii_whitespace(value.back())) {
        value.remove_suffix(1);
    }
    return value;
}

file_read_result read_bounded_file(const std::string & path) {
    std::ifstream stream{path, std::ios::binary};
    if (!stream.is_open()) {
        return {cgroup_memory_status::unavailable, {}};
    }
    std::array<char, max_content_bytes + 1> buffer{};
    stream.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    if (stream.bad()) {
        return {cgroup_memory_status::io_error, {}};
    }
    const auto count = static_cast<size_t>(stream.gcount());
    if (count > max_content_bytes) {
        return {cgroup_memory_status::invalid_value, {}};
    }
    return {cgroup_memory_status::ok, std::string{buffer.data(), count}};
}

bool parse_uint64(std::string_view raw, uint64_t & output) noexcept {
    const std::string_view value = trim_ascii_whitespace(raw);
    if (value.empty()) {
        return false;
    }
    uint64_t parsed{0};
    const auto result = std::from_chars(value.data(), value.data() + value.size(), parsed);
    if (result.ec != std::errc{} || result.ptr != value.data() + value.size()) {
        return false;
    }
    output = parsed;
    return true;
}

cgroup_memory_snapshot error_snapshot(cgroup_memory_status status) noexcept {
    return {status, 0, 0};
}

} // namespace

cgroup_memory_snapshot read_cgroup_memory(const std::string & root) {
    const file_read_result current_file = read_bounded_file(root + "/memory.current");
    if (current_file.status != cgroup_memory_status::ok) {
        return error_snapshot(current_file.status);
    }
    const file_read_result max_file = read_bounded_file(root + "/memory.max");
    if (max_file.status != cgroup_memory_status::ok) {
        return error_snapshot(max_file.status);
    }

    uint64_t current{0};
    if (!parse_uint64(current_file.content, current)) {
        return error_snapshot(cgroup_memory_status::invalid_value);
    }
    if (trim_ascii_whitespace(max_file.content) == "max") {
        return {cgroup_memory_status::unlimited, current, 0};
    }

    uint64_t maximum{0};
    if (!parse_uint64(max_file.content, maximum) || current > maximum) {
        return error_snapshot(cgroup_memory_status::invalid_value);
    }
    return {cgroup_memory_status::ok, current, maximum};
}

} // namespace slim_arc
