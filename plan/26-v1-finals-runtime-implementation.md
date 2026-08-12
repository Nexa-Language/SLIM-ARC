# Finals Closed-Loop Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a thread-safe, page-safe, pressure/accuracy-aware MoE expert residency loop whose promoted configuration is selected by reproducible Mac 80A3B experiments.

**Architecture:** Pure C++17 value-policy modules compute safe page ranges, wrong-prefetch reclaim plans, and bounded expert admission. The active prefetch scheduler owns synchronized router state, snapshots all mutable data before issuing POSIX advice, and exposes structured counters. The upstream patcher and Mac harness carry the new modules and flags idempotently while the default path remains unchanged.

**Tech Stack:** C++17, POSIX `posix_madvise`, Python 3 with type hints, pytest, Bash, pinned llama.cpp `360e134`, Docker/Colima with cgroups v2.

## Global Constraints

- Preserve model weights, router outputs, KV contents, sampling, and tensor addresses.
- Never reclaim a selected expert or bytes outside an expert's interior complete pages.
- Do not hold a scheduler mutex while calling `posix_madvise`.
- Advice failures are metrics and fallback events, not inference failures.
- Reject non-divisible tensor layouts and checked-arithmetic overflow.
- Keep new runtime behavior opt-in until promotion gates pass.
- Every production behavior is preceded by a failing test that fails for the intended missing behavior.
- Run normal and ASan/UBSan tests for every new standalone C++ module.
- Do not claim performance until the pinned upstream build and corrected Mac variant-linkage gate pass.
- Use the five-section repository commit format after each independently reviewable task.

---

### Task 1: Freeze the Active Baseline

**Files:**
- Inspect: `patches/llama-upstream/slim-arc-prefetch.h`
- Inspect: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Inspect: `scripts/apply-slim-arc.py`
- Inspect: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Inspect: `tests/test_apply_pressure_admission.py`

**Interfaces:**
- Consumes: current `main` at or after design commit `912ec91f`.
- Produces: a clean baseline test log and exact base SHA for later review.

- [x] **Step 1: Record the baseline SHA and worktree state**

Run:

```bash
git rev-parse HEAD
git status --short
```

Expected: the design commit is present; only explicitly preserved local materials may be untracked.

- [x] **Step 2: Run all current short tests before edits**

Run:

```bash
uv run --with pytest pytest -q
bash tests/run-cpp-unit.sh test-slim-arc-cgroup-memory
bash tests/run-cpp-unit.sh test-slim-arc-pressure-budget
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-unified-pressure
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
python3 -m compileall -q scripts tests
git diff --check
```

Expected: all existing tests pass. Any baseline failure becomes a separately reproduced bug before feature work continues.

---

### Task 2: Add Overflow-Safe Interior Page Ranges

**Files:**
- Create: `patches/llama-upstream/slim-arc-page-range.h`
- Create: `patches/llama-upstream/slim-arc-page-range.cpp`
- Create: `tests/cpp/test-slim-arc-page-range.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: unsigned address, byte length, and system page size.
- Produces: `slim_arc::page_range interior_page_range(uintptr_t, size_t, size_t) noexcept`.

- [x] **Step 1: Write the public value type and failing unit test**

The desired header API is:

```cpp
#pragma once

#include <cstddef>
#include <cstdint>

namespace slim_arc {

struct page_range {
    uintptr_t address{0};
    size_t length{0};
    size_t skipped_bytes{0};
    bool valid{false};
};

page_range interior_page_range(
    uintptr_t address,
    size_t length,
    size_t page_size) noexcept;

} // namespace slim_arc
```

The test must assert:

```cpp
const auto aligned = slim_arc::interior_page_range(0x2000, 0x2000, 0x1000);
assert(aligned.valid);
assert(aligned.address == 0x2000);
assert(aligned.length == 0x2000);
assert(aligned.skipped_bytes == 0);

const auto inward = slim_arc::interior_page_range(0x2003, 0x3000, 0x1000);
assert(inward.valid);
assert(inward.address == 0x3000);
assert(inward.length == 0x2000);
assert(inward.skipped_bytes == 0x1000);

