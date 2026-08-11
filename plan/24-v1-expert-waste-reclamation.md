# Expert Prefetch Waste Reclamation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在真实 router 结果到达后，仅对“已预取但未激活”的 MoE expert 完整页发出 `DONTNEED`，降低错误预取造成的 cgroup page-cache 占用，同时避免驱逐活跃 expert。

**Architecture:** 先用纯函数计算 expert tensor 内可安全回收的 page-aligned 内部区间，再从 `last_prefetched_experts - actually_selected` 生成回收计划。`prefetch_scheduler` 在状态锁内快照集合、锁外执行 `posix_madvise`，并以 `SLIM_ARC_EXPERT_RECLAIM_WASTE=1` opt-in；现有推理和预取路径在开关关闭时不变。

**Tech Stack:** C++17、POSIX `posix_madvise`、llama.cpp `360e134`、SLIM-ARC MoE router hook、Colima/cgroups v2 80B benchmark harness。

## Global Constraints

- 只有 plan 22 证明 expert prefetch 存在显著 waste，且 plan 23 已完成或明确判定不实施后才启动。
- 只回收 `prefetched - actually_selected`；不得驱逐当前真实激活 expert 或全部上一 token expert。
- 只对 expert 地址范围内部完整覆盖的系统页执行 `DONTNEED`；不得向外对齐而触碰相邻 expert 页。
- `SLIM_ARC_EXPERT_RECLAIM_WASTE=1` 才启用；默认和开关关闭行为保持当前主线。
- madvise 失败只记录并回退到内核自然回收，不得中断推理。
- 指标至少包含 candidates、reclaim calls、reclaimed bytes、unaligned skipped bytes、madvise failures。
- 晋级要求：解锁更低无 swap 稳定档，或 `memory.peak` 至少下降 10% 且 `pp64 + tg16` 总耗时退化不超过 15%。
- A/B 必须报告 major faults、I/O bytes 与 expert prefetch hit/waste，防止用缺页抖动换取表面 RSS。
- 按用户要求最终成果进入单一 `main`，保持线性提交历史。

---

### Task 1: Safe Interior Page-Range Calculation

**Files:**
- Create: `patches/llama-upstream/slim-arc-page-range.h`
- Create: `patches/llama-upstream/slim-arc-page-range.cpp`
- Create: `tests/cpp/test-slim-arc-page-range.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Produces:

```cpp
struct page_range {
    uintptr_t address;
    size_t length;
    size_t skipped_prefix;
    size_t skipped_suffix;
    bool valid;
};

page_range interior_page_range(
    uintptr_t address,
    size_t length,
    size_t page_size);
```

- [ ] **Step 1: Write failing boundary tests**

```cpp
static void test_unaligned_range_uses_only_interior_pages() {
    const auto r = slim_arc::interior_page_range(0x1003, 0x3005, 0x1000);
    assert(r.valid);
    assert(r.address == 0x2000);
    assert(r.length == 0x2000);
    assert(r.skipped_prefix == 0x0ffd);
    assert(r.skipped_suffix == 0x0008);
}

static void test_subpage_range_is_not_reclaimable() {
    const auto r = slim_arc::interior_page_range(0x1003, 12, 4096);
    assert(!r.valid);
    assert(r.length == 0);
}
```

Also cover aligned start/end, zero length, zero/non-power-of-two page size, `address + length` overflow and `size_t` narrowing.

- [ ] **Step 2: Run and verify expected failure**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-page-range`

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Implement checked interior alignment**

Use checked addition for the exclusive end. Align start upward and end downward with integer arithmetic. Return `valid=false` when no complete page remains. Do not access memory or call the OS from this helper.

- [ ] **Step 4: Run normal and sanitizer tests**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-page-range && SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-page-range`

Expected: PASS.

- [ ] **Step 5: Commit the range helper**

```text
[feat][Experts][1/3] Compute safe page ranges

