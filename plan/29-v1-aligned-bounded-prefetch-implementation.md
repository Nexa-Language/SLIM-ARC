# Aligned and Bounded Prefetch Implementation Plan

> **For Codex:** Use the `superpowers:executing-plans` skill to execute this plan task-by-task. Apply strict RED-GREEN-REFACTOR; do not start A1 until A0 normal and sanitizer gates pass.

**Goal:** Make every SLIM-ARC `WILLNEED` request page-valid and observable, then replace graph-wide FIFO work with a bounded latest-generation scheduler suitable for slow storage.

**Architecture:** Extend the existing pure page-range module with outward covering ranges and deterministic coalescing. Route both ordinary tensor and expert advice through that planner. After correctness is proven, evolve the existing request queue into a latest-generation, byte-bounded queue while preserving the model-owned scheduler lifetime and the flag-off behavior.

**Tech Stack:** C++17, POSIX `posix_madvise`, llama.cpp patch injection, Python patcher tests, shell C++ test runner, ASan/UBSan.

---

## Task 1: Characterize and implement covering page ranges

**Files:**
- Modify: `patches/llama-upstream/slim-arc-page-range.h`
- Modify: `patches/llama-upstream/slim-arc-page-range.cpp`
- Modify: `tests/cpp/test-slim-arc-page-range.cpp`

**Step 1: Write failing tests**

Add cases for aligned, unaligned, sub-page, zero-length, page-end, invalid page size,
`address + length` overflow, and ceil overflow:

```cpp
const auto covering = slim_arc::covering_page_range(0x2003, 0x1000, 0x1000);
assert(covering.valid);
assert(covering.address == 0x2000);
assert(covering.length == 0x2000);
assert(covering.extra_bytes == 0x1000);
```

Add a real anonymous-mapping regression that calls `posix_madvise` on `base + 32`
and proves the raw address fails while the planned covering range succeeds.

**Step 2: Run RED**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-page-range`

Expected: compile failure because `covering_page_range` and `extra_bytes` do not exist.

**Step 3: Implement the pure API**

Use separate result semantics instead of overloading reclaim terminology:

```cpp
struct page_range {
    uintptr_t address{0};
    size_t length{0};
    size_t edge_bytes{0};
    bool valid{false};
};

page_range covering_page_range(
    uintptr_t address,
    size_t length,
    size_t page_size) noexcept;
```

For `interior_page_range`, `edge_bytes` means excluded bytes. For
`covering_page_range`, it means additionally covered bytes. Document this explicitly.
Check all address and size conversions before arithmetic.

**Step 4: Run GREEN and sanitizer**

Run:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-page-range
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-page-range
```

Expected: both exit 0.

**Step 5: Commit**

```bash
git add patches/llama-upstream/slim-arc-page-range.h \
  patches/llama-upstream/slim-arc-page-range.cpp \
  tests/cpp/test-slim-arc-page-range.cpp
git commit -m "[bug][I/O] Align WILLNEED page ranges" \
  -m "Root cause: GGUF tensors are only 32-byte aligned while POSIX WILLNEED requires page-aligned addresses." \
  -m "Solution: Add overflow-safe outward page coverage while retaining inward reclaim ranges." \
  -m "Risks: Covering ranges include adjacent bytes sharing the boundary pages." \
  -m "Dependency: SLIM-ARC@00c953a0." \
  -m "Links: plan/28-v1-slow-storage-io-redesign.md"
```

## Task 2: Add deterministic page-range coalescing

**Files:**
- Modify: `patches/llama-upstream/slim-arc-page-range.h`
- Modify: `patches/llama-upstream/slim-arc-page-range.cpp`
- Modify: `tests/cpp/test-slim-arc-page-range.cpp`

**Step 1: Write failing table tests**

Cover empty input, invalid input, identical, overlapping, adjacent, disjoint, unsorted,
and `end` overflow. Freeze stable ascending output and saturating accounting:

```cpp
const auto result = slim_arc::coalesce_page_ranges({
    {0x3000, 0x1000, 0, true},
    {0x2000, 0x1000, 0, true},
});
assert(result.valid);
assert(result.ranges.size() == 1);
assert(result.ranges[0].address == 0x2000);
assert(result.ranges[0].length == 0x2000);
```

**Step 2: Run RED**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-page-range`

Expected: compile failure because the coalescing API is absent.

**Step 3: Implement**

Copy only valid, non-empty ranges, reject invalid/overflowing ranges, sort by address then
length, and merge overlap or adjacency. Return requested input range count and final range
count for metrics; never merge across an overflowing end.

**Step 4: Verify**

Run normal and sanitizer commands from Task 1; both must exit 0.

**Step 5: Commit**

Commit only the three owned files with subject:
`[feat][I/O] Coalesce prefetch page ranges` and the required five-section body.

## Task 3: Route ordinary prefetch through aligned ranges

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`

