# A23 Online Expert Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and evaluate a decode-only, zero-extra-matmul online transition predictor that issues bounded next-layer expert page prefetches on slow storage.

**Architecture:** A pure `expert_transition_table` stores four bounded heavy-hitter targets for every observed `(source_layer, source_expert)` row. The model-owned `prefetch_scheduler` serializes access to that table, while graph-local Router state pairs adjacent native Router outputs, issues existing generation-tracked `WILLNEED` requests, and records prediction matches. A23 is strictly opt-in and suppresses A22 graph construction when active.

**Tech Stack:** C++17, llama.cpp `360e1349f0009c5ad99d21e3c4546b707addc68a`, Python 3 patcher/pytest fixtures, POSIX `madvise`, Docker/Colima cgroups v2, Raspberry Pi 5 systemd/Tailscale SSH harness.

## Global Constraints

- `SLIM_ARC_CROSS_LAYER_TRANSITION=1` is the only enabling value.
- `SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK` must be an integer in `1..64` and no greater than the registered expert count.
- A23 runs only for `n_tokens == 1`; prefill batches neither train nor query the table.
- A23 and A22 are mutually exclusive; a valid A23 configuration suppresses A22's extra Router graph nodes.
- Native Router output remains authoritative; A23 only calls the existing `prefetch_experts()` advice path.
- Each transition row has exactly four `{uint16_t expert_id, uint16_t count}` slots.
- Each source layer decays only its own rows after 64 valid observations.
- A23 allocates no model copy, calibration file, or persistent state and adds approximately 1 MiB or less runtime state for the target model.
- Existing `[SLIM-ARC-RUNTIME] schema=3` output must remain unchanged; A23 emits a separate `[SLIM-ARC-TRANSITION] schema=1` line.
- Only the minimum correctness gates in the approved design run before performance experiments.

---

### Task 1: Pure bounded transition table

**Files:**
- Create: `patches/llama-upstream/slim-arc-expert-transition.h`
- Create: `patches/llama-upstream/slim-arc-expert-transition.cpp`
- Create: `tests/cpp/test-slim-arc-expert-transition.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: native Router expert IDs as bounded `int` arrays.
- Produces:
  - `bool expert_transition_table::register_layer(int layer, int n_experts)`
  - `void expert_transition_table::observe(int layer, const int * source_ids, int source_n, const int * target_ids, int target_n)`
  - `std::vector<int> expert_transition_table::predict(int layer, const int * source_ids, int source_n, int top_k)`
  - `void expert_transition_table::record_result(const int * predicted, int predicted_n, const int * actual, int actual_n)`
  - `expert_transition_stats expert_transition_table::statistics() const noexcept`
  - `size_t expert_transition_table::allocated_bytes() const noexcept`

- [ ] **Step 1: Add the allowlisted test target and failing behavioral test**

Add this runner case before the default branch:

```bash
test-slim-arc-expert-transition)
    readonly test_source="$test_root/test-slim-arc-expert-transition.cpp"
    readonly module_sources=("$source_root/slim-arc-expert-transition.cpp")
    ;;
```

Create a test with exact cold-start, learning, deterministic tie and decay assertions:

```cpp
#include "slim-arc-expert-transition.h"

#include <cassert>
#include <cstdint>
#include <vector>

int main() {
    slim_arc::expert_transition_table table;
    assert(table.register_layer(3, 64));
    const int source[] = {7, 2, 7, -1, 99};
    assert(table.predict(3, source, 5, 2).empty());

    const int target[] = {11, 5, 11};
    table.observe(3, source, 5, target, 3);
    assert((table.predict(3, source, 5, 2) == std::vector<int>{5, 11}));

    for (int sample = 1; sample < 64; ++sample) {
        table.observe(3, source, 5, target, 3);
    }
    const auto stats = table.statistics();
    assert(stats.updates == 64);
    assert(stats.decays == 1);
    assert(table.allocated_bytes() <= (1U << 20));
}
```

Add exact four-slot replacement and result-accounting checks:

```cpp
slim_arc::expert_transition_table bounded;
assert(bounded.register_layer(0, 8));
const int one_source[] = {0};
const int first_four[] = {1, 2, 3, 4};
bounded.observe(0, one_source, 1, first_four, 4);
const int replacement[] = {5};
bounded.observe(0, one_source, 1, replacement, 1);
assert((bounded.predict(0, one_source, 1, 4) ==
        std::vector<int>{5, 1, 2, 3}));