const auto subpage = slim_arc::interior_page_range(0x2003, 0x0ffc, 0x1000);
assert(subpage.valid);
assert(subpage.length == 0);
assert(subpage.skipped_bytes == 0x0ffc);
```

Also cover zero length, zero page size, non-power-of-two page size, address overflow, and a returned interval never escaping `[address, address + length)`.

- [x] **Step 2: Register the target and verify RED**

Add `test-slim-arc-page-range` to the test runner with only `slim-arc-page-range.cpp` as a module source.

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-page-range
```

Expected: compilation or assertion failure because `interior_page_range` is not implemented.

- [x] **Step 3: Implement checked inward alignment**

The implementation must:

```cpp
if (page_size == 0 || (page_size & (page_size - 1)) != 0) {
    return {};
}
if (length > UINTPTR_MAX - address) {
    return {};
}
```

Compute the first aligned address without `address + page_size - 1` overflow, round the exclusive end down, return a valid zero-length range when the input is structurally valid but contains no complete page, and calculate skipped bytes with checked subtraction.

- [x] **Step 4: Verify GREEN and sanitizers**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-page-range
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-page-range
git diff --check
```

Expected: both runs pass with no warnings.

- [x] **Step 5: Commit the page-range primitive**

Commit subject:

```text
[feat][Experts][1/4] Add safe page ranges
```

The body records inward-only alignment, rejected invalid page sizes, and sanitizer evidence.

---

### Task 3: Add a Pure Wrong-Prefetch Reclaim Planner

**Files:**
- Create: `patches/llama-upstream/slim-arc-expert-reclaim.h`
- Create: `patches/llama-upstream/slim-arc-expert-reclaim.cpp`
- Create: `tests/cpp/test-slim-arc-expert-reclaim.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: `page_range` from Task 2, immutable expert tensor views, prefetched IDs, selected IDs.
- Produces: deterministic `wasted_expert_ids` and `build_expert_reclaim_plan` value results.

- [x] **Step 1: Write the desired planner API and failing tests**

Use:

```cpp
struct expert_tensor_view {
    uintptr_t address{0};
    size_t total_bytes{0};
    int expert_count{0};
};

struct expert_reclaim_item {
    int expert_id{-1};
    uintptr_t address{0};
    size_t length{0};
    size_t skipped_bytes{0};
};

struct expert_reclaim_plan {
    std::vector<expert_reclaim_item> items;
    uint64_t invalid_layouts{0};
    uint64_t invalid_ids{0};
    uint64_t skipped_bytes{0};
};

std::vector<int> wasted_expert_ids(
    const std::vector<int> & prefetched,
    const std::vector<int> & selected);

expert_reclaim_plan build_expert_reclaim_plan(
    const std::vector<expert_tensor_view> & tensors,
    const std::vector<int> & wasted_ids,
    size_t page_size);
```

Core assertions:

```cpp
assert((wasted_expert_ids({1, 2, 2, 7}, {2, 8}) == std::vector<int>{1, 7}));
const expert_tensor_view tensor{0x1000, 4 * 4096, 4};
const auto plan = build_expert_reclaim_plan({tensor}, {1}, 4096);
assert(plan.items.size() == 1);
assert(plan.items[0].expert_id == 1);
assert(plan.items[0].address == 0x2000);
assert(plan.items[0].length == 4096);
```

Add explicit tests for negative/out-of-range IDs, zero expert count, non-divisible layout, multiple views, address overflow, sub-page slices, duplicate selected IDs, and deterministic first-occurrence ordering.

- [x] **Step 2: Register the target and verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim
```

Expected: compilation or assertion failure because the planner is absent.

- [x] **Step 3: Implement set semantics without a new dependency**

Preserve first occurrence order from `prefetched`, deduplicate with bounded vector scans, remove any ID appearing in `selected`, and reject each ID not valid for a tensor view. Require `total_bytes % expert_count == 0`. Use checked multiplication and addition before constructing an expert slice.

- [x] **Step 4: Verify GREEN and sanitizers**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim
git diff --check
```

Expected: all planner boundaries pass.

- [x] **Step 5: Commit the pure planner**

Commit subject:

```text
[feat][Experts][2/4] Plan wrong-page reclaim
```

---

### Task 4: Replace Mutable Router Pointers with Locked Snapshots

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `scripts/apply-slim-arc.py`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Create: `tests/test_apply_expert_reclaim.py`

**Interfaces:**
- Consumes: current router observations and registered immutable expert metadata.
- Produces: `std::vector<int> cached_experts_snapshot(int layer) const`, exact unique hit/waste accounting, and an idempotent generated graph hook.