Root cause: NA
Solution: Add overflow-checked interior page alignment that never reaches adjacent expert data.
Risks: Sub-page fragments are intentionally left to normal kernel reclamation.
Dependency: NA
Links: plan/24-v1-expert-waste-reclamation.md
```

### Task 2: Deterministic Wasted-Expert Reclamation Plan

**Files:**
- Create: `patches/llama-upstream/slim-arc-expert-reclaim.h`
- Create: `patches/llama-upstream/slim-arc-expert-reclaim.cpp`
- Create: `tests/cpp/test-slim-arc-expert-reclaim.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: `page_range` from Task 1 and expert tensor metadata.
- Produces:

```cpp
struct expert_tensor_view {
    uintptr_t address;
    size_t total_bytes;
    int expert_count;
};

struct expert_reclaim_item {
    int expert_id;
    uintptr_t address;
    size_t length;
    size_t skipped_bytes;
};

std::vector<int> wasted_expert_ids(
    const std::vector<int> & prefetched,
    const std::vector<int> & selected);

std::vector<expert_reclaim_item> build_expert_reclaim_plan(
    const std::vector<expert_tensor_view> & tensors,
    const std::vector<int> & wasted_ids,
    size_t page_size);
```

- [ ] **Step 1: Write failing set and layout tests**

```cpp
const auto wasted = wasted_expert_ids({1, 2, 2, 7}, {2, 8});
assert((wasted == std::vector<int>{1, 7}));

const expert_tensor_view tensor{0x1003, 16 * 4096, 4};
const auto plan = build_expert_reclaim_plan({tensor}, {1}, 4096);
assert(plan.size() == 1);
assert(plan[0].expert_id == 1);
assert(plan[0].address >= 0x1003 + 4 * 4096);
assert(plan[0].address + plan[0].length <= 0x1003 + 8 * 4096);
```

Use plain `assert` without adding a testing framework dependency. Cover duplicate/negative/out-of-range IDs, `total_bytes % expert_count != 0`, zero experts, multiple tensor views for one expert and arithmetic overflow.

- [ ] **Step 2: Run and verify expected failure**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim`

Expected: FAIL before implementation.

- [ ] **Step 3: Implement stable set difference**

Preserve first occurrence order from `prefetched`, remove duplicates, reject negative IDs, and treat any ID present in `selected` as active. Complexity may be O(n²) because Qwen activates only 10 of 512 experts and vectors remain small; do not add a hash-table dependency.

- [ ] **Step 4: Implement checked expert slicing**

For each tensor view, require `expert_count > 0`, compute `per_expert = total_bytes / expert_count`, and reject layouts with a non-zero remainder instead of silently mis-slicing. Apply `interior_page_range` to each expert slice and accumulate skipped prefix/suffix bytes.

- [ ] **Step 5: Run normal and sanitizer tests**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim && SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim`

Expected: PASS with no out-of-range address generation.

- [ ] **Step 6: Commit the pure reclaim planner**

```text
[feat][Experts][2/3] Plan wasted page reclaim

Root cause: NA
Solution: Compute deterministic wasted-expert sets and checked page-aligned reclaim items.
Risks: Non-divisible tensor layouts are skipped and reported instead of reclaimed.
Dependency: Safe page-range helper.
Links: plan/24-v1-expert-waste-reclamation.md
```

### Task 3: Integrate Opt-In Reclamation and Metrics

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `scripts/apply-slim-arc.py`
- Create: `tests/test_apply_expert_reclaim.py`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: Tasks 1–2 helpers and existing `last_prefetched_experts_`, `experts_by_layer_`, `cache_router_experts()`.
- Produces: environment flag `SLIM_ARC_EXPERT_RECLAIM_WASTE`; `expert_reclaim_stats { candidate_experts, calls, reclaimed_bytes, skipped_bytes, madvise_failures, invalid_layouts }`.