slim_arc::expert_transition_table measured;
assert(measured.register_layer(0, 8));
measured.observe(0, one_source, 1, first_four, 4);
const auto predicted = measured.predict(0, one_source, 1, 2);
const int actual[] = {1, 7, 7};
measured.record_result(predicted.data(), static_cast<int>(predicted.size()), actual, 3);
const auto measured_stats = measured.statistics();
assert(measured_stats.prediction_rounds == 1);
assert(measured_stats.predicted_experts == 2);
assert(measured_stats.matched_experts == 1);
```

Add invalid registration, layer-local decay and full target-model memory checks:

```cpp
assert(!bounded.register_layer(-1, 8));
assert(!bounded.register_layer(1, 0));
assert(!bounded.register_layer(1, 65536));

slim_arc::expert_transition_table decay;
assert(decay.register_layer(0, 8));
assert(decay.register_layer(1, 8));
for (int sample = 0; sample < 64; ++sample) {
    decay.observe(0, one_source, 1, replacement, 1);
}
decay.observe(1, one_source, 1, replacement, 1);
assert(decay.statistics().decays == 1);
assert((decay.predict(1, one_source, 1, 64) == std::vector<int>{5}));

slim_arc::expert_transition_table target_size;
for (int layer = 0; layer < 48; ++layer) {
    assert(target_size.register_layer(layer, 512));
}
assert(target_size.allocated_bytes() <= (1U << 20));
```

- [ ] **Step 2: Run the new target and verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-expert-transition
```

Expected: compilation fails because `slim-arc-expert-transition.h` does not exist.

- [ ] **Step 3: Implement the fixed-width table**

Define the public types exactly as follows:

```cpp
struct expert_transition_stats {
    uint64_t updates{0};
    uint64_t prediction_rounds{0};
    uint64_t empty_rounds{0};
    uint64_t predicted_experts{0};
    uint64_t matched_experts{0};
    uint64_t decays{0};
};

class expert_transition_table {
  public:
    bool register_layer(int layer, int n_experts);
    void observe(int layer, const int * source_ids, int source_n,
                 const int * target_ids, int target_n);
    std::vector<int> predict(int layer, const int * source_ids,
                             int source_n, int top_k);
    void record_result(const int * predicted, int predicted_n,
                       const int * actual, int actual_n);
    expert_transition_stats statistics() const noexcept;
    size_t allocated_bytes() const noexcept;
};
```

Use one `std::vector<transition_row>` per layer, with `transition_row` containing `std::array<transition_slot, 4>`. Normalize inputs into sorted unique valid IDs. On a full row replace the minimum-count slot, choosing the greatest target ID on a tie, and set the new count to saturating `minimum + 1`. Prediction aggregates into a dense score vector sized to `n_experts`, sorts `{expert_id, score}` by score descending then ID ascending, and returns at most `min(top_k, n_experts)` entries. After each layer's 64th observation, halve only that layer's nonzero counts and retain a minimum of one.

- [ ] **Step 4: Run focused GREEN and sanitizer**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-expert-transition
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-expert-transition
```

Expected: both commands exit `0` and print no sanitizer diagnostic.

- [ ] **Step 5: Commit the pure module**

```bash
git add patches/llama-upstream/slim-arc-expert-transition.h \
  patches/llama-upstream/slim-arc-expert-transition.cpp \
  tests/cpp/test-slim-arc-expert-transition.cpp tests/run-cpp-unit.sh
git commit -m '[feat][MoE][1/3] Learn expert transitions' \
  -m 'Root cause: NA' \
  -m 'Solution: Add a deterministic four-slot online cross-layer expert transition table with per-layer decay.' \
  -m 'Risks: Four heavy-hitter slots may omit long-tail experts.' \
  -m 'Dependency: A22 evidence d9108a5d.' \
  -m 'Links: docs/superpowers/specs/2026-08-14-a23-online-expert-transition-design.md'