**Step 1: Add RED tests with an unaligned mapping**

Register two overlapping unaligned tensors in the same future layer. Inject `page_size=4096`
and an advice callback that asserts:

- every `WILLNEED` address and length is page-aligned;
- the two planned ranges are coalesced;
- budget selection uses covered bytes, not raw tensor bytes;
- callback failure increments failure count and not issued bytes.

Extend `prefetch_budget_stats` with explicit range metrics:

```cpp
uint64_t advice_requests;
uint64_t coalesced_ranges;
uint64_t covered_bytes;
uint64_t invalid_ranges;
```

**Step 2: Run RED**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget`

Expected: compile/assertion failure from raw unaligned advice and missing fields.

**Step 3: Implement the smallest correct planner seam**

In `worker_loop`, snapshot tensors under `mtx_`, release the lock, call
`covering_page_range`, coalesce, select ranges against the per-round budget, then invoke
advice. Do not hold scheduler locks during callbacks. Count only successful covered bytes as
issued.

Invalid page-size queries or invalid ranges must fail closed: issue no advice and increment
`invalid_ranges`/failures without crashing the worker.

**Step 4: Verify normal, sanitizer and runtime integration**

```bash
bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
bash tests/run-cpp-unit.sh test-slim-arc-runtime
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-runtime
```

Expected: all exit 0.

**Step 5: Commit**

Commit only the three owned files with subject:
`[bug][Prefetch] Align tensor WILLNEED requests`.

## Task 4: Route expert prefetch through aligned, coalesced ranges

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`

**Step 1: Add RED regressions matching 80A3B layout**

Use a page-aligned anonymous mapping but register expert tensors at offsets 864, 1632 and
2400 bytes. Use expert slice sizes 860160 and 589824. Assert:

- every callback address/length is page-aligned;
- ranges from different tensor roles/experts are coalesced when they overlap/abut;
- a successful expert receives exactly the successful covered bytes;
- partial failures do not inflate issued/hit/waste accounting;
- pending generation is erased if no advice succeeds.

**Step 2: Run RED**

Run: `bash tests/run-cpp-unit.sh test-slim-arc-prefetch-budget`

Expected: the injected callback rejects current unaligned requests.

**Step 3: Implement**

Build value snapshots `(expert_id, page_range)` outside the state lock, coalesce only when
accounting can still attribute success to every covered expert. Maintain a reverse mapping
from each coalesced range to the expert IDs it covers; a successful range contributes its
bytes once globally and proportionally/uniquely to settlement accounting without double
counting shared boundary pages.

If exact per-expert byte attribution becomes ambiguous for a shared page, use a deterministic
owner (lowest expert ID) and expose shared edge bytes separately. Never count one physical page
twice in global issued bytes.

**Step 4: Verify**

Run the four commands from Task 3 plus:

```bash
bash tests/run-cpp-unit.sh test-slim-arc-unified-pressure
SLIM_ARC_TEST_SANITIZE=1 bash tests/run-cpp-unit.sh test-slim-arc-unified-pressure
```

Expected: all exit 0.

**Step 5: Commit**

Commit only the three owned files with subject:
`[bug][Experts] Align expert WILLNEED requests`.

## Task 5: Preserve patch injection and machine metrics

**Files:**
- Modify: `scripts/apply-slim-arc.py`
- Modify: `tests/test_apply_expert_reclaim.py`
- Modify: `scripts/macos/container/run_manifest.py`
- Modify: `scripts/macos/parse_runtime_metrics.py`
- Modify: `tests/macos/test_run_manifest.py`
- Modify: `tests/macos/test_parse_runtime_metrics.py`

**Step 1: Add RED integration tests**

Assert the standalone copy/CMake list contains page-range exactly once; applying twice is
byte-identical; the single runtime line contains the new alignment/coalescing counters in a
stable order; parser and manifest reject duplicate/malformed/overflow values.

**Step 2: Run RED**

```bash
UV_CACHE_DIR=/tmp/slim-arc-uv-cache uv run --with pytest pytest -q \
  tests/test_apply_expert_reclaim.py \
  tests/macos/test_run_manifest.py \
  tests/macos/test_parse_runtime_metrics.py
```

Expected: new field assertions fail.

**Step 3: Implement**

Keep one authoritative metric schema. Extend, do not replace, existing fields. Runtime-disabled
patched diagnostic runs must be representable as a successful benchmark with
`runtime_metrics_status=disabled`, rather than converting the benchmark into a wrapper failure.

**Step 4: Verify**

Run the pytest command, `python3 -m py_compile` for modified Python files, and
`git diff --check`.

**Step 5: Commit**

Commit only the six owned files with subject:
`[test][I/O] Record aligned prefetch metrics`.

## Task 6: Replace FIFO backlog with latest-generation scheduling