- [x] **Step 1: Add a failing snapshot/metric test**

The test must compile against:

```cpp
std::vector<int> cached_experts_snapshot(int layer) const;
```

It must store a snapshot, update the scheduler with a different router vector, and assert that the stored snapshot remains unchanged. Add a metric test where selected IDs contain duplicates and assert no unsigned waste underflow occurs.

- [x] **Step 2: Verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
```

Expected: compilation failure for the missing snapshot API or assertion failure for duplicate-safe accounting.

- [x] **Step 3: Add `expert_state_mtx_` and snapshot mutable state**

Move the following under the dedicated mutex:

```cpp
cached_router_experts_
last_prefetched_experts_
prev_router_experts_
expert_pop_counts_
```

`cache_router_experts` computes unique set intersection/difference once. `issue_expert_willneed` snapshots predictor state and target metadata under the lock, releases it, issues advice, then stores only the successfully issued expert IDs under the lock.

- [x] **Step 4: Change both generated hook sites**

Replace:

```cpp
int nc = 0;
const int * ce = s->get_cached_experts(l, &nc);
if (ce && nc > 0) s->prefetch_experts(l, ce, nc);
```

with:

```cpp
const std::vector<int> experts = s->cached_experts_snapshot(l);
if (!experts.empty()) {
    s->prefetch_experts(l, experts.data(), static_cast<int>(experts.size()));
}
```

The patch test runs the script twice and asserts byte-identical output and no `get_cached_experts` call remains.

- [x] **Step 5: Verify GREEN**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py tests/test_apply_pressure_admission.py
python3 -m py_compile scripts/apply-slim-arc.py
git diff --check
```

Expected: snapshot, duplicate accounting, and patch idempotence pass.

- [x] **Step 6: Commit the concurrency boundary**

Commit subject:

```text
[bug][Experts] Fix router snapshot races
```

`Root cause` identifies mutable vector pointers escaping without synchronization.

---

### Task 5: Fix Worker, Scheduler, Mapping, and Env Lifetimes

**Files:**
- Create: `patches/llama-upstream/slim-arc-runtime.h`
- Create: `patches/llama-upstream/slim-arc-runtime.cpp`
- Create: `tests/cpp/test-slim-arc-runtime.cpp`
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `patches/llama-upstream/slim-arc-unified-scheduler.h`
- Modify: `patches/llama-upstream/slim-arc-unified-scheduler.cpp`
- Modify: `scripts/apply-slim-arc.py`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Modify: `tests/run-cpp-unit.sh`
- Modify: `tests/test_apply_expert_reclaim.py`

**Interfaces:**
- Consumes: graph notifications, model-owned mmap/tensor addresses, environment configuration.
- Produces: a model-owned runtime with lease-guarded global access, a bounded request queue, strict flags, and post-join metrics.

- [x] **Step 1: Write failing two-worker request-claim tests**

Create a scheduler with two workers, register one valid tensor, notify layer 0 twice, and require exactly two completed requests. Run a second case with two different layers and require each request generation to be claimed once. The current layer-only predicate must fail the same-layer case; an incomplete generation-only fix may fail by letting both workers claim one request.

- [x] **Step 2: Write failing runtime-lease and mapping-owner tests**

Define a single model-owned runtime interface:

```cpp
class runtime_lease {
  public:
    runtime_lease() noexcept = default;
    runtime_lease(runtime_lease && other) noexcept;
    runtime_lease & operator=(runtime_lease && other) noexcept;
    ~runtime_lease();

    explicit operator bool() const noexcept;
    prefetch_scheduler & prefetch() const noexcept;
    unified_io_scheduler & unified() const noexcept;

  private:
    friend runtime_lease acquire_runtime() noexcept;
    runtime_owner * owner_{nullptr};
};

class runtime_owner {
  public:
    explicit runtime_owner(size_t total_budget_bytes);
    ~runtime_owner();

    void activate();
    void deactivate();
    prefetch_scheduler & prefetch() noexcept;
    unified_io_scheduler & unified() noexcept;
};

runtime_lease acquire_runtime() noexcept;
```

The test acquires a lease, starts `deactivate()` on another thread, proves teardown waits while the lease is held, releases the lease, then proves teardown completes and every subsequent acquire is empty. Register a mapped tensor/expert before activation; after deactivation, attempts through the global path must issue zero `WILLNEED` and zero `DONTNEED` calls.

