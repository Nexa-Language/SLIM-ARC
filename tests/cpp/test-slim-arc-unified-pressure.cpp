#include "slim-arc-unified-scheduler.h"

#include <cassert>
#include <cstdlib>
#include <future>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

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
    unsetenv("SLIM_ARC_EXPERT_RESIDENCY");
}

void test_each_model_owned_runtime_emits_its_exact_machine_line_once() {
    clear_pressure_environment();
    int descriptors[2];
    assert(pipe(descriptors) == 0);
    const pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        assert(close(descriptors[0]) == 0);
        assert(dup2(descriptors[1], STDERR_FILENO) >= 0);
        assert(close(descriptors[1]) == 0);
        {
            slim_arc::prefetch_scheduler first_prefetcher{1, 1};
            const int selected = 0;
            first_prefetcher.cache_router_experts(0, &selected, 1);
            slim_arc::unified_io_scheduler first{static_budget, &first_prefetcher, nullptr};
        }
        {
            slim_arc::prefetch_scheduler second_prefetcher{1, 1};
            const int selected = 0;
            second_prefetcher.cache_router_experts(0, &selected, 1);
            second_prefetcher.cache_router_experts(0, &selected, 1);
            slim_arc::unified_io_scheduler second{static_budget, &second_prefetcher, nullptr};
        }
        _exit(0);
    }
    assert(close(descriptors[1]) == 0);
    std::string output;
    char buffer[1024];
    ssize_t count;
    while ((count = read(descriptors[0], buffer, sizeof(buffer))) > 0) {
        output.append(buffer, static_cast<size_t>(count));
    }
    assert(count == 0);
    assert(close(descriptors[0]) == 0);
    int status = 0;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    const std::string common_suffix =
        " expert_issued_bytes=0 expert_hit_bytes=0 expert_waste_bytes=0 reclaim_candidates=0 reclaim_calls=0 reclaimed_bytes=0 reclaim_skipped_bytes=0 reclaim_failures=0 residency_samples=0 residency_admitted_experts=0 residency_admitted_bytes=0 residency_skipped_bytes=0 residency_fallbacks=0 pressure_normal=0 pressure_high=0 pressure_critical=0\n";
    const std::string first_expected =
        "[SLIM-ARC-RUNTIME] schema=1 expert_samples=1" + common_suffix;
    const std::string second_expected =
        "[SLIM-ARC-RUNTIME] schema=1 expert_samples=2" + common_suffix;
    const size_t first = output.find(first_expected);
    const size_t second = output.find(second_expected);
    assert(first != std::string::npos);
    assert(second != std::string::npos);
    assert(first < second);
    assert(output.find(first_expected, first + first_expected.size()) == std::string::npos);
    assert(output.find(second_expected, second + second_expected.size()) == std::string::npos);
    assert(output.find("[SLIM-ARC-RUNTIME]", second + second_expected.size()) == std::string::npos);
}

void test_residency_strict_values_do_not_sample_pressure() {
    for (const char * value : {"0", "", "false", "invalid"}) {
        clear_pressure_environment();
        assert(setenv("SLIM_ARC_EXPERT_RESIDENCY", value, 1) == 0);
        size_t provider_calls{0};
        slim_arc::unified_io_scheduler scheduler{static_budget, nullptr, nullptr, [&] {
            ++provider_calls;
            return slim_arc::cgroup_memory_snapshot{slim_arc::cgroup_memory_status::ok, 96, 100};
        }};
        scheduler.tick(0, 1);
        assert(provider_calls == 0);
    }
    clear_pressure_environment();
}