```

### Task 2: Model-owned scheduler integration

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Modify: `tests/run-cpp-unit.sh`

**Interfaces:**
- Consumes: `expert_transition_table` from Task 1 and layer expert counts from `register_expert_tensor()`.
- Produces:
  - `bool prefetch_scheduler::cross_layer_transition_enabled() const noexcept`
  - `int prefetch_scheduler::cross_layer_transition_topk() const noexcept`
  - `void prefetch_scheduler::observe_expert_transition(int layer, const std::vector<int> & source, const std::vector<int> & target)`
  - `std::vector<int> prefetch_scheduler::predict_expert_transition(int layer, const std::vector<int> & source)`
  - `void prefetch_scheduler::record_expert_transition_result(const std::vector<int> & predicted, const std::vector<int> & actual)`
  - `expert_transition_stats prefetch_scheduler::expert_transition_statistics() const noexcept`

- [ ] **Step 1: Write scheduler RED tests**

Add test scopes that set environment variables before scheduler construction and restore them afterward:

```cpp
setenv("SLIM_ARC_CROSS_LAYER_TRANSITION", "1", 1);
setenv("SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", "2", 1);
slim_arc::prefetch_scheduler scheduler(0, 1);
std::vector<unsigned char> tensor(64 * 4096);
scheduler.register_expert_tensor("blk.2.ffn_down_exps", tensor.data(), tensor.size(), 2, 64);
scheduler.register_expert_tensor("blk.3.ffn_down_exps", tensor.data(), tensor.size(), 3, 64);
assert(scheduler.cross_layer_transition_enabled());
assert(scheduler.predict_expert_transition(2, {1, 2}).empty());
scheduler.observe_expert_transition(2, {1, 2}, {9, 4});
assert((scheduler.predict_expert_transition(2, {1, 2}) == std::vector<int>{4, 9}));
```

Use a table-driven exact-flag test:

```cpp
for (const char * value : {"0", "01", "true", ""}) {
    scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", value};
    scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", "2"};
    slim_arc::prefetch_scheduler disabled{0, 1};
    assert(!disabled.cross_layer_transition_enabled());
}
for (const char * value : {nullptr, "0", "65", "2x"}) {
    scoped_env enabled{"SLIM_ARC_CROSS_LAYER_TRANSITION", "1"};
    scoped_env topk{"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK", value};
    slim_arc::prefetch_scheduler disabled{0, 1};
    assert(!disabled.cross_layer_transition_enabled());
}
```

After one scheduler prediction and result, assert the getter returns
`prediction_rounds == 1`, `predicted_experts == 2`, and the exact ID intersection. Use one
`std::async` call to `predict_expert_transition()` while the advice callback calls
`expert_transition_statistics()`; require readiness within two seconds to prove no transition lock is held
across advice.

- [ ] **Step 2: Run scheduler test and verify RED**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
```

Expected: compile failure because the scheduler APIs are not declared.

- [ ] **Step 3: Integrate configuration, locking and metrics**

Include the Task 1 header, parse both environment variables once in the scheduler constructor, and add:

```cpp
const bool cross_layer_transition_enabled_;
const int cross_layer_transition_topk_;
mutable std::mutex expert_transition_mtx_;
expert_transition_table expert_transition_table_;
```

`register_expert_tensor()` calls `expert_transition_table_.register_layer(layer, n_experts)` under `expert_transition_mtx_`; duplicate tensor registrations with the same expert count remain valid. Scheduler wrappers hold that mutex only while table methods copy/update state. No scheduler lock may be held across `prefetch_experts()` or `advice_()`.

Expose `expert_transition_statistics()` as a locked value snapshot. Append this independent output in
`dump_metrics()` when enabled:

```cpp
std::fprintf(stderr,
    "[SLIM-ARC-TRANSITION] schema=1 updates=%llu prediction_rounds=%llu "
    "empty_rounds=%llu predicted_experts=%llu matched_experts=%llu decays=%llu\n",
    static_cast<unsigned long long>(stats.updates),
    static_cast<unsigned long long>(stats.prediction_rounds),
    static_cast<unsigned long long>(stats.empty_rounds),
    static_cast<unsigned long long>(stats.predicted_experts),
    static_cast<unsigned long long>(stats.matched_experts),
    static_cast<unsigned long long>(stats.decays));
```