This replaces both raw global scheduler getters. `runtime_owner` is stored as the final member of `llama_model::impl`, so reverse member destruction deactivates and joins the runtime before `pimpl->mappings` can unmap model pages. The global registry never owns the runtime; it holds a mutex-protected non-owning pointer only while the owner is active. Lease acquisition increments an active-call count before releasing the registry lock. Deactivation removes the registry pointer, rejects new leases, waits for the count to reach zero, then stops workers.

- [x] **Step 3: Write failing strict parser tests**

Add seams/counters that prove:

- `SLIM_ARC_EXPERT_CONF=0`, empty, `false`, and invalid text do not enable the flag;
- popularity accepts only a complete integer in `[0, 64]` and rejects negative, overflow, empty, and trailing text.

- [x] **Step 4: Verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-runtime
```

Expected: the current same-layer wake predicate, raw global access, persistent global mmap registry, or permissive parser fails the new assertions.

- [x] **Step 5: Implement a bounded claimed-request queue**

Replace target-layer/signature state with:

```cpp
struct prefetch_request {
    uint64_t generation;
    int layer;
};

std::deque<prefetch_request> pending_requests_;
uint64_t next_request_generation_{0};
static constexpr size_t max_pending_requests{64};
```

Each worker pops one request under `mtx_`; no worker observes a request without removing it. When the queue is full, drop only the oldest unclaimed request, increment `dropped_requests_`, then enqueue the new request. Tests do not accept duplicate processing or an unbounded queue.

- [x] **Step 6: Move every address registry into `runtime_owner`**

Remove `g_scheduler`, `g_unified_scheduler`, and `g_mmap_regions`. `runtime_owner` contains `prefetch_scheduler` before `unified_io_scheduler` so reverse member destruction destroys unified state first. The scheduler owns mmap regions, tensor metadata, and expert metadata; no address registry exists outside the runtime.

Implement a new idempotent `patch_model()` path in `apply-slim-arc.py`. The pinned anchors are the final `tensor_split_owned` member in `llama_model::impl` and the `use_mmap_buffer` mapping-transfer loop in `llama_model_base::load_tensors`. Extend the fixture with a minimal `llama-model.cpp` containing both anchors. The generated model patch must validate mapping indices, offsets, byte lengths, and address addition before registration. `patch_model_loader()` becomes cleanup-only and must not insert or retain scheduler, mapping-registry, or SLIM-ARC address ownership.

Patch pinned `src/llama-model.cpp`, not `llama-model-loader.cpp`, to:

1. add `std::unique_ptr<slim_arc::runtime_owner> slim_arc_runtime;` as the final `llama_model::impl` member;
2. after `ml.mappings` have moved into `pimpl->mappings`, construct the owner only when mmap-backed CPU tensors are active and the model exceeds the existing threshold;
3. register pimpl mapping regions and `ml.weights_map` tensor/expert views while the owner is inactive;
4. call `activate()` only after registration is complete.

Generated graph hooks acquire a `runtime_lease` and use `lease.prefetch()` / `lease.unified()` for the whole dereference window. No hook receives a raw global scheduler pointer. Patcher fixtures must include a minimal `llama-model.cpp` owner/transfer pattern and assert the runtime field is last in the generated minimal impl block.

Add `slim-arc-runtime.h/.cpp` to the standalone copy list and `slim-arc-runtime.cpp` to generated CMake exactly once. Remove model-loader construction of static schedulers and the global mmap registry block; model loader retains no SLIM-ARC address after mappings transfer to `llama_model::impl`.

- [x] **Step 7: Implement strict env parsing**

Use exact value `1` to enable boolean flags and `std::from_chars` for popularity K in `[0, 64]`. Reject negative, overflow, empty, and trailing-text input. Emit one bounded warning and use the safe disabled default.

- [x] **Step 8: Verify GREEN and sanitizers**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-runtime
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-runtime
uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py
git diff --check
```

- [x] **Step 9: Commit lifecycle hardening**

Commit subject:

```text
[bug][Scheduler] Fix advice lifetimes
```

---

### Task 6: Execute Safe Wrong-Prefetch Reclaim

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `scripts/apply-slim-arc.py`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Modify: `tests/run-cpp-unit.sh`
- Modify: `tests/test_apply_expert_reclaim.py`

