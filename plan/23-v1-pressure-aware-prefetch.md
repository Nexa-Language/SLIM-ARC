# Pressure-Aware Prefetch Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 unified scheduler 到普通权重和 expert prefetch 的预算闭环，在 cgroup 内存余量不足时主动限流，并用 80B A/B 证明它能降低峰值或解锁更低内存档。

**Architecture:** 新增独立的 Linux cgroup memory reader 与纯函数预算策略，`unified_io_scheduler` 每个 tick 计算有效预算，`prefetch_scheduler` 只对预算内的完整 tensor/expert 区间发出 `WILLNEED`。非 Linux、非 cgroup 或解析失败时保持当前行为；新策略由 `SLIM_ARC_PRESSURE_ADMISSION=1` 显式启用。

**Tech Stack:** C++17、POSIX、Linux cgroups v2、llama.cpp `360e134`、Python patch integration、macOS Colima benchmark harness。

## Global Constraints

- 只有 `plan/22-v1-macos-80b-constrained-benchmark.md` 产生可复现 baseline 且显示 prefetch memory pressure/waste 后才启动实现。
- 默认行为保持不变；`SLIM_ARC_PRESSURE_ADMISSION=1` 才启用压力感知预算。
- 默认 reserve 为 `max(memory.max * 10%, 512 MiB)`，可通过严格解析的 `SLIM_ARC_PRESSURE_RESERVE_MB` 覆盖绝对值。
- 读取失败、`memory.max=max` 或非 cgroups 平台时回退 static budget，不得解释为零预算。
- 普通权重与 expert 预取 issued bytes 不得超过各自 tick budget。
- 计算路径不能因预取预算耗尽失败；预算为零时退化为按需缺页。
- 晋级要求：解锁更低无 swap 稳定档，或 `memory.peak` 至少下降 10% 且 `pp64 + tg16` 总耗时退化不超过 15%。
- 固定模型 hash、llama.cpp `360e134`、最低稳定内存、4 vCPU 和冷/热口径做 A/B。
- 按用户要求最终成果进入单一 `main`，保持线性提交历史。

---

### Task 1: Cgroup v2 Memory Snapshot Reader

**Files:**
- Create: `patches/llama-upstream/slim-arc-cgroup-memory.h`
- Create: `patches/llama-upstream/slim-arc-cgroup-memory.cpp`
- Create: `tests/cpp/test-slim-arc-cgroup-memory.cpp`
- Create: `tests/run-cpp-unit.sh`

**Interfaces:**
- Produces: `slim_arc::cgroup_memory_snapshot read_cgroup_memory(const std::string & root)`.
- Produces type:

```cpp
enum class cgroup_memory_status {
    OK,
    UNAVAILABLE,
    UNLIMITED,
    INVALID_VALUE,
    IO_ERROR,
};

struct cgroup_memory_snapshot {
    cgroup_memory_status status;
    uint64_t current_bytes;
    uint64_t max_bytes;
};
```

- [x] **Step 1: Write failing reader tests**

```cpp
static void test_valid_snapshot(const std::filesystem::path & root) {
    write_file(root / "memory.current", "3221225472\n");
    write_file(root / "memory.max", "8589934592\n");
    const auto value = slim_arc::read_cgroup_memory(root.string());
    assert(value.status == slim_arc::cgroup_memory_status::OK);
    assert(value.current_bytes == 3221225472ULL);
    assert(value.max_bytes == 8589934592ULL);
}

static void test_unlimited_is_not_zero_budget(const std::filesystem::path & root) {
    write_file(root / "memory.current", "1\n");
    write_file(root / "memory.max", "max\n");
    const auto value = slim_arc::read_cgroup_memory(root.string());
    assert(value.status == slim_arc::cgroup_memory_status::UNLIMITED);
}
```

Also cover missing files, empty content, negative text, suffixes, overflow, trailing non-whitespace and `current > max`.

