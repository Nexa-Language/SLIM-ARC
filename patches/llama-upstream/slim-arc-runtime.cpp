#include "slim-arc-runtime.h"

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

bool runtime_owner::register_mapping(void * addr, size_t size) {
    std::lock_guard<std::mutex> state_lock(state_mtx_);
    if (accepting_calls_ || permanently_deactivated_) return false;
    return prefetch_scheduler_.register_mapping(addr, size);
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

} // namespace slim_arc