- [ ] **Step 1: Write patch idempotence and file-copy tests**

The fixture must assert that all four new page/reclaim files are copied once, both `.cpp` files enter CMake once, and running `apply-slim-arc.py` twice is byte-identical.

- [ ] **Step 2: Write a syscall-seam unit test**

Add an injectable internal function pointer with production default `posix_madvise`. In tests, record `(address, length, advice)` calls and return configured error codes. Assert only `POSIX_MADV_DONTNEED` is issued, selected experts never appear, success bytes count only return code 0, and failures increment without throwing.

- [ ] **Step 3: Run tests and verify they fail before integration**

Run: `uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py && bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim`

Expected: FAIL because integration and seam are absent.

- [ ] **Step 4: Add a dedicated expert-state mutex and snapshot API**

Protect `cached_router_experts_`, `last_prefetched_experts_`, `prev_router_experts_` and popularity state with `expert_state_mtx_`. Add:

```cpp
std::vector<int> cached_experts_snapshot(int layer) const;
```

Update the generated llama-context hook to consume the returned vector instead of holding a raw pointer into a mutable vector. Do not hold the mutex while calling `posix_madvise`.

- [ ] **Step 5: Build and execute a reclaim plan at router comparison time**

Inside `cache_router_experts`, under the state lock:

1. snapshot the prior `last_prefetched_experts_[layer]`;
2. compute hit/waste metrics once;
3. clear the accounted prior set;
4. snapshot immutable expert tensor views and the opt-in flag;
5. update router history.

After releasing the lock, compute and execute reclaim items. Record invalid layout and unaligned skipped bytes explicitly.

- [ ] **Step 6: Extend the bounded shutdown metric line**

Append reclaim candidates/calls/MB/skipped/failures to `[SLIM-ARC-METRICS]` without per-token logging. With the flag disabled all reclaim counters must stay zero.

- [ ] **Step 7: Update integration and run focused verification**

Run: `uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py && bash tests/run-cpp-unit.sh test-slim-arc-page-range && bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim && bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget && python3 -m py_compile scripts/apply-slim-arc.py && git diff --check`

Expected: PASS; patch is idempotent; thread/state tests show no raw mutable-vector lifetime dependency.

- [ ] **Step 8: Commit integration**

```text
[feat][Experts][3/3] Reclaim wasted expert pages

Root cause: NA
Solution: Reclaim only page-aligned incorrect expert prefetches behind an opt-in flag with bounded metrics.
Risks: Reclaimed experts can fault again if the router selects them in a later token.
Dependency: Expert reclaim planner and existing router hook.
Links: plan/24-v1-expert-waste-reclamation.md
```

### Task 4: Pinned Build, Functional Output, and Fault Regression

**Files:**
- Modify: `scripts/macos/configs/current-ablation.json`
- Create at runtime: `docs/macos_test_notes/2026-08-11/expert-reclaim-functional.json`

**Interfaces:**
- Consumes: plan 22 runner, plan 23 selected configuration, Task 3 patched source.
- Produces: validated functional rows before performance promotion.

- [ ] **Step 1: Rebuild llama.cpp `360e134` patched image**

Run: `bash scripts/macos/build-llama-image.sh --rebuild-patched`

Expected: build succeeds; second patch application has no diff; baseline binary/image digest is unchanged.

- [ ] **Step 2: Run the flag-off regression**

At 12 GB, 4 vCPU, `pp4 + tg1`, compare the newly built binary with flag absent against the prior patched image. Require matching non-empty output behavior, zero reclaim calls and no new OOM/signal.

- [ ] **Step 3: Run the flag-on functional test**

Use `SLIM_ARC_EXPERT_RECLAIM_WASTE=1` with the plan 23 selected prefetch configuration. Require non-empty output, reclaim candidate count greater than zero when expert waste is greater than zero, reclaim bytes no larger than waste bytes, and swap current equal to zero.