void test_residency_and_legacy_pressure_share_one_snapshot_per_tick() {
    clear_pressure_environment();
    assert(setenv("SLIM_ARC_EXPERT_RESIDENCY", "1", 1) == 0);
    assert(setenv("SLIM_ARC_PRESSURE_ADMISSION", "1", 1) == 0);
    size_t provider_calls{0};
    slim_arc::prefetch_scheduler prefetcher{1, 1};
    slim_arc::unified_io_scheduler scheduler{static_budget, &prefetcher, nullptr, [&] {
        ++provider_calls;
        return slim_arc::cgroup_memory_snapshot{slim_arc::cgroup_memory_status::ok, 70, 100};
    }};
    scheduler.set_phase(slim_arc::runtime_phase::MOE_DECODE);
    scheduler.tick(0, 1);
    assert(provider_calls == 1);
    assert(scheduler.pressure_stats().samples == 1);
    assert(prefetcher.expert_residency_statistics().pressure_normal == 0);
    assert(prefetcher.current_expert_pressure() == slim_arc::expert_pressure_state::normal);
    clear_pressure_environment();
}

void test_injected_pressure_sequence_uses_controller_hysteresis() {
    clear_pressure_environment();
    assert(setenv("SLIM_ARC_EXPERT_RESIDENCY", "1", 1) == 0);
    const std::vector<uint64_t> current{96, 89, 89, 74, 74};
    const std::vector<slim_arc::expert_pressure_state> expected{
        slim_arc::expert_pressure_state::critical,
        slim_arc::expert_pressure_state::critical,
        slim_arc::expert_pressure_state::high,
        slim_arc::expert_pressure_state::high,
        slim_arc::expert_pressure_state::normal,
    };
    size_t index{0};
    slim_arc::prefetch_scheduler prefetcher{1, 1};
    slim_arc::unified_io_scheduler scheduler{static_budget, &prefetcher, nullptr, [&] {
        return slim_arc::cgroup_memory_snapshot{slim_arc::cgroup_memory_status::ok, current[index++], 100};
    }};
    for (const auto state : expected) {
        scheduler.tick(0, 1);
        assert(prefetcher.current_expert_pressure() == state);
    }
    assert(index == current.size());
    clear_pressure_environment();
}

void test_invalid_snapshot_maps_to_missing_and_provider_callback_does_not_deadlock() {
    clear_pressure_environment();
    assert(setenv("SLIM_ARC_EXPERT_RESIDENCY", "1", 1) == 0);
    slim_arc::prefetch_scheduler prefetcher{1, 1};
    slim_arc::unified_io_scheduler * scheduler_ptr{nullptr};
    slim_arc::unified_io_scheduler scheduler{static_budget, &prefetcher, nullptr, [&] {
        assert(scheduler_ptr != nullptr);
        (void) scheduler_ptr->adaptation_history();
        (void) scheduler_ptr->pressure_stats();
        return slim_arc::cgroup_memory_snapshot{slim_arc::cgroup_memory_status::invalid_value, 99, 100};
    }};
    scheduler_ptr = &scheduler;
    auto tick = std::async(std::launch::async, [&] { scheduler.tick(0, 1); });
    assert(tick.wait_for(std::chrono::seconds{2}) == std::future_status::ready);
    tick.get();
    assert(prefetcher.current_expert_pressure() == slim_arc::expert_pressure_state::missing);
    clear_pressure_environment();
}

struct integrated_result {
    std::vector<int> advised;
    slim_arc::expert_residency_runtime_stats stats;
};

integrated_result run_integrated_selection(const slim_arc::cgroup_memory_snapshot & snapshot) {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 4 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    integrated_result result;
    {
        slim_arc::prefetch_scheduler prefetcher{1, 1, {}, [&](void * addr, size_t, int advice) {
            if (advice == POSIX_MADV_WILLNEED) result.advised.push_back(static_cast<int>(
                (static_cast<uint8_t *>(addr) - static_cast<uint8_t *>(mapping)) / page_size));
            return 0;
        }};
        prefetcher.register_expert_tensor("blk.7.exps", mapping, 4 * page_size, 7, 4);
        const int previous[] = {1, 3};
        const int requested[] = {1, 2};
        prefetcher.cache_router_experts(7, previous, 2);
        prefetcher.cache_router_experts(7, requested, 2);
        slim_arc::unified_io_scheduler scheduler{4 * page_size, &prefetcher, nullptr, [snapshot] { return snapshot; }};
        scheduler.set_phase(slim_arc::runtime_phase::MOE_DECODE);
        scheduler.tick(0, 1);
        const uint64_t generation = prefetcher.prefetch_experts(7, requested, 2);
        if (generation != 0) prefetcher.cancel_expert_prefetch(7, generation);
        result.stats = prefetcher.expert_residency_statistics();
    }
    assert(munmap(mapping, 4 * page_size) == 0);
    return result;
}