- [x] **Step 2: Run the focused C++ test and verify it fails**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-cgroup-memory`

Expected: compile failure because the new header and implementation do not exist.

- [x] **Step 3: Implement strict, side-effect-free parsing**

Use `std::from_chars` over trimmed ASCII decimal content; do not use `atoi`, `strtoull` without end checks, or exceptions. Read at most 128 bytes per file. `memory.max=max` returns `UNLIMITED`; any malformed value returns `INVALID_VALUE` and preserves zeroed numeric fields.

- [x] **Step 4: Implement the isolated C++ test runner**

`tests/run-cpp-unit.sh` must compile into `mktemp -d`, use `c++ -std=c++17 -Wall -Wextra -Werror`, and remove only its validated temporary directory on exit. It accepts an allowlisted test target name instead of arbitrary compiler arguments.

- [x] **Step 5: Run focused and sanitizer tests**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-cgroup-memory && SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-cgroup-memory`

Expected: all cases pass under normal and address/undefined sanitizers.

- [x] **Step 6: Commit the reader**

```text
[feat][Scheduler][1/4] Read cgroup memory

Root cause: NA
Solution: Add strict cgroups v2 current/max parsing with explicit fallback states.
Risks: Unsupported cgroup layouts fall back to the existing static budget.
Dependency: Linux cgroups v2 at runtime.
Links: plan/23-v1-pressure-aware-prefetch.md
```

### Task 2: Pure Pressure Budget Policy

**Files:**
- Create: `patches/llama-upstream/slim-arc-pressure-budget.h`
- Create: `patches/llama-upstream/slim-arc-pressure-budget.cpp`
- Create: `tests/cpp/test-slim-arc-pressure-budget.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: `cgroup_memory_snapshot` from Task 1.
- Produces:

```cpp
struct pressure_budget_result {
    bool pressure_data_valid;
    uint64_t static_budget_bytes;
    uint64_t reserve_bytes;
    uint64_t headroom_bytes;
    uint64_t effective_budget_bytes;
    bool throttled;
};

pressure_budget_result compute_pressure_budget(
    uint64_t static_budget_bytes,
    const cgroup_memory_snapshot & snapshot,
    uint64_t minimum_reserve_bytes,
    uint32_t reserve_basis_points);
```

- [ ] **Step 1: Write table-driven failing tests**

```cpp
constexpr uint64_t MiB = 1ULL << 20;
constexpr uint64_t GiB = 1ULL << 30;
const case_t cases[] = {
    // static, current, max, min reserve, bp, expected effective
    {GiB, 3 * GiB, 8 * GiB, 512 * MiB, 1000, GiB},
    {GiB, 7 * GiB, 8 * GiB, 512 * MiB, 1000, 214748365ULL},
    {GiB, 8 * GiB, 8 * GiB, 512 * MiB, 1000, 0},
};
```

Add explicit cases for invalid/unlimited snapshots, `current > max`, zero static budget, multiplication overflow and reserve larger than max.

- [ ] **Step 2: Run and observe the expected compile failure**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-pressure-budget`

Expected: FAIL before policy files exist.

- [ ] **Step 3: Implement saturating integer-only budget math**

Compute percentage reserve without floating point and without overflow. For a valid snapshot:

```text
headroom = max(max_bytes - current_bytes, 0)
reserve = max(minimum_reserve_bytes, floor(max_bytes * basis_points / 10000))
effective = min(static_budget_bytes, max(headroom - reserve, 0))
```

For invalid/unlimited data, set `pressure_data_valid=false`, `effective_budget_bytes=static_budget_bytes`, `throttled=false`.

- [ ] **Step 4: Run unit and sanitizer tests**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-pressure-budget && SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-pressure-budget`

Expected: PASS.

- [ ] **Step 5: Commit the policy**

```text
[feat][Scheduler][2/4] Compute pressure budget

Root cause: NA
Solution: Add overflow-safe headroom and reserve policy as a pure tested function.
Risks: A conservative reserve can reduce useful prefetch under tight limits.
Dependency: Cgroup memory snapshot reader.
Links: plan/23-v1-pressure-aware-prefetch.md
```

### Task 3: Enforce the Weight Prefetch Budget

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Create: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: `prefetch_scheduler::set_memory_budget(size_t bytes)`.
- Produces: `prefetch_budget_stats { requested_bytes, issued_bytes, skipped_bytes, rounds_throttled }` and `prefetch_scheduler::budget_stats() const`.

- [ ] **Step 1: Write a failing budget-selection test around a pure helper**

Expose a small internal helper:

```cpp
std::vector<size_t> select_prefetch_items(
    const std::vector<size_t> & item_sizes,
    uint64_t budget_bytes,
    uint64_t * requested_bytes,
    uint64_t * skipped_bytes);