Add `slim-arc-expert-transition.cpp` to the prefetch and runtime test link lists.

- [ ] **Step 4: Run focused GREEN**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-expert-transition
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-runtime
```

Expected: all exit `0`.

- [ ] **Step 5: Commit scheduler integration**

```bash
git add patches/llama-upstream/slim-arc-prefetch.h \
  patches/llama-upstream/slim-arc-prefetch.cpp \
  tests/cpp/test-slim-arc-prefetch-budget.cpp tests/run-cpp-unit.sh
git commit -m '[feat][MoE][2/3] Integrate transition state' \
  -m 'Root cause: NA' \
  -m 'Solution: Own the bounded transition predictor in the model runtime and expose decode callback APIs and metrics.' \
  -m 'Risks: Multi-context workloads share one learned transition table.' \
  -m 'Dependency: Task 1 transition module.' \
  -m 'Links: docs/superpowers/specs/2026-08-14-a23-online-expert-transition-design.md'
```

### Task 3: Native Router graph wiring and A22 exclusion

**Files:**
- Modify: `scripts/apply-slim-arc.py`
- Modify: `tests/test_apply_expert_reclaim.py`
- Modify: `scripts/macos/run_constrained.py`
- Modify: `scripts/macos/container/run-benchmark.sh`
- Modify: `tests/macos/test_run_constrained.py`
- Modify: `tests/macos/test_run_manifest.py`

**Interfaces:**
- Consumes: scheduler APIs from Task 2 and existing generation-tracked `prefetch_experts()` settlement.
- Produces: decode-only graph-local pairing of adjacent native Router outputs, A23 prediction issue, match accounting, and source/CMake installation.

- [ ] **Step 1: Add patcher RED assertions**

Extend the fixture assertions to require copied sources and exact graph wiring:

```python
assert context.count('std::getenv("SLIM_ARC_CROSS_LAYER_TRANSITION")') == 1
assert "observe_expert_transition(layer - 1" in context
assert "predict_expert_transition(layer, unique)" in context
assert "record_expert_transition_result" in context
assert "native_experts_by_layer" in context
assert "predicted_experts_by_layer" in context
assert cmake.count("slim-arc-expert-transition.cpp") == 1
assert "slim-arc-expert-transition.h" in second
assert "slim-arc-expert-transition.cpp" in second
```

Add an assertion that the Qwen3-Next A22 count requires the parsed transition count to be zero, so a valid A23 configuration cannot construct `slim_arc_cross_layer_topk`.

- [ ] **Step 2: Run patcher test and verify RED**

Run:

```bash
uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py
```

Expected: assertions fail because A23 sources and callback wiring are absent.

- [ ] **Step 3: Install the new sources and wire native callbacks**

Add both transition files to `SLIM_ARC_FILES` and `slim-arc-expert-transition.cpp` to the generated CMake required source list.

In `transform_qwen3next()`, parse the A23 flag and TopK with the same strict bounds as A22. Define A22's `slim_arc_cross_layer_topk_count` only when the parsed A23 count is zero. A23 itself adds no tensor, callback root, or `ggml_build_forward_expand()` call.

Extend `slim_arc_inline_router_state` with:

```cpp
bool cross_layer_transition;
std::vector<std::vector<int>> native_experts_by_layer;
std::vector<std::vector<int>> predicted_experts_by_layer;
```

For every native Router result, perform this order before the legacy A20 fallback:

```cpp
settle_pending();
if (cross_layer_transition && layer > min_layer &&
    !native_experts_by_layer[static_cast<size_t>(layer - 1)].empty()) {
    runtime->prefetch().observe_expert_transition(
        layer - 1,
        native_experts_by_layer[static_cast<size_t>(layer - 1)], unique);
}
if (cross_layer_transition &&
    !predicted_experts_by_layer[static_cast<size_t>(layer)].empty()) {
    runtime->prefetch().record_expert_transition_result(
        predicted_experts_by_layer[static_cast<size_t>(layer)], unique);
}
native_experts_by_layer[static_cast<size_t>(layer)] = unique;
if (cross_layer_transition && layer < max_layer) {
    auto predicted = runtime->prefetch().predict_expert_transition(layer, unique);
    predicted_experts_by_layer[static_cast<size_t>(layer + 1)] = predicted;
    prefetch_prediction(layer + 1, predicted);
}
```

Generalize `prefetch_prediction()` to allow either A22 or A23, retain the existing per-layer generation guard and budget reset, and suppress `prefetch_layer(layer + 1)` when either cross-layer mode is enabled. On failed graph compute, the existing unconditional generation cancellation remains the terminal cleanup.

Add both A23 variables to the Mac host/container exact allowlists. The runner accepts only the pair
`SLIM_ARC_CROSS_LAYER_TRANSITION=1` plus `TOPK=1..64`, rejects a lone variable, and records both values
in `run-manifest.json`. Add these concrete parameter cases:

```python
@pytest.mark.parametrize("value", ["1", "2", "4", "8", "64"])
def test_allows_cross_layer_transition_topk(value: str) -> None:
    config(env={
        "SLIM_ARC_CROSS_LAYER_TRANSITION": "1",
        "SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": value,
    }).validate()

