#pragma once

#include "slim-arc-prefetch.h"
#include "slim-arc-unified-scheduler.h"

#include <condition_variable>
#include <cstddef>
#include <mutex>

namespace slim_arc {

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

} // namespace slim_arc