**Interfaces:**
- Consumes: Task 3 planner, an exact consumed generation record, actual selected IDs, page size.
- Produces: opt-in `SLIM_ARC_EXPERT_RECLAIM_WASTE=1` behavior and `expert_reclaim_stats`.

- [x] **Step 1: Write failing syscall-seam tests**

Define:

```cpp
struct expert_reclaim_stats {
    uint64_t candidate_experts{0};
    uint64_t calls{0};
    uint64_t reclaimed_bytes{0};
    uint64_t skipped_bytes{0};
    uint64_t madvise_failures{0};
    uint64_t invalid_layouts{0};
    uint64_t invalid_ids{0};
};
```

Inject a test advice function that records address, length, and advice. Assert selected experts are never advised, every call uses `POSIX_MADV_DONTNEED`, successful bytes exclude failed calls, failures do not throw, and flag-off counters remain zero.

- [x] **Step 2: Verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
```

Expected: missing reclaim stats or no recorded DONTNEED call.

- [x] **Step 3: Integrate lock-inside/execute-outside reclaim**

At router comparison, consume the previous prefetch set once under the expert mutex, snapshot tensor views and selected IDs, release the mutex, construct the plan, then execute advice. Count only return-code-zero calls as reclaimed bytes. Saturate all counters.

- [x] **Step 4: Carry source files through patch and CMake**

Add page-range and expert-reclaim headers/sources to the standalone copy list. Add both `.cpp` sources to the generated CMake list exactly once. Remove on-demand prototype files from the active copy list while preserving their historical tracked files if provenance requires them.

- [x] **Step 5: Verify GREEN**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-page-range
bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py tests/test_apply_pressure_admission.py
python3 -m py_compile scripts/apply-slim-arc.py
git diff --check
```

- [x] **Step 6: Commit runtime reclaim**

Commit subject:

```text
[feat][Experts][3/4] Reclaim wrong pages
```

---

### Task 7: Add a Pure Bounded Residency Policy

**Files:**
- Create: `patches/llama-upstream/slim-arc-expert-residency.h`
- Create: `patches/llama-upstream/slim-arc-expert-residency.cpp`
- Create: `tests/cpp/test-slim-arc-expert-residency.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: pressure state, budget, stable IDs, temporal IDs, hot scores, hit/waste EWMA.
- Produces: deterministic `expert_residency_decision` with ordered admitted IDs and reason counters.

- [x] **Step 1: Write value types and failing policy tests**

Use explicit enums and value inputs:

```cpp
enum class expert_pressure_state { missing, normal, high, critical };

struct expert_candidate {
    int expert_id{-1};
    uint64_t bytes{0};
    uint32_t popularity{0};
    bool stable{false};
    bool temporal{false};
};

struct expert_residency_input {
    expert_pressure_state pressure{expert_pressure_state::missing};
    uint64_t budget_bytes{0};
    size_t max_experts{0};
    uint32_t waste_ratio_milli{0};
    std::vector<expert_candidate> candidates;
};

struct expert_residency_decision {
    std::vector<int> expert_ids;
    uint64_t admitted_bytes{0};
    uint64_t skipped_bytes{0};
    bool fallback{false};
};

expert_residency_decision select_resident_experts(
    const expert_residency_input & input);
```

Add a pure pressure controller and waste EWMA:

```cpp
struct expert_pressure_sample {
    bool valid{false};
    uint64_t current_bytes{0};
    uint64_t maximum_bytes{0};
};

class expert_pressure_controller {
  public:
    expert_pressure_state update(const expert_pressure_sample & sample) noexcept;
};

uint32_t update_waste_ewma_milli(
    uint32_t previous_milli,
    uint32_t sample_milli,
    bool initialized) noexcept;