@pytest.mark.parametrize("value", ["0", "65", "2x", ""])
def test_rejects_cross_layer_transition_topk(value: str) -> None:
    with pytest.raises(ValueError, match="SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK"):
        config(env={
            "SLIM_ARC_CROSS_LAYER_TRANSITION": "1",
            "SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": value,
        }).validate()

def test_transition_requires_flag_and_topk_together() -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        config(env={"SLIM_ARC_CROSS_LAYER_TRANSITION": "1"}).validate()
    with pytest.raises(ValueError, match="must be configured together"):
        config(env={"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": "2"}).validate()
```

Mirror the valid, invalid and missing-pair cases in `test_run_manifest.py` using the existing
`run_manifest.collect_slim_arc_environment()` helper:

```python
assert run_manifest.collect_slim_arc_environment({
    "SLIM_ARC_CROSS_LAYER_TRANSITION": "1",
    "SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": "2",
}) == {
    "SLIM_ARC_CROSS_LAYER_TRANSITION": "1",
    "SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": "2",
}
```

- [ ] **Step 4: Run patcher GREEN and focused C++ regression**

Run:

```bash
uv run --with pytest pytest -q tests/test_apply_expert_reclaim.py
python3 -m py_compile scripts/apply-slim-arc.py
uv run --with pytest pytest -q tests/macos/test_run_constrained.py tests/macos/test_run_manifest.py
bash tests/run-cpp-unit.sh test-slim-arc-expert-transition
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
git diff --check
```

Expected: all exit `0`; applying twice yields byte-identical output.

- [ ] **Step 5: Commit graph integration**

```bash
git add scripts/apply-slim-arc.py tests/test_apply_expert_reclaim.py \
  scripts/macos/run_constrained.py scripts/macos/container/run-benchmark.sh \
  tests/macos/test_run_constrained.py tests/macos/test_run_manifest.py
git commit -m '[feat][MoE][3/3] Prefetch learned experts' \
  -m 'Root cause: NA' \
  -m 'Solution: Pair adjacent native Router outputs and issue bounded learned next-layer prefetches without extra graph compute.' \
  -m 'Risks: The first decode graph intentionally has no A23 prediction.' \
  -m 'Dependency: Task 2 scheduler integration.' \
  -m 'Links: docs/superpowers/specs/2026-08-14-a23-online-expert-transition-design.md'