void test_injected_critical_high_normal_and_invalid_snapshots_drive_selection() {
    clear_pressure_environment();
    assert(setenv("SLIM_ARC_EXPERT_RESIDENCY", "1", 1) == 0);
    const integrated_result critical = run_integrated_selection(
        {slim_arc::cgroup_memory_status::ok, 96, 100});
    assert(critical.advised.empty());
    assert(critical.stats.pressure_critical == 1);

    const integrated_result high = run_integrated_selection(
        {slim_arc::cgroup_memory_status::ok, 86, 100});
    assert((high.advised == std::vector<int>{1}));
    assert(high.stats.pressure_high == 1);

    const integrated_result normal = run_integrated_selection(
        {slim_arc::cgroup_memory_status::ok, 70, 100});
    assert((normal.advised == std::vector<int>{1, 2}));
    assert(normal.stats.pressure_normal == 1);

    const integrated_result invalid = run_integrated_selection(
        {slim_arc::cgroup_memory_status::invalid_value, 99, 100});
    assert((invalid.advised == std::vector<int>{1, 2}));
    assert(invalid.stats.pressure_missing == 1);
    assert(invalid.stats.fallbacks == 1);
    clear_pressure_environment();
}

void test_normal_budget_can_admit_hot_candidate_beyond_requested_count() {
    clear_pressure_environment();
    assert(setenv("SLIM_ARC_EXPERT_RESIDENCY", "1", 1) == 0);
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, 3 * page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    std::vector<int> advised;
    {
        slim_arc::prefetch_scheduler prefetcher{1, 1, {}, [&](void * addr, size_t, int advice) {
            if (advice == POSIX_MADV_WILLNEED) advised.push_back(static_cast<int>(
                (static_cast<uint8_t *>(addr) - static_cast<uint8_t *>(mapping)) / page_size));
            return 0;
        }};
        prefetcher.register_expert_tensor("blk.8.exps", mapping, 3 * page_size, 8, 3);
        const int hot = 2;
        prefetcher.cache_router_experts(8, &hot, 1);
        const int requested = 1;
        slim_arc::unified_io_scheduler scheduler{4 * page_size, &prefetcher, nullptr, [] {
            return slim_arc::cgroup_memory_snapshot{slim_arc::cgroup_memory_status::ok, 70, 100};
        }};
        scheduler.set_phase(slim_arc::runtime_phase::MOE_DECODE);
        scheduler.tick(0, 1);
        const uint64_t generation = prefetcher.prefetch_experts(8, &requested, 1);
        assert(generation != 0);
        assert((advised == std::vector<int>{1, 2}));
    }
    assert(munmap(mapping, 3 * page_size) == 0);
    clear_pressure_environment();
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
    test_each_model_owned_runtime_emits_its_exact_machine_line_once();
    test_pressure_admission_is_opt_in();
    test_invalid_configuration_disables_pressure_admission();
    test_valid_configuration_samples_pressure_once_per_tick();
    test_residency_strict_values_do_not_sample_pressure();
    test_residency_and_legacy_pressure_share_one_snapshot_per_tick();
    test_injected_pressure_sequence_uses_controller_hysteresis();
    test_invalid_snapshot_maps_to_missing_and_provider_callback_does_not_deadlock();
    test_injected_critical_high_normal_and_invalid_snapshots_drive_selection();
    test_normal_budget_can_admit_hot_candidate_beyond_requested_count();
    return 0;
}
