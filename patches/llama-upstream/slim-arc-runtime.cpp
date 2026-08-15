#include "slim-arc-runtime.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <utility>

namespace slim_arc {

namespace {

std::mutex registry_mtx;
runtime_owner * registry_owner{nullptr};

} // namespace

runtime_lease::runtime_lease(runtime_lease && other) noexcept : owner_(other.owner_) {
    other.owner_ = nullptr;
}

runtime_lease & runtime_lease::operator=(runtime_lease && other) noexcept {
    if (this == &other) return *this;
    release();
    owner_ = other.owner_;
    other.owner_ = nullptr;
    return *this;
}

runtime_lease::~runtime_lease() {
    release();
}

void runtime_lease::release() noexcept {
    runtime_owner * const owner = owner_;
    owner_ = nullptr;
    if (owner != nullptr) owner->release_call();
}

prefetch_scheduler & runtime_lease::prefetch() const noexcept {
    return owner_->prefetch();
}

unified_io_scheduler & runtime_lease::unified() const noexcept {
    return owner_->unified();
}

runtime_owner::runtime_owner(size_t total_budget_bytes)
    : prefetch_scheduler_(2, 3)
    , unified_io_scheduler_(total_budget_bytes, &prefetch_scheduler_, nullptr) {}

runtime_owner::~runtime_owner() {
    deactivate();
}

void runtime_owner::activate() noexcept {
    std::lock_guard<std::mutex> registry_lock(registry_mtx);
    std::lock_guard<std::mutex> state_lock(state_mtx_);
    if (permanently_deactivated_ || (registry_owner != nullptr && registry_owner != this)) return;
    registry_owner = this;
    accepting_calls_ = true;
}

void runtime_owner::deactivate() noexcept {
    {
        std::lock_guard<std::mutex> registry_lock(registry_mtx);
        std::lock_guard<std::mutex> state_lock(state_mtx_);
        if (registry_owner == this) registry_owner = nullptr;
        accepting_calls_ = false;
        permanently_deactivated_ = true;
    }
    {
        std::unique_lock<std::mutex> state_lock(state_mtx_);
        state_cv_.wait(state_lock, [this] { return active_calls_ == 0; });
    }
    prefetch_scheduler_.shutdown();
}

bool runtime_owner::register_mapping(void * addr, size_t size, int file_id) {
    std::lock_guard<std::mutex> state_lock(state_mtx_);
    if (accepting_calls_ || permanently_deactivated_) return false;
    return prefetch_scheduler_.register_mapping(addr, size, file_id);
}

void runtime_owner::release_call() noexcept {
    std::lock_guard<std::mutex> state_lock(state_mtx_);
    if (active_calls_ == 0) return;
    --active_calls_;
    if (active_calls_ == 0) state_cv_.notify_all();
}

runtime_lease acquire_runtime() noexcept {
    std::lock_guard<std::mutex> registry_lock(registry_mtx);
    runtime_owner * const owner = registry_owner;
    if (owner == nullptr) return {};
    std::lock_guard<std::mutex> state_lock(owner->state_mtx_);
    if (!owner->accepting_calls_) return {};
    ++owner->active_calls_;
    return runtime_lease{owner};
}

// SLIM-ARC OPT 2026-08-13: SLIM_ARC_TOTAL_BUDGET_MB 覆盖统一调度器总预算。
// 严格解析：仅接受十进制数字；范围 [16, 1048576] MiB；任何非法输入回退
// 历史默认 1GiB，保证默认行为与既有部署完全一致。
size_t default_runtime_budget_bytes() noexcept {
    constexpr uint64_t fallback = 1ULL << 30;
    const char * const raw = std::getenv("SLIM_ARC_TOTAL_BUDGET_MB");
    if (raw == nullptr || *raw == '\0') return static_cast<size_t>(fallback);
    uint64_t value = 0;
    for (const char * cursor = raw; *cursor != '\0'; ++cursor) {
        if (*cursor < '0' || *cursor > '9') {
            std::fprintf(stderr, "SLIM-ARC: invalid SLIM_ARC_TOTAL_BUDGET_MB '%s'; expected decimal MiB, using default\n", raw);
            return static_cast<size_t>(fallback);
        }
        if (value > (UINT64_MAX - static_cast<uint64_t>(*cursor - '0')) / 10) {
            std::fprintf(stderr, "SLIM-ARC: SLIM_ARC_TOTAL_BUDGET_MB '%s' overflows; using default\n", raw);
            return static_cast<size_t>(fallback);
        }
        value = value * 10 + static_cast<uint64_t>(*cursor - '0');
    }
    if (value < 16 || value > 1048576) {
        std::fprintf(stderr, "SLIM-ARC: SLIM_ARC_TOTAL_BUDGET_MB=%llu out of range [16,1048576] MiB; using default\n",
                     static_cast<unsigned long long>(value));
        return static_cast<size_t>(fallback);
    }
    return static_cast<size_t>(value) << 20;
}

} // namespace slim_arc