```

### Task 4: Pinned build and Mac performance screening

**Files:**
- Modify only if required by actual packaging failure: `scripts/macos/Dockerfile.llama`, `scripts/macos/build-llama-image.sh`
- Create evidence under: `docs/macos_test_notes/2026-08-14/a23-*`

**Interfaces:**
- Consumes: committed A23 patcher and fixed 80B model already stored in the Colima volume.
- Produces: one patched image identity and cold 2 GiB/no-swap control, Top2 and Top4 results.

- [ ] **Step 1: Apply twice to the pinned llama.cpp source and compare hashes**

Use one temporary checkout, not another model copy:

```bash
tmp=$(mktemp -d /tmp/slim-arc-a23-llama.XXXXXX)
git clone --no-checkout https://github.com/ggml-org/llama.cpp.git "$tmp"
git -C "$tmp" checkout 360e1349f0009c5ad99d21e3c4546b707addc68a
python3 scripts/apply-slim-arc.py "$tmp"
first=$(find "$tmp/src" -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256)
python3 scripts/apply-slim-arc.py "$tmp"
second=$(find "$tmp/src" -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256)
test "$first" = "$second"
```

Expected: both hashes match and the patcher prints `SLIM-ARC integration complete` twice.

- [ ] **Step 2: Build only the required target or refreshed image**

Run the existing sanitized image builder after the code commits so provenance binds to `HEAD`:

```bash
bash scripts/macos/build-llama-image.sh
```

Expected: patched `llama-bench` builds at the pinned commit and the variant-linkage check resolves its own `libllama.so`.

- [ ] **Step 3: Run one short smoke, then the cold screen**

Run A23 with strict variables:

```text
SLIM_ARC_CROSS_LAYER_GATE is unset
SLIM_ARC_CROSS_LAYER_TRANSITION=1
SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK=2 or 4
SLIM_ARC_INLINE_ROUTER=1
SLIM_ARC_EXPERT_PIPELINE_MB=32
```

Use the existing 2 GiB/no-swap/8 CPU cold `pp64/tg64` contract for transition-off control, Top2 and Top4. Preserve only manifests and small text logs; do not duplicate the GGUF.

- [ ] **Step 4: Make the Mac promotion decision**

Promote the best A23 point to Pi only when it does not reduce both decode TPS and wall time against the same-image control. Record A20 separately as the historical overall winner; do not mix image identities or warm/cold rows.

### Task 5: Raspberry Pi slow-disk screen and winner commit

**Files:**
- Modify: `scripts/pi/run-a22-noswap-screen.sh` or create `scripts/pi/run-a23-noswap-screen.sh` only if the existing script cannot express A23 cleanly.
- Create evidence under: `docs/pi5_4GB_test_notes/2026-08-14-a23-noswap-screen/`
- Create summary: `docs/macos_test_notes/2026-08-14/a23-online-transition-summary.json`
- Create summary: `docs/macos_test_notes/2026-08-14/a23-online-transition-summary.md`

**Interfaces:**
- Consumes: Mac-promoted TopK points, the existing remote GGUF, and Tailscale SSH target `yituodabian@100.66.244.55`.
- Produces: cold/no-swap Pi control and TopK results with restored zram, plus a keep/disable decision.

- [ ] **Step 1: Transfer only source/build deltas**

Apply the committed patch to the existing remote pinned llama.cpp tree or transfer a compressed source archive. Rebuild `llama-bench` in a new small build directory; reuse `/home/yituodabian/data/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf` in place.

- [ ] **Step 2: Run serial cold/no-swap screening**

Use transient systemd units with `ExecStopPost=... --restore-only`. For control and each Mac-promoted TopK, assert before launch that zram is active and no `llama-bench` exists; during measurement assert `/proc/swaps` has only its header; after exit assert code `0`, two JSONL rows, zram active, and no surviving benchmark process.

- [ ] **Step 3: Repeat only the provisional winner**

If one A23 setting beats control in the first screen, run it twice more. Compare the three-run median to the same-image control. Do not repeat losing points.

- [ ] **Step 4: Keep or disable A23**

Keep A23 as a device profile only if at least two repeats produce a median decode TPS above control with non-regressing wall time and no filesystem input/waste explosion. Otherwise leave it opt-in and move directly to sequential expert pack plus explicit async `pread`/double buffering.

- [ ] **Step 5: Commit and push evidence**

Commit small logs, structured summary and the final device decision with the five-part repository message, fetch/rebase `origin/main`, then push ordinary `main`. Exclude model files, build trees, `.DS_Store`, `AGENT*`, `.omo`, and generated caches.