```

Test that `{128, 512, 128}` under a 300-byte budget selects indices `{0, 2}`, requests 768 bytes, issues 256 bytes and skips 512 bytes. Test zero budget, exact boundary and near-`UINT64_MAX` totals.

- [ ] **Step 2: Run the test and verify failure**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget`

Expected: FAIL because budget selection is absent.

- [ ] **Step 3: Make the scheduler budget atomic and enforce it per worker round**

Change `memory_budget_` to `std::atomic<size_t>`. At the start of a worker round, load one immutable budget snapshot. Visit tensors in current layer/window order and issue `posix_madvise(..., POSIX_MADV_WILLNEED)` only for complete items that fit the remaining budget. Never partially advise an arbitrary tensor, and never let unsigned subtraction underflow.

- [ ] **Step 4: Count syscall success and failure separately**

Only add bytes to `issued_bytes` when `posix_madvise` returns 0. Add a `madvise_failures` counter; a failed hint is observable but does not fail inference.

- [ ] **Step 5: Run focused tests plus thread sanitizer where supported**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget && SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget`

Expected: PASS; issued bytes never exceed budget in concurrent notification tests.

- [ ] **Step 6: Commit enforcement**

```text
[bug][Scheduler][3/4] Enforce prefetch budget

Root cause: The unified scheduler populated memory_budget_ but the worker ignored it and advised every tensor in its lookahead window.
Solution: Enforce an atomic per-round byte budget and expose issued, skipped, and failed advice metrics.
Risks: Large tensors that exceed the remaining budget are skipped rather than partially prefetched.
Dependency: Existing prefetch scheduler.
Links: plan/23-v1-pressure-aware-prefetch.md
```

### Task 4: Integrate Pressure Admission into the Unified Scheduler

**Files:**
- Modify: `patches/llama-upstream/slim-arc-unified-scheduler.h`
- Modify: `patches/llama-upstream/slim-arc-unified-scheduler.cpp`
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `scripts/apply-slim-arc.py`
- Create: `tests/test_apply_pressure_admission.py`

**Interfaces:**
- Consumes: Tasks 1–3 modules and metrics.
- Produces: `pressure_admission_stats { samples, throttled_samples, fallback_samples, static_bytes, effective_bytes }`; environment variables `SLIM_ARC_PRESSURE_ADMISSION` and `SLIM_ARC_PRESSURE_RESERVE_MB`.

- [ ] **Step 1: Write patch-integration tests**

Create a minimal temporary llama source fixture with the exact CMake and model-loader anchors used by `apply-slim-arc.py`. Assert the script copies both new modules once, adds both `.cpp` files once, and remains byte-identical on a second application.

- [ ] **Step 2: Run the Python test and verify it fails**

Run: `uv run --with pytest pytest -q tests/test_apply_pressure_admission.py`

Expected: FAIL because the integration script does not know the new files.

- [ ] **Step 3: Add opt-in pressure configuration**

At scheduler construction, parse `SLIM_ARC_PRESSURE_ADMISSION` once. Parse `SLIM_ARC_PRESSURE_RESERVE_MB` with full end/range checks into bytes; invalid explicit configuration prints one error and disables pressure admission instead of silently using zero.

- [ ] **Step 4: Apply effective budget once per tick**

When enabled, read `/sys/fs/cgroup`, compute effective total budget, allocate weight/KV/expert shares from that effective value, and set both weight and expert budgets every tick. When effective budget is zero, set both prefetch budgets to zero; do not disable or fail model computation.

- [ ] **Step 5: Emit bounded observability output**

At shutdown, emit one summary line with pressure samples, throttled/fallback samples and current prefetch requested/issued/skipped/failure counts. Do not log every tick or print full cgroup paths.

- [ ] **Step 6: Update patch copying and CMake injection**

Add the two new `.h/.cpp` pairs to the copy allowlist and the `.cpp` files to the patched llama CMake source list. Preserve idempotence.

- [ ] **Step 7: Run all focused verification**

Run: `uv run --with pytest pytest -q tests/test_apply_pressure_admission.py && bash tests/run-cpp-unit.sh test-slim-arc-cgroup-memory && bash tests/run-cpp-unit.sh test-slim-arc-pressure-budget && bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget && python3 -m py_compile scripts/apply-slim-arc.py && git diff --check`

Expected: all tests pass.

- [ ] **Step 8: Rebuild pinned patched image**

Run: `bash scripts/macos/build-llama-image.sh --rebuild-patched`

Expected: llama.cpp `360e134` patched build succeeds, a second patch application produces no diff, and baseline image layer is unchanged.

- [ ] **Step 9: Commit integration**

```text
[feat][Scheduler][4/4] Limit pressure prefetch