**Files:**
- Modify: `patches/llama-upstream/slim-arc-prefetch.h`
- Modify: `patches/llama-upstream/slim-arc-prefetch.cpp`
- Modify: `tests/cpp/test-slim-arc-prefetch-budget.cpp`
- Modify: `scripts/apply-slim-arc.py`
- Modify: `tests/test_apply_expert_reclaim.py`

**Step 1: Add deterministic concurrency RED tests**

With a blocking `request_claim_hook`, publish generations 1, 2 and 3. Assert generation 1 may
finish if already claimed, generation 2 is counted stale and never advised, generation 3 is the
only pending generation. Add tests for:

- same-layer duplicate coalescing;
- queue never above one pending generation per kind;
- per-generation byte budget;
- global in-flight peak bound;
- shutdown while callback is blocked;
- flag-off target/advice order equivalence.

**Step 2: Run RED**

Run normal prefetch test. Expected: current FIFO advises generation 2.

**Step 3: Implement latest-wins queue**

Store complete immutable planned ranges in the request. Publishing a newer generation replaces
unclaimed older work and increments `stale_requests/stale_bytes`. Claiming atomically reserves
in-flight bytes; completion releases them on every success/failure path. One slow-storage worker
is the default; existing constructor remains source-compatible.

Do not attempt to cancel a `posix_madvise` already in progress. Its metrics remain attached to
the generation that issued it.

**Step 4: Verify normal and sanitizer suites**

Run prefetch, runtime and unified-pressure normal + ASan/UBSan, patcher pytest, pycompile and
`git diff --check`.

**Step 5: Commit**

Commit with subject:
`[feat][Prefetch] Bound slow-storage generations`.

## Task 7: Build pinned image and run local slow-storage campaign

**Files:**
- Modify: `scripts/macos/run_constrained.py`
- Create: `scripts/macos/run_slow_storage.py`
- Create: `tests/macos/test_run_slow_storage.py`
- Create under ignored evidence root: `docs/macos_test_notes/2026-08-13/slow-storage/`

**Step 1: Add harness RED tests**

Freeze cgroup v2 `io.max` schema, exact workload identity, cold-cache handling, device major/minor,
I/O-before/after counters, major faults, runtime metrics and no-swap validation. Test invalid
bandwidth, missing I/O controller, wrong image/model hash, partial rounds and resume behavior.

**Step 2: Implement the smallest campaign runner**

Run only baseline, patched-control and aligned-bounded candidate at 200 MiB/s first. Stop on
correctness/OOM/linkage/manifest failure. Expand to 50/20/8 MiB/s only if the candidate passes.

**Step 3: Build and verify**

Use the repository's sanitized pinned-image workflow, then run linkage and packaged runtime
metrics smoke. Do not mount current host patch sources over the image.

**Step 4: Execute interleaved evidence runs**

Run one diagnostic round, inspect structured evidence, then cold 2/warm 3 only for passing
configurations. Generate a machine decision recording promote/keep-opt-in/reject.

**Step 5: Commit code, not raw scratch**

Commit runner/tests and a compact validated summary/manifest only. Do not commit model files,
container layers, raw transient logs or `.DS_Store`.

## Task 8: Connect and preflight the Tailscale device

**Files:**
- Create after identity is confirmed: `docs/remote_test_notes/2026-08-13/device-manifest.json`
- Create: `docs/remote_test_notes/2026-08-13/preflight.md`

**Step 1: Verify tailnet membership**

Run `tailscale status` and `tailscale ping 100.66.244.55`. If the peer is absent, stop and ask
the user to finish accepting the invite; do not probe another address.

**Step 2: Read-only SSH preflight**

After host-key confirmation, collect architecture, kernel, CPU count, memory, swap, cgroup v2,
block devices/filesystems, available disk, compiler/container runtime and model hash. Do not
install packages or write outside an explicitly selected workspace.

**Step 3: Run staged smoke**

First no-weight linkage/runtime smoke, then a small model, then 80A3B only if RAM, disk and
thermal conditions are safe. Record each command and exit status in structured evidence.

**Step 4: Compare, do not pool**

Keep Mac/Colima and remote-device results separate. Compare directionality and bottleneck
metrics; do not average non-comparable TPS values.

## Task 9: A2/B decision checkpoint

**Files:**
- Create: `plan/30-v1-adaptive-prefetch-or-resident-slots.md`
- Update: `ROADMAP.md`

Use Task 7/8 evidence to choose exactly one next branch:

- If aligned bounded advice improves cold wall/read amplification: implement A2 feedback control.
- If page faults remain random and expert advice cannot overlap: implement B resident slots.
- If neither path is evidence-positive: retain A0 correctness, keep A1 opt-in, and investigate
  model layout before adding complexity.

Write the chosen plan before implementation. Defer final report/PPT changes until 2026-08-17.
