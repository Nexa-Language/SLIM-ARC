#include "slim-arc-runtime.h"

#include <cassert>
#include <chrono>
#include <future>
#include <sys/mman.h>
#include <thread>
#include <unistd.h>

// The runtime owns a null KV manager in these tests. These link shims keep the
// platform-specific Linux mremap implementation out of the macOS unit binary.
int slim_arc::kv_eviction_manager::run_eviction() { return 0; }
int slim_arc::kv_eviction_manager::prefetch_cold_blocks(int32_t, int32_t) { return 0; }

namespace {

void test_deactivate_waits_for_live_lease_and_rejects_new_acquires() {
    slim_arc::runtime_owner owner{1ULL << 20};
    assert(!slim_arc::acquire_runtime());
    owner.activate();
    auto lease = slim_arc::acquire_runtime();
    assert(lease);

    std::promise<void> entered;
    std::promise<void> finished;
    auto finished_future = finished.get_future();
    std::thread deactivator([&] {
        entered.set_value();
        owner.deactivate();
        finished.set_value();
    });
    entered.get_future().wait();
    bool unregistered = false;
    for (int attempt = 0; attempt < 200; ++attempt) {
        auto transient = slim_arc::acquire_runtime();
        if (!transient) {
            unregistered = true;
            break;
        }
        transient = {};
        std::this_thread::yield();
    }
    assert(unregistered);
    assert(finished_future.wait_for(std::chrono::milliseconds{50}) == std::future_status::timeout);
    assert(!slim_arc::acquire_runtime());

    lease = {};
    assert(finished_future.wait_for(std::chrono::seconds{2}) == std::future_status::ready);
    deactivator.join();
    assert(!slim_arc::acquire_runtime());
    owner.deactivate();
}

void test_lease_moves_release_each_owner_once() {
    slim_arc::runtime_owner owner{1ULL << 20};
    owner.activate();
    auto first = slim_arc::acquire_runtime();
    auto second = slim_arc::acquire_runtime();
    assert(first && second);
    slim_arc::runtime_lease moved{std::move(first)};
    assert(!first && moved);
    moved = std::move(second);
    assert(!second && moved);
    moved = {};
    owner.deactivate();
    assert(!slim_arc::acquire_runtime());
}

void test_conflicting_owner_cannot_take_over_active_registry() {
    slim_arc::runtime_owner first{1ULL << 20};
    slim_arc::runtime_owner second{1ULL << 20};
    first.activate();
    second.activate();
    auto lease = slim_arc::acquire_runtime();
    assert(lease);
    assert(&lease.prefetch() == &first.prefetch());
    lease = {};
    second.deactivate();
    assert(slim_arc::acquire_runtime());
    first.deactivate();
}

void test_mapping_and_tensor_registration_are_owner_lifetime_bound() {
    const size_t page_size = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    void * const mapping = mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    {
        slim_arc::runtime_owner owner{page_size};
        assert(owner.register_mapping(mapping, page_size));
        owner.prefetch().register_tensor("blk.1.weight", mapping, page_size, 1);
        owner.activate();
        {
            auto lease = slim_arc::acquire_runtime();
            assert(lease);
            lease.prefetch().set_memory_budget(page_size);
            lease.prefetch().notify_layer_compute(0);
        }
        owner.deactivate();
        const int calls = owner.prefetch().total_prefetch_calls();
        const size_t expert_bytes = owner.prefetch().expert_prefetch_bytes();
        assert(!slim_arc::acquire_runtime());
        const int expert{0};
        owner.prefetch().set_phase(slim_arc::compute_phase::DECODE);
        assert(owner.prefetch().prefetch_experts(1, &expert, 1) == 0);
        std::this_thread::sleep_for(std::chrono::milliseconds{20});
        assert(owner.prefetch().total_prefetch_calls() == calls);
        assert(owner.prefetch().expert_prefetch_bytes() == expert_bytes);
    }
    assert(munmap(mapping, page_size) == 0);
}

} // namespace

int main() {
    test_deactivate_waits_for_live_lease_and_rejects_new_acquires();
    test_lease_moves_release_each_owner_once();
    test_conflicting_owner_cannot_take_over_active_registry();
    test_mapping_and_tensor_registration_are_owner_lifetime_bound();
    return 0;
}