Root cause: NA
Solution: Feed cgroup headroom into unified weight and expert admission with bounded metrics and safe fallbacks.
Risks: Conservative throttling can reduce prefetch overlap and throughput.
Dependency: Scheduler budget reader, policy, and enforcement commits.
Links: plan/23-v1-pressure-aware-prefetch.md
```

### Task 5: 80B A/B Gate and Promotion Decision

**Files:**
- Modify: `scripts/macos/configs/current-ablation.json`
- Create at runtime: `docs/macos_test_notes/2026-08-11/pressure-admission-results.json`
- Create at runtime: `docs/macos_test_notes/2026-08-11/pressure-admission-summary.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: lowest stable/boundary tiers from plan 22 and patched image from Task 4.
- Produces: promotion decision `enabled_for_final_demo`, `kept_opt_in`, or `removed_no_benefit` with referenced run IDs.

- [ ] **Step 1: Define exact A/B rows**

At the plan 22 lowest stable memory and first failed lower tier, 4 vCPU, no swap, same model hash and `pp64 + tg16`, run:

1. current best config without `SLIM_ARC_PRESSURE_ADMISSION`;
2. the same config with `SLIM_ARC_PRESSURE_ADMISSION=1`;
3. pressure admission with reserve 512 MiB;
4. pressure admission with reserve 1024 MiB only if row 2 throttles more than 80% of samples or still OOMs.

Each stable-tier row receives one cold and two warm repetitions. The failed lower tier receives up to two attempts per configuration.

- [ ] **Step 2: Verify functional output before comparing metrics**

Reject any row with empty output, different prompt/token counts, cgroup swap use, commit/hash mismatch, OOM at the stable tier, or malformed pressure metrics.

- [ ] **Step 3: Compute promotion criteria from raw manifests**

Promote when pressure admission either makes the lower tier stable, or decreases stable-tier `memory.peak` by at least 10% while total `pp64 + tg16` wall time regresses by no more than 15%. Use median warm wall time; report cold separately.

- [ ] **Step 4: Apply the decision**

- `enabled_for_final_demo`: update demo/test configuration to set the flag explicitly; do not make global library behavior implicit.
- `kept_opt_in`: retain implementation and tests but leave demo/default configuration unchanged.
- `removed_no_benefit`: revert only Task 3/4 production integration while retaining benchmark evidence and negative-result documentation; keep reusable pure tests only if they still test shipped code.

- [ ] **Step 5: Run regression and repository verification**

Run: `uv run --with pytest pytest -q tests/test_apply_pressure_admission.py tests/macos && bash tests/run-cpp-unit.sh test-slim-arc-cgroup-memory && bash tests/run-cpp-unit.sh test-slim-arc-pressure-budget && bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget && git diff --check`

Expected: PASS and no untracked model/build artifact.

- [ ] **Step 6: Record ROADMAP evidence and commit**

```text
[milestone] Evaluate pressure admission

Root cause: NA
Solution: Record the 80B cgroup A/B result and apply the evidence-based promotion decision.
Risks: Results are specific to the tested Linux ARM64 VM and NVMe path.
Dependency: plan/22-v1-macos-80b-constrained-benchmark.md.
Links: docs/macos_test_notes/2026-08-11/pressure-admission-summary.md
```