```

Use these fixed parameters:

- enter high at `current/max >= 8500` basis points;
- enter critical at `current/max >= 9500` basis points;
- leave critical for high after two consecutive samples at or below `9000` basis points;
- leave high for normal after two consecutive samples at or below `7500` basis points;
- any invalid, zero-maximum, or `current > maximum` sample yields `missing` and resets recovery count;
- waste EWMA initializes to the first sample and then uses integer `floor((3 * previous + sample) / 4)`;
- high waste begins at `600` permille and recovers below `400` permille after two consecutive samples;
- popularity decay occurs every `64` valid router samples by replacing each count with `count / 2`.

Tests must cover critical pressure returns no speculative targets, high pressure admits stable-only, normal pressure orders stable then temporal then hot, missing pressure returns deterministic compatibility fallback, zero budget, max count, duplicate/invalid IDs, overflow, tie ordering, and waste-ratio boundaries. Pressure sequence assertions are: `7000 -> normal`, `8600 -> high`, `9600 -> critical`, `8900, 8900 -> high`, and `7400, 7400 -> normal`.

- [x] **Step 2: Register target and verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-expert-residency
```

Expected: compilation or assertion failure before implementation.

- [x] **Step 3: Implement minimal deterministic policy**

Use stable sorting by category and original order, not an unordered container. Admit a whole expert only when both byte budget and count allow it. Treat zero-byte/negative IDs as invalid skipped candidates. Use saturating requested/skipped accounting.

- [x] **Step 4: Verify GREEN and sanitizers**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-expert-residency
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-expert-residency
git diff --check
```

- [x] **Step 5: Commit the policy**

Commit subject:

```text
[feat][Experts][4/4] Select resident experts
```

---

### Task 8: Integrate Adaptive Residency and Bounded History

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `patches/llama-upstream/slim-arc-unified-scheduler.h`
- Modify: `patches/llama-upstream/slim-arc-unified-scheduler.cpp`
- Modify: `scripts/apply-slim-arc.py`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Modify: `tests/cpp/test-slim-arc-unified-pressure.cpp`
- Modify: `tests/test_apply_expert_reclaim.py`

**Interfaces:**
- Consumes: Task 7 pure policy and an injectable cgroup pressure snapshot provider.
- Produces: opt-in `SLIM_ARC_EXPERT_RESIDENCY=1`, bounded decay, hysteresis, structured metrics.

- [ ] **Step 1: Write failing integration tests**

Tests must prove:

- injected `{current=96, maximum=100}` critical pressure yields zero expert advice;
- injected `{current=86, maximum=100}` high pressure admits stable ID `{1}` and never popularity-only ID `{3}`;
- injected `{current=70, maximum=100}` normal pressure with candidates stable `1`, temporal `2`, hot `3` and a two-expert budget admits `{1, 2}`;
- injected invalid pressure yields the legacy target order with `fallback=true` and increments the missing-pressure reason counter;
- pressure sequence `96%, 89%, 89%, 74%, 74%` transitions `critical, critical, high, high, normal`;
- waste samples `800, 800, 300, 300` permille exercise the exact EWMA and recovery counters;
- popularity decays at the configured bounded interval and never overflows;
- flag-off behavior matches the previous target-selection path.

- [ ] **Step 2: Verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-unified-pressure
```

Expected: missing flag/policy integration assertions fail.

- [ ] **Step 3: Inject deterministic pressure snapshots**

Add to `unified_io_scheduler`:

```cpp
using pressure_snapshot_provider = std::function<cgroup_memory_snapshot()>;

explicit unified_io_scheduler(
    size_t total_budget_bytes,
    prefetch_scheduler * weight_prefetcher,
    kv_eviction_manager * kv_manager,
    pressure_snapshot_provider pressure_provider = {});
```

The empty provider installs the production reader for `/sys/fs/cgroup`; tests inject a deterministic lambda or finite sequence. Convert each valid cgroup snapshot to `expert_pressure_sample` and pass the resulting state to the prefetch scheduler once per tick. An invalid snapshot explicitly passes `missing`; it must not accidentally become critical.

- [ ] **Step 4: Integrate pure decisions from snapshots**

Construct candidates under `expert_state_mtx_`, including stable/temporal flags and bounded popularity. Snapshot pressure, waste EWMA, and byte budget once per scheduling tick. Call the pure policy outside the state lock, issue advice, and update success state/counters under the lock.

Use only the fixed Task 7 thresholds and two-sample recovery; no environment variable may silently change the experiment policy.

- [ ] **Step 5: Bound/decay popularity**

