#include "slim-arc-unified-scheduler.h"

#include <cassert>
#include <cstdlib>

namespace slim_arc {

int kv_eviction_manager::run_eviction() {
    return 0;
}

int kv_eviction_manager::prefetch_cold_blocks(int32_t, int32_t) {
    return 0;
}

} // namespace slim_arc

namespace {

constexpr size_t static_budget{1ULL << 30};

void clear_pressure_environment() {
    unsetenv("SLIM_ARC_PRESSURE_ADMISSION");
    unsetenv("SLIM_ARC_PRESSURE_RESERVE_MB");
}

void test_pressure_admission_is_opt_in() {
    clear_pressure_environment();
    slim_arc::unified_io_scheduler scheduler{static_budget, nullptr, nullptr};
    scheduler.tick(0, 1);
    const auto stats = scheduler.pressure_stats();
    assert(stats.samples == 0);
    assert(stats.static_bytes == static_budget);
    assert(stats.effective_bytes == static_budget);
}

void test_invalid_configuration_disables_pressure_admission() {
    clear_pressure_environment();
    assert(setenv("SLIM_ARC_PRESSURE_ADMISSION", "1", 1) == 0);
    assert(setenv("SLIM_ARC_PRESSURE_RESERVE_MB", "512MB", 1) == 0);
    slim_arc::unified_io_scheduler scheduler{static_budget, nullptr, nullptr};
    scheduler.tick(0, 1);
    assert(scheduler.pressure_stats().samples == 0);
    clear_pressure_environment();
}

void test_valid_configuration_samples_pressure_once_per_tick() {
    clear_pressure_environment();
    assert(setenv("SLIM_ARC_PRESSURE_ADMISSION", "1", 1) == 0);
    assert(setenv("SLIM_ARC_PRESSURE_RESERVE_MB", "512", 1) == 0);
    slim_arc::unified_io_scheduler scheduler{static_budget, nullptr, nullptr};
    scheduler.tick(0, 1);
    const auto stats = scheduler.pressure_stats();
    assert(stats.samples == 1);
    assert(stats.static_bytes == static_budget);
    assert(stats.effective_bytes <= static_budget);
    clear_pressure_environment();
}

} // namespace

int main() {
    test_pressure_admission_is_opt_in();
    test_invalid_configuration_disables_pressure_admission();
    test_valid_configuration_samples_pressure_once_per_tick();
    return 0;
}
