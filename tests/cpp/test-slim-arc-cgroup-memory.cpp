#include "slim-arc-cgroup-memory.h"

#include <array>
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <unistd.h>
#include <vector>

namespace {

class temporary_directory {
  public:
    temporary_directory() {
        const std::string value = (std::filesystem::temp_directory_path() / "slim-arc-cgroup-test.XXXXXX").string();
        std::vector<char> pattern{value.begin(), value.end()};
        pattern.push_back('\0');
        const char * const created = mkdtemp(pattern.data());
        assert(created != nullptr);
        path_ = created;
    }

    ~temporary_directory() {
        const std::string name = path_.filename().string();
        assert(name.rfind("slim-arc-cgroup-test.", 0) == 0);
        std::error_code error;
        std::filesystem::remove_all(path_, error);
        assert(!error);
    }

    temporary_directory(const temporary_directory &) = delete;
    temporary_directory & operator=(const temporary_directory &) = delete;

    const std::filesystem::path & path() const { return path_; }

  private:
    std::filesystem::path path_{};
};

void write_file(const std::filesystem::path & path, const std::string & value) {
    std::ofstream stream{path};
    assert(stream.is_open());
    stream << value;
    assert(stream.good());
}

slim_arc::cgroup_memory_snapshot read_values(const std::string & current, const std::string & maximum) {
    temporary_directory root;
    write_file(root.path() / "memory.current", current);
    write_file(root.path() / "memory.max", maximum);
    return slim_arc::read_cgroup_memory(root.path().string());
}

void test_valid_snapshot() {
    const auto value = read_values("3221225472\n", "8589934592\n");
    assert(value.status == slim_arc::cgroup_memory_status::ok);
    assert(value.current_bytes == 3221225472ULL);
    assert(value.max_bytes == 8589934592ULL);
}

void test_unlimited_is_not_zero_budget() {
    const auto value = read_values("1\n", "max\n");
    assert(value.status == slim_arc::cgroup_memory_status::unlimited);
    assert(value.current_bytes == 1);
    assert(value.max_bytes == 0);
}

void test_missing_files_are_unavailable() {
    temporary_directory root;
    const auto value = slim_arc::read_cgroup_memory(root.path().string());
    assert(value.status == slim_arc::cgroup_memory_status::unavailable);
}

void test_invalid_values_are_rejected() {
    const std::array<std::string, 6> invalid_values{"", "-1", "1KiB", "18446744073709551616", "12 trailing", std::string(129, '1')};
    for (const std::string & value : invalid_values) {
        const auto current = read_values(value, "8589934592\n");
        assert(current.status == slim_arc::cgroup_memory_status::invalid_value);
        assert(current.current_bytes == 0);
        assert(current.max_bytes == 0);

        const auto maximum = read_values("1\n", value);
        assert(maximum.status == slim_arc::cgroup_memory_status::invalid_value);
        assert(maximum.current_bytes == 0);
        assert(maximum.max_bytes == 0);
    }
}

void test_current_above_max_is_invalid() {
    const auto value = read_values("9\n", "8\n");
    assert(value.status == slim_arc::cgroup_memory_status::invalid_value);
    assert(value.current_bytes == 0);
    assert(value.max_bytes == 0);
}

void test_ascii_whitespace_is_trimmed() {
    const auto value = read_values(" \t42\r\n", " 84 \n");
    assert(value.status == slim_arc::cgroup_memory_status::ok);
    assert(value.current_bytes == 42);
    assert(value.max_bytes == 84);
}

} // namespace

int main() {
    test_valid_snapshot();
    test_unlimited_is_not_zero_budget();
    test_missing_files_are_unavailable();
    test_invalid_values_are_rejected();
    test_current_above_max_is_invalid();
    test_ascii_whitespace_is_trimmed();
    return 0;
}