Use saturating `uint32_t` counts. Every 64 valid router samples, halve every count and retain vector capacity. Ensure the decay occurs once for the global sample boundary, not independently for each candidate.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-unified-pressure
bash tests/run-cpp-unit.sh test-slim-arc-expert-residency
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py tests/test_apply_pressure_admission.py
git diff --check
```

- [ ] **Step 7: Commit adaptive integration**

Commit subject:

```text
[feat][Scheduler] Close expert residency loop
```

---

### Task 9: Carry Finals Flags and Metrics Through the Mac Harness

**Files:**
- Modify: `scripts/macos/run_constrained.py`
- Modify: `scripts/macos/container/run-benchmark.sh`
- Modify: `scripts/macos/container/run_manifest.py`
- Modify: `scripts/macos/container/fake-llama-bench.sh`
- Modify: `tests/macos/test_run_constrained.py`
- Modify: `tests/macos/test_run_manifest.py`
- Modify: `tests/macos/test_run_ablation.py`
- Create: `tests/macos/test-runtime-metrics-smoke.sh`
- Modify: `scripts/macos/configs/current-ablation.json`

**Interfaces:**
- Consumes: `SLIM_ARC_EXPERT_RECLAIM_WASTE`, `SLIM_ARC_EXPERT_RESIDENCY`, runtime metric lines.
- Produces: safe allowlisted Docker env arguments and frozen structured run manifests.

- [ ] **Step 1: Write failing allowlist and strict metric-parser tests**

Require both new flags to pass validation only with value `1`. Unknown `SLIM_ARC_*` variables must still fail closed.

Define exactly one machine line per patched benchmark process:

```text
[SLIM-ARC-RUNTIME] schema=1 expert_samples=0 expert_issued_bytes=0 expert_hit_bytes=0 expert_waste_bytes=0 reclaim_candidates=0 reclaim_calls=0 reclaimed_bytes=0 reclaim_skipped_bytes=0 reclaim_failures=0 residency_samples=0 residency_admitted_experts=0 residency_admitted_bytes=0 residency_skipped_bytes=0 residency_fallbacks=0 pressure_normal=0 pressure_high=0 pressure_critical=0
```

All 18 fields after the prefix are required exactly once and contain unsigned decimal integers. `run_manifest.py` receives repeatable `--runtime-log` paths, accepts zero rows for baseline, and requires exactly one valid line from each successful patched repetition. Duplicate fields/lines, missing fields, unknown fields, non-decimal values, or values above `uint64_t` are manifest errors. The manifest stores `runtime_metrics` per repetition and a `runtime_metrics_summary` formed only by saturating sums of counter fields; it never averages hit-rate strings.

`run-benchmark.sh` accumulates one `--runtime-log <rep-N.stderr.log>` pair for each executed repetition and passes the array to `run_manifest.py`. The fake patched benchmark writes the exact fixture line to stderr. `test-runtime-metrics-smoke.sh` runs the test image with a small read-only bind-mounted fixture model, finite cgroup/no-swap limits, and the fake benchmark override, then asserts schema 1 and one parsed row without using 80A3B weights.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run --with pytest pytest -q tests/macos/test_run_constrained.py tests/macos/test_run_manifest.py tests/macos/test_run_ablation.py
```

Expected: tests fail because the flags, metrics parser, and new finalist order are absent.

- [ ] **Step 3: Add strict flags and five exact comparison configs**

Add:

```json
[
  {"name": "baseline", "variant": "baseline", "env": {}},
  {"name": "patched-control", "variant": "patched", "env": {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1"}},
  {"name": "patched-reclaim", "variant": "patched", "env": {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1"}},
  {"name": "patched-residency", "variant": "patched", "env": {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RESIDENCY": "1"}},
  {"name": "patched-combined", "variant": "patched", "env": {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1", "SLIM_ARC_EXPERT_RESIDENCY": "1"}}
]
```

