#pragma once

#include "slim-arc-prefetch.h"
#include "slim-arc-unified-scheduler.h"

#include <condition_variable>
#include <cstddef>
#include <mutex>

namespace slim_arc {

constexpr bool model_runtime_admitted(
    bool use_mmap_buffer, size_t mapping_count, uint64_t size_data, bool enabled) noexcept {
    return use_mmap_buffer && mapping_count > 0 && size_data > (6ULL << 30) && enabled;
}

class runtime_owner;

class runtime_lease {
  public:
    runtime_lease() noexcept = default;
    runtime_lease(runtime_lease && other) noexcept;
    runtime_lease & operator=(runtime_lease && other) noexcept;
    ~runtime_lease();

    runtime_lease(const runtime_lease &) = delete;
    runtime_lease & operator=(const runtime_lease &) = delete;

    explicit operator bool() const noexcept { return owner_ != nullptr; }
    prefetch_scheduler & prefetch() const noexcept;
    unified_io_scheduler & unified() const noexcept;

  private:
    friend runtime_lease acquire_runtime() noexcept;
    explicit runtime_lease(runtime_owner * owner) noexcept : owner_(owner) {}
    void release() noexcept;

    runtime_owner * owner_{nullptr};
};

class runtime_owner {
  public:
    explicit runtime_owner(size_t total_budget_bytes);
    ~runtime_owner();

    runtime_owner(const runtime_owner &) = delete;
    runtime_owner & operator=(const runtime_owner &) = delete;

    void activate() noexcept;
    void deactivate() noexcept;
    bool register_mapping(void * addr, size_t size);
    prefetch_scheduler & prefetch() noexcept { return prefetch_scheduler_; }
    unified_io_scheduler & unified() noexcept { return unified_io_scheduler_; }

  private:
    friend class runtime_lease;
    friend runtime_lease acquire_runtime() noexcept;
    void release_call() noexcept;

    // Declaration order is intentional: unified scheduler is destroyed first.
    prefetch_scheduler prefetch_scheduler_;
    unified_io_scheduler unified_io_scheduler_;
    std::mutex state_mtx_;
    std::condition_variable state_cv_;
    size_t active_calls_{0};
    bool accepting_calls_{false};
    bool permanently_deactivated_{false};
};

runtime_lease acquire_runtime() noexcept;

// SLIM-ARC OPT 2026-08-13: 运行时总 I/O 预算（统一调度器每 tick 额度）。
// 默认 1GiB（历史硬编码值）；SLIM_ARC_TOTAL_BUDGET_MB=N（16..1048576 MiB，
// 仅十进制数字）时覆盖。非法/越界/空值一律回退默认，保证三线默认行为不变。
// 背景：4GB 端侧（Pi5）上每 step 614MB 专家预算挤占页缓存，
// 允许按机器内存缩放（如 SLIM_ARC_TOTAL_BUDGET_MB=256）。
size_t default_runtime_budget_bytes() noexcept;

} // namespace slim_arc