- [ ] **Step 4: Inspect fault and I/O sanity**

Reject the build before long A/B if flag-on major faults or read bytes exceed flag-off by more than 2× on both repetitions, or if reclaimed bytes are zero despite recorded reclaimable waste.

- [ ] **Step 5: Run all regressions**

Run: `uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py tests/macos && bash tests/run-cpp-unit.sh test-slim-arc-page-range && bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim && git diff --check`

Expected: PASS.

- [ ] **Step 6: Commit functional evidence**

```text
[test] Validate expert page reclaim

Root cause: NA
Solution: Validate flag-off compatibility, flag-on output, reclaim metrics, and early fault regressions.
Risks: Short smoke inference does not establish steady-state throughput.
Dependency: Rebuilt patched llama image.
Links: docs/macos_test_notes/2026-08-11/expert-reclaim-functional.json
```

### Task 5: 80B Promotion A/B and Final Decision

**Files:**
- Create at runtime: `docs/macos_test_notes/2026-08-11/expert-reclaim-results.json`
- Create at runtime: `docs/macos_test_notes/2026-08-11/expert-reclaim-summary.md`
- Modify: `scripts/macos/configs/current-ablation.json`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: lowest stable/boundary tiers, best existing config, and optional pressure admission result.
- Produces: decision `enabled_for_final_demo`, `kept_opt_in`, or `removed_no_benefit`.

- [ ] **Step 1: Define paired A/B rows**

At lowest stable memory and first failed lower tier, no swap, 4 vCPU, same model/hash/commit and `pp64 + tg16`, compare the selected configuration with reclaim flag absent versus `SLIM_ARC_EXPERT_RECLAIM_WASTE=1`. Stable-tier rows receive one cold and two warm repetitions; failed lower-tier rows receive two attempts.

- [ ] **Step 2: Validate comparable metrics**

Reject any pair with resource/config mismatch, different token counts, empty output, swap use, malformed expert metrics or reclaim bytes greater than the aligned subset of waste bytes.

- [ ] **Step 3: Calculate the full trade-off**

For each pair report:

- `memory.peak` absolute and percentage difference;
- warm median wall time and tok/s;
- major/minor fault difference;
- cgroup read-byte difference;
- expert issued/hit/waste/reclaimed bytes;
- OOM/timeout outcome at the lower tier.

- [ ] **Step 4: Apply the promotion rule**

Promote only if reclaim makes the lower tier stable, or reduces stable-tier `memory.peak` by at least 10% while total wall time regresses by no more than 15%. A result that lowers peak but causes more than 2× major faults and unstable latency remains `kept_opt_in`, even if the basic threshold passes.

- [ ] **Step 5: Update final configuration and documentation**

- `enabled_for_final_demo`: add the explicit environment flag to the documented final config and explain reclaimed-waste semantics.
- `kept_opt_in`: document which workloads may benefit; leave final/default config unchanged.
- `removed_no_benefit`: remove production hook/module integration in a dedicated revert-style commit while retaining raw negative results; rerun flag-off regression.

- [ ] **Step 6: Run final verification**

Run: `uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py tests/macos && bash tests/run-cpp-unit.sh test-slim-arc-page-range && bash tests/run-cpp-unit.sh test-slim-arc-expert-reclaim && python3 -m py_compile scripts/apply-slim-arc.py && git diff --check && git status --short`

Expected: PASS; no model, image, build directory or token is tracked.

- [ ] **Step 7: Record ROADMAP decision and commit**

```text
[milestone] Evaluate expert page reclaim

Root cause: NA
Solution: Record the 80B memory, latency, fault, and I/O trade-off and apply the promotion decision.
Risks: Results are specific to the tested router trace, quantization, VM, and storage path.
Dependency: plan/22 benchmark and plan/23 decision.
Links: docs/macos_test_notes/2026-08-11/expert-reclaim-summary.md
```