`patched-control` explicitly freezes current dynamic-MADV and decode-SEQUENTIAL behavior. None of the four patched configurations enables legacy `SLIM_ARC_EXPERT_CONF`, `SLIM_ARC_EXPERT_POP`, `SLIM_ARC_EXPERT_BUDGET`, or `SLIM_ARC_PRESSURE_ADMISSION`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run --with pytest pytest -q tests/macos/test_run_constrained.py tests/macos/test_run_manifest.py tests/macos/test_run_ablation.py
bash -n scripts/macos/container/run-benchmark.sh
git diff --check
```

- [ ] **Step 5: Build and run the no-weight metrics smoke**

Run after the test image exists:

```bash
bash tests/macos/test-runtime-metrics-smoke.sh slim-arc-llama-test:360e134
```

Expected: the fake patched process produces one strict runtime row and the generated manifest contains the same counters.

- [ ] **Step 6: Commit harness support**

Commit subject:

```text
[test][Mac] Record finals expert policies
```

---

### Task 10: Build the Pinned Upstream and Run the Full Short Gate

**Files:**
- Modify: `scripts/macos/Dockerfile.llama`
- Create from commands: `docs/macos_test_notes/2026-08-12/build/`
- Modify: `ROADMAP.md`
- Modify: `docs/design/architecture.md`
- Modify: `docs/design/phase2a-moe-expert-prediction.md`

**Interfaces:**
- Consumes: all runtime commits from Tasks 2–9.
- Produces: patched pinned llama.cpp build, patch-idempotence evidence, variant-linkage evidence, updated architecture.

- [ ] **Step 1: Run the complete short gate**

Run:

```bash
UV_CACHE_DIR=/tmp/slim-arc-uv-cache uv run --with pytest pytest -q
bash tests/run-cpp-unit.sh test-slim-arc-cgroup-memory
bash tests/run-cpp-unit.sh test-slim-arc-pressure-budget
bash tests/run-cpp-unit.sh test-slim-arc-page-range
bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim
bash tests/run-cpp-unit.sh test-slim-arc-expert-residency
bash tests/run-cpp-unit.sh test-slim-arc-runtime
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-unified-pressure
for target in test-slim-arc-page-range test-slim-arc-expert-reclaim test-slim-arc-expert-residency test-slim-arc-runtime test-slim-arc-prefetch-budget; do
  SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh "$target"
done
PYTHONPYCACHEPREFIX=/tmp/slim-arc-pycache python3 -m compileall -q scripts tests
find scripts tests -type f -name '*.sh' -exec bash -n {} +
git diff --check
```

Expected: zero failures and no compiler warnings.

- [ ] **Step 2: Build the pinned images and prove double-apply idempotence**

Run:

```bash
bash scripts/macos/build-llama-image.sh
```

The Dockerfile applies the patch twice, hashes the full patched `src` tree before/after the second apply, and fails the build unless they match. It also builds baseline and patched `llama-cli`/`llama-bench` from `360e134`.

- [ ] **Step 3: Build and verify shared-library resolution**

Run with the required safe result directory:

```bash
mkdir -p docs/macos_test_notes/2026-08-12/build
bash scripts/macos/verify-build.sh docs/macos_test_notes/2026-08-12/build
bash tests/macos/test-variant-linkage.sh slim-arc-llama:360e134
bash tests/macos/test-runtime-metrics-smoke.sh slim-arc-llama-test:360e134
```

Expected: the patched executable resolves `libllama` from the patched build directory; the build manifest records `PATCH_IDEMPOTENT=1`; the no-weight fake patched run produces the strict `[SLIM-ARC-RUNTIME]` row and parser-backed manifest.

- [ ] **Step 4: Update architecture and ROADMAP from evidence**

Document the snapshot API, generation wakeup, page-safe reclaim, bounded residency policy, flags, counters, default fallback, and disabled on-demand prototype. Record every failed build/test root cause and its prevention gate.

- [ ] **Step 5: Request code review**

Provide the reviewer with the design plan, implementation base SHA, head SHA, exact test output, and known platform limitation. Fix all Critical and Important findings before experiments.

- [ ] **Step 6: Commit build-verified runtime documentation**

Commit subject:

```text
[milestone] Verify finals expert runtime
```

## Plan Self-Review

- **Specification coverage:** Tasks 2–3 cover page and reclaim safety; Tasks 4–5 cover all audited races/lifetimes/configuration bugs; Tasks 6–8 implement the two confirmed optimizations; Task 9 carries experiment identity; Task 10 proves pinned-upstream integration and documentation.
- **No placeholders:** every task names files, interfaces, failing tests, implementation boundary, verification commands, and commit subject.
- **Type consistency:** `page_range`, `expert_tensor_view`, `expert_reclaim_plan`, `cached_experts_snapshot`, `expert_reclaim_stats`, and `expert_residency_decision` are defined once and consumed by later tasks with the same names.
- **Deferred scope:** Mac A/B execution, charts, PPT, finals report, and GitLab staging are governed by `plan/25-v1-finals-research-closure.md` and receive a separate evidence/material/release execution plan after the runtime build gate.
