# SLIM-ARC Finals Research Closure Design

> **Status:** Overall design confirmed by the repository owner on 2026-08-12.
>
> **Date:** 2026-08-12
>
> **Scope:** Finals-stage runtime hardening, closed-loop MoE expert residency, Mac 80A3B constrained experiments, incremental presentation/report updates, and an auditable GitHub-to-GitLab release.

## Goal

Deliver a finals-stage SLIM-ARC release that is materially stronger than the preliminary submission and can support a research-paper claim through reproducible evidence. The implementation must reduce memory/I/O waste or improve throughput under a fixed memory limit without changing the model's mathematical output, and every promoted optimization must pass correctness, resource, and performance gates.

The goal is not to maximize the count of feature flags. The goal is to close the loop:

```text
router observation
    -> immutable predictor snapshot
    -> pressure/accuracy-aware admission
    -> page-cache WILLNEED advice
    -> actual router comparison
    -> hit/waste accounting
    -> safe reclaim of wrong-prefetch pages
    -> next admission decision
```

## Current Baseline

- Local `main` and `origin/main` both point to `03ba926` after linearly integrating the eight newer teammate commits from `origin/main`.
- `origin/haoma` has no commits absent from `main`.
- `origin/agent/upload-local-sources-and-papers` retains thirteen commits absent from `main`, but these are the repository owner's historical snapshots, build outputs, and `node_modules`; they are not teammate feature work and must not be merged wholesale.
- The official GitLab repository already contains 88 preliminary-stage commits. Finals publication must append to that history rather than rewrite or forge it.
- The official 80A3B Q4_K_M model is stored outside Git. Its frozen identity is:
  - Hugging Face revision: `4c8630cf7af926a9c5095cb4bbbbc65d36e20f77`
  - Size: `48410988384` bytes
  - SHA-256: `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`
  - llama.cpp revision: `360e134`
- Corrected pressure-off measurements at 2 GiB and 4 vCPU show approximately 3.76 GiB of expert prefetch advice, a 42.67% hit rate, and approximately 2.41 GiB of wrong-prefetch advice. This is the concrete motivation for reclaim and adaptive residency.
- Earlier patched Mac performance rows produced before the variant `LD_LIBRARY_PATH` fix are invalid. They may remain as historical diagnostics but must not support performance conclusions.

## Inputs and Research Rationale

### Repository survey

`docs/moe_cpu_memory_limited_survey.pdf` prioritizes:

1. separating always-on model paths from routed expert paths;
2. explicit expert residency/cache policy;
3. overlap of I/O, compute, KV, and hidden-state movement;
4. confidence-aware prediction with safe fallback;
5. expert compression only after protected-path and quality calibration;
6. speculation only after cache and pipeline behavior are stable.

The finals implementation therefore changes only page-cache advice and residency decisions for routed expert weights. It does not alter attention, embeddings, norms, router computation, shared experts, model weights, token sampling, or KV semantics.

### Paper-derived directions

- **FlexInfer:** asynchronous prefetch, memory-aware admission, and preservation of hot tensors motivate the closed-loop scheduler.
- **PowerInfer-2:** fine-grained neuron/expert placement and segmented cache motivate expert-granular metrics and residency, but its custom kernel/model-format scope is deferred.
- **DUAL-BLADE, HillInfer, ScoutAttention:** hierarchical KV placement and overlapped I/O remain future work because this Mac experiment does not provide direct NVMe/GPU/SmartSSD execution paths.
- **MoE-Prism, MobileMoE:** offline expert decomposition, training-time routing, and low-bit kernel co-design require retraining/calibration and are not claimed as finals-night implementations.

## Global Constraints

- Preserve model outputs: new runtime policies may issue `WILLNEED` or `DONTNEED`, but must not modify weights, router results, KV contents, or tensor addresses.
- Preserve the default path: all new behavior starts opt-in and falls back to existing mmap demand paging on invalid configuration, unsupported advice, or missing metrics.
- Never reclaim an active expert.
- Reclaim only page-aligned ranges strictly contained within an expert slice; never align outward into adjacent expert data.
- Do not hold the expert-state mutex while issuing `posix_madvise`.
- Treat non-divisible expert layouts, overflow, invalid IDs, and sub-page ranges as non-reclaimable and count them.
- New production behavior follows TDD: each behavior must first have a test that fails for the expected missing-behavior reason.
- Mac experiments use the same model hash, llama.cpp revision, prompt, seed, context, token counts, swap setting, and cache-state label for each A/B pair.
- Results from different memory tiers, cache states, devices, prompts, or token counts must not be combined into a single speedup ratio.
- Only measured, validated results may appear as achieved improvements in the presentation or finals report.
- GitLab publication must never put the access token in a URL, Git config, process log, manifest, or committed file.
- No force-push, fake commit timestamps, or replay of `node_modules`/build-output history.

## Architecture

### 1. Immutable router and predictor snapshots

The current scheduler exposes `const int * get_cached_experts(...)` backed by a mutable `std::vector`. Concurrent graph and scheduler activity can invalidate the pointer. Runtime expert state also grows and mutates without a dedicated synchronization boundary.

Introduce one `expert_state_mtx_` for:

- `cached_router_experts_`;
- `last_prefetched_experts_`;
- `prev_router_experts_`;
- bounded popularity state;
- recent hit/waste history used by adaptive admission.

Replace the raw-pointer API with a value snapshot:

```cpp
std::vector<int> cached_experts_snapshot(int layer) const;
```

The graph hook obtains a vector snapshot, releases the lock, then issues advice. Registration metadata is finalized during model initialization and remains read-only during inference. If later evidence shows concurrent registration is possible, registration receives its own metadata mutex rather than being folded into the hot expert-state lock.

The existing worker wake predicate compares only the target layer with the last processed layer. A repeated request for the same layer can therefore be lost even when its signature changes. Replace layer-based wakeup with a monotonic request generation:

```cpp
uint64_t requested_generation_;
uint64_t processed_generation_;
```

The condition-variable predicate becomes `stop_ || requested_generation_ != processed_generation_`. The worker snapshots the requested generation and registry inputs, performs advice outside the lock, and advances only that generation. Tests must exercise two consecutive notifications for the same layer.

Global lifecycle must also be explicit:

- synchronize global scheduler publication and removal, and clear it before destruction;
- stop and join worker threads before dumping final metrics;
- add an mmap unregister API at the injected upstream mapping teardown boundary, or prove from the pinned upstream ownership path that every registered mapping outlives every `apply_dynamic_madv` call;
- never retain a mapping address after its owner can unmap it.

### 2. Page-safe expert waste reclamation

Create a platform-independent planning layer and a thin POSIX execution layer.

```cpp
struct page_range {
    uintptr_t address;
    size_t length;
    size_t skipped_bytes;
};

page_range interior_page_range(
    uintptr_t address,
    size_t length,
    size_t page_size) noexcept;

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
    size_t page_size,
    uint64_t * invalid_layouts);
```

`interior_page_range` rounds the start upward and the end downward after overflow checks. If no complete page remains, it returns a zero-length range. `build_expert_reclaim_plan` requires exact divisibility of `total_bytes / expert_count`; it never guesses a tensor layout.

At actual-router observation time:

1. lock `expert_state_mtx_`;
2. copy the previous `last_prefetched_experts_[layer]`;
3. compute hit/waste once;
4. clear the consumed last-prefetch state;
5. update bounded history and copy immutable tensor views;
6. unlock;
7. compute `prefetched - selected`;
8. plan interior full-page ranges;
9. issue `POSIX_MADV_DONTNEED` through an injectable function pointer;
10. record success and failure counters without throwing.

The feature is controlled by:

```text
SLIM_ARC_EXPERT_RECLAIM_WASTE=1
```

The flag is absent by default until experiments promote it.

### 3. Pressure/accuracy-aware expert residency

The existing implementation contains independent static mechanisms: confidence intersection, unbounded all-history popularity, a byte budget, and pressure admission. The finals policy composes them into one bounded decision with hysteresis.

#### Inputs

- valid cgroup v2 `memory.current` and `memory.max` snapshot when available;
- effective prefetch budget from the existing pressure policy;
- per-layer stable experts from two recent router observations;
- bounded recency/frequency score for each expert;
- EWMA hit and waste bytes;
- current cache mode (`cold`, `warm`, or unknown) only as a metric label, never as hidden behavior.

#### State bounds

- Use saturating integer counters.
- Decay popularity at a fixed sample interval instead of accumulating for the process lifetime.
- Bound predictor history to two observations per layer.
- Bound selected experts by both maximum target count and byte budget.
- Use high/low pressure thresholds with hysteresis so a single sample cannot oscillate the policy.

#### Decision

```text
critical pressure:
    issue no speculative expert prefetch;
    reclaim proven wrong-prefetch pages;

high pressure or high waste EWMA:
    admit only stable experts that fit the byte budget;
    do not append popularity-only experts;

normal pressure with acceptable hit EWMA:
    admit stable/temporal experts first;
    append at most K bounded hot experts while budget remains;

missing/invalid pressure data:
    preserve the existing static configuration;
```

The policy never evicts an expert merely because it is unpopular. Reclaim remains tied to a proven wrong prefetch for the completed comparison step.

Expose structured counters:

- samples and pressure state transitions;
- admitted/stable/hot/skipped expert counts;
- requested/issued/skipped bytes;
- hit/waste bytes and EWMA;
- reclaim candidates/calls/success bytes/skipped bytes/failures;
- invalid layouts and invalid IDs;
- fallback count and reason.

The adaptive policy is controlled by:

```text
SLIM_ARC_EXPERT_RESIDENCY=1
```

Existing flags remain accepted for compatibility, but the finals report must distinguish legacy static modes from the closed-loop policy.

### 4. Disabled on-demand loader

`slim-arc-on-demand.cpp` is a disabled historical prototype, not the active mmap path. Its manual pointer/data management and lock handling are unsafe to present as production runtime behavior.

Final handling:

- remove it from the default patch-carrier copy list if it is still copied;
- keep a clearly labeled historical copy only if required for preliminary-stage provenance;
- remove it from active architecture diagrams and implementation counts;
- document that demand paging is provided by upstream mmap plus SLIM-ARC advice, not by a second loader.

No time is spent repairing an unused parallel loader.

## TDD and Implementation Order

### Task 1: Safe page ranges

Create:

- `patches/llama-upstream/slim-arc-page-range.h`
- `patches/llama-upstream/slim-arc-page-range.cpp`
- `tests/cpp/test-slim-arc-page-range.cpp`

Failing tests must cover:

- already aligned ranges;
- misaligned start/end with inward alignment;
- sub-page and zero-length ranges;
- address + length overflow;
- invalid/non-power-of-two page size;
- no returned byte outside the input interval.

### Task 2: Pure reclaim planner

Create:

- `patches/llama-upstream/slim-arc-expert-reclaim.h`
- `patches/llama-upstream/slim-arc-expert-reclaim.cpp`
- `tests/cpp/test-slim-arc-expert-reclaim.cpp`

Failing tests must cover:

- duplicate prefetched IDs;
- selected IDs excluded from waste;
- negative and out-of-range IDs;
- non-divisible tensor layouts;
- zero expert count;
- multiple expert tensors for one layer;
- overflow and sub-page expert slices;
- deterministic first-occurrence ordering.

### Task 3: Snapshot API and concurrency-safe metrics

Modify:

- `patches/llama-upstream/slim-arc-prefetch.h`
- `patches/llama-upstream/slim-arc-prefetch.cpp`
- `scripts/apply-slim-arc.py`

Create or extend tests to prove:

- graph hooks consume `std::vector<int> cached_experts_snapshot(int layer) const` rather than a mutable raw pointer;
- repeated router nodes cannot count one prefetch set twice;
- failed advice is not counted as issued/reclaimed bytes;
- all counters saturate instead of wrapping;
- the flag-off path produces zero reclaim calls;
- applying the patch twice is byte-identical.

### Task 4: Scheduler wakeup, global lifetime, and configuration parsing

Modify:

- `patches/llama-upstream/slim-arc-prefetch.h`;
- `patches/llama-upstream/slim-arc-prefetch.cpp`;
- `scripts/apply-slim-arc.py` when upstream teardown injection is required;
- the relevant C++ and patch-fixture tests.

Tests must first prove the current failures and then prove:

- two consecutive notifications for the same layer produce two observable generations rather than a lost wakeup;
- scheduler removal prevents graph hooks from observing an object in destruction;
- worker shutdown joins before the final metric snapshot;
- a removed mmap region never receives later phase advice;
- `SLIM_ARC_EXPERT_CONF=0`, an empty value, and invalid text do not enable confidence mode;
- popularity K rejects negative, overflowing, and trailing-text values and obeys a documented maximum.

### Task 5: Bounded adaptive residency policy

Prefer a pure policy module:

- `patches/llama-upstream/slim-arc-expert-residency.h`
- `patches/llama-upstream/slim-arc-expert-residency.cpp`
- `tests/cpp/test-slim-arc-expert-residency.cpp`

Its input and output must be plain value types so the policy can be tested without llama.cpp or cgroup I/O. Tests must cover critical/high/normal/missing pressure, hysteresis, byte and expert-count bounds, stable-first ordering, decayed popularity, zero budget, overflow, and deterministic fallback.

### Task 6: Patch and build integration

Update:

- patch copy list;
- llama.cpp CMake source list;
- graph hook snapshot call;
- environment allowlists in the Mac controller/wrapper;
- run manifest and metrics parser;
- unit-test allowlist.

Run both first-apply and second-apply fixtures. Build the pinned upstream revision and verify that the patched binary resolves its own patched shared libraries.

### Task 7: Dead prototype and known-issue cleanup

- remove `.DS_Store` files and ignore them;
- deduplicate the survey PDF while keeping one tracked canonical copy;
- mark or archive invalid pre-linkage Mac performance rows;
- correct report claims that mix cold timeout, warm throughput, memory tiers, or devices;
- retire the unsafe old GitLab history-replay script from the supported path;
- update architecture and README statements immediately with the runtime changes.

## Mac 80A3B Experiment Protocol

### Fixed environment

- Host: current Mac, using the existing Colima/Linux cgroup harness.
- Model and llama.cpp identity: exactly as listed in Current Baseline.
- Swap: `memory.swap.max=0` and observed swap current zero.
- Primary workload: fixed prompt/seed/context with `pp64 + tg16`.
- Long-decode confirmation: `tg64` for the promoted configuration if the remaining window permits.
- Every run stores command/config, Git commit, model hash, host label, cold/warm label, start/end time, and exit classification.

### Reduced-repeat schedule

The user chose fewer repetitions to fit the finals window:

1. Boundary scan at `2/4/6/8/12 GiB`, 4 vCPU: one run per tier.
2. Finalist ablation at the lowest stable tier:
   - baseline/current best;
   - reclaim only;
   - adaptive residency only;
   - combined;
   - one cold and one warm run per configuration.
3. First failed lower tier: one attempt per relevant finalist if the controller supports a safe tier below the current 2 GiB floor.
4. CPU scaling for the promoted configuration at `2/4/6/8` vCPU: one run per tier.
5. Add one tie-breaker repetition only when:
   - repeated/cold-warm normalized results differ by more than 10%;
   - a result lies within 2 percentage points of a promotion threshold;
   - metrics are malformed or an anomalous exit occurs.

### Required measurements

- output non-empty and exit classification;
- OOM/signal/timeout state;
- `memory.current`, `memory.peak`, `memory.events`, swap;
- process RSS where supported;
- major/minor faults;
- storage read bytes;
- TTFT, prompt t/s, decode t/s, total wall time;
- expert requested/issued/hit/waste/reclaimed bytes;
- admission state, fallback, skipped bytes, advice failures;
- cold/warm cache label.

### Promotion gates

#### Reclaim

Promote only when it either:

- makes a previously failing lower memory tier stable; or
- reduces stable-tier `memory.peak` by at least 10% with total wall-time regression no worse than 15%.

Reject promotion when major faults or read bytes remain above 2x the control in comparable runs, even if peak memory improves.

#### Adaptive residency

Promote only when a comparable run shows at least one primary improvement of 10% or more in expert waste, storage read bytes, or decode throughput, without increasing the lowest stable memory tier and without a regression greater than 15% in total wall time.

#### Combined policy

Call the result synergistic only if it outperforms both control and at least one single-feature variant on a primary metric while satisfying the same regression gates. Otherwise report interference or equivalence.

Negative results remain valuable boundary evidence but do not enter the final demo defaults.

## Evidence Schema and Single Source of Truth

Create a finals results document whose rows include:

```json
{
  "run_id": "finals-...",
  "git_commit": "40-hex-sha",
  "model_sha256": "d103...61a",
  "llama_cpp_commit": "360e134",
  "variant": "current|reclaim|residency|combined",
  "cache_state": "cold|warm|unknown",
  "memory_limit_bytes": 2147483648,
  "cpu_limit": 4,
  "swap_max_bytes": 0,
  "prompt_tokens": 64,
  "generated_tokens": 16,
  "status": "success|oom|timeout|signal|invalid",
  "memory_peak_bytes": 0,
  "major_faults": 0,
  "read_bytes": 0,
  "ttft_seconds": null,
  "prompt_tps": null,
  "decode_tps": null,
  "wall_seconds": null,
  "expert_issued_bytes": 0,
  "expert_hit_bytes": 0,
  "expert_waste_bytes": 0,
  "expert_reclaimed_bytes": 0,
  "source_directory": "docs/macos_test_notes/2026-08-12/runs/..."
}
```

The chart generator consumes this file and emits the same figures used by Markdown, LaTeX, and PowerPoint. Manual transcription of result numbers is prohibited.

## Finals Presentation and Report

### Preliminary preservation

Before finals editing:

- preserve the current `reports/Competition_Report/` tree as the preliminary TeX snapshot;
- preserve the current 31-slide editable PPTX as a preliminary PPTX copy;
- preserve the current tracked PPT PDF as a preliminary PDF copy;
- create a separate finals report tree from the preliminary source.

Names must be stable and explicit:

```text
reports/Competition_Report_Preliminary/
reports/Competition_Report_Finals/
reports/SLIM-ARC展示PPT-Preliminary.pptx
reports/SLIM-ARC展示PPT-Preliminary.pdf
reports/SLIM-ARC展示PPT.pptx
reports/SLIM-ARC展示PPT.pdf
```

### Incremental PowerPoint changes after 22:00

Do not rewrite or reorder the preliminary 31 slides. Append:

1. one slide for Safe Expert Waste Reclamation;
2. one slide for Pressure/Accuracy-Aware Expert Residency if correctness is complete;
3. one ablation slide generated from the finals results file;
4. one memory-throughput/Pareto or boundary slide;
5. one limitations/future-work slide if needed to distinguish implemented work from paper-inspired directions.

Each optimization slide contains the problem, mechanism, diagram, metrics, and promotion status. An optimization without a completed benchmark may be labeled implemented/validated for correctness, but may not contain an invented performance claim.

Use the existing presentation as the visual template. Duplicate the closest slide layouts and edit inherited elements. Render and inspect every slide in both PPTX and exported PDF for overflow, overlap, font substitution, and chart readability.

### Finals LaTeX report

Create an independent finals report that preserves the preliminary structure and adds:

- finals-stage motivation and contributions;
- closed-loop architecture;
- algorithms/pseudocode and safety invariants;
- thread-safety and fallback behavior;
- experimental protocol and data provenance;
- boundary, ablation, scaling, I/O, and page-fault results;
- corrected cross-device comparison;
- negative results, validity threats, and limitations;
- paper-oriented future work based on the survey and included papers.

Build the PDF, render it to images, and inspect every page. TeX source, generated figures, bibliography, and final PDF all enter the finals submission.

### Video

Do not create or upload a new video. The presentation, report, README, and submission note must use the repository's authoritative original Bilibili link and explicitly reference part P2 as the demo content. P2 is supporting demonstration material, not evidence for unrecorded finals optimizations.

## GitHub Integration

- Continue on local `main` as explicitly requested by the repository owner.
- Fetch before every publication checkpoint.
- If `origin/main` advances, protect the local worktree and rebase/fast-forward; do not add merge commits.
- Never import the historical `origin/agent/upload-local-sources-and-papers` build and dependency snapshots wholesale.
- Use the required five-section commit format and keep logical changes independently reviewable.
- At minimum, recheck remote state:
  - after runtime implementation;
  - immediately before 22:00 materials work;
  - immediately before the 23:00 GitLab staging snapshot.

## GitLab Finals Publisher

### Strategy

Preserve the official 88-commit preliminary history and append finals commits with honest timestamps.

1. Fresh-clone official GitLab `main` to a bounded temporary directory.
2. Verify the expected remote URL and current head.
3. Generate a source manifest from the validated GitHub snapshot.
4. Overlay only allowlisted files into the GitLab clone.
5. Remove only stale files that are explicitly owned by the previous manifest; never recursively delete an unresolved path.
6. Run secret, file-size, binary, generated-artifact, test, and report gates.
7. Commit finals changes on top of official `main`.
8. Push fast-forward using an ephemeral credential helper that reads `SLIM_ARC_GITLAB_TOKEN` without printing it.
9. Verify `ls-remote` and fresh-clone the pushed head.

### Allowlist

- root project metadata and documentation;
- `config/` without secrets;
- `data/` only small, documented demo inputs;
- `docs/` including canonical papers and validated result summaries;
- `patches/`;
- `plan/`;
- `reports/` including finals TeX/PDF/PPTX/PDF and generated figures;
- `scripts/`;
- `tests/`;
- necessary small demo source/assets.

### Denylist

- `.git/`, `.DS_Store`, caches and editor state;
- `.env*`, credentials, access tokens, cookies, SSH material;
- model weights and downloads;
- `node_modules/`, build directories, compiled objects/shared libraries;
- transient containers, run locks, partial downloads, raw home paths;
- unrelated temporary logs or duplicated paper copies.

### Release gates

- source and staged manifests are deterministic;
- no secret-pattern or high-entropy credential finding remains unexplained;
- no unexpected file exceeds the repository size policy;
- all expected source/test/report artifacts exist;
- full relevant unit/integration tests pass from the staged tree;
- final report PDF and presentation PDF open and render;
- Git push is fast-forward;
- post-push clone matches the staged commit and manifest.

The old publisher that deletes/rebuilds `gitlab-clean`, replays every GitHub commit, and forges June dates is unsupported for finals publication.

## Timeline

### Before 22:00 CST

- implement and review runtime changes;
- build patched pinned llama.cpp;
- run correctness and constrained experiments;
- consolidate validated JSON/CSV evidence;
- re-fetch teammate changes;
- prepare chart assets and finals report skeleton.

### At/after 22:00 CST

- freeze preliminary material copies;
- append only achieved finals deltas to the PPTX;
- complete finals LaTeX report and figures;
- export and visually inspect PPT/PDF/report PDF;
- re-fetch teammate changes and resolve through rebase.

### At 23:00 CST

- stage the best fully validated snapshot from the official GitLab head;
- run release gates;
- push only if gates pass;
- verify remote head and fresh clone;
- retain unpromoted or unfinished work on GitHub without putting it in the official snapshot.

## Acceptance Criteria

### Repository and code

- all teammate work intended for `main` is present, with no unreviewed dependency/build snapshot import;
- active runtime has no mutable-vector raw-pointer API for router snapshots;
- page range and reclaim planner tests pass normally and under ASan/UBSan;
- adaptive residency pure-policy tests cover every pressure state and boundary;
- patch application is idempotent;
- pinned upstream patched build succeeds and links to the patched libraries;
- default/flag-off path remains behaviorally compatible;
- no `.DS_Store`, duplicate survey, or unsafe active on-demand claim remains.

### Experiments

- every published row matches the frozen model and code identity;
- every published A/B row has matching resources, workload, and cache label;
- invalid pre-linkage rows cannot enter summary statistics;
- promotion decisions are mechanically derived from the documented thresholds;
- TPS, TTFT, memory, faults, and I/O are reported separately rather than collapsed into one score.

### Materials

- preliminary TeX/PPTX/PDF copies remain available;
- finals report source and PDF exist independently;
- presentation contains one incremental slide per completed optimization plus new data slides;
- all displayed numbers come from the finals evidence file;
- every slide and report page is rendered and inspected;
- the Bilibili P2 reference is consistent across materials.

### Publication

- GitHub and GitLab heads are recorded;
- official GitLab preliminary history remains intact;
- finals push is fast-forward and post-push fresh-clone verification passes;
- no secrets, models, `node_modules`, build outputs, or fake timestamps enter the official repository.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Reclaim causes refault amplification | Lower RSS but worse latency/I/O | Opt-in flag, wrong-prefetch-only invariant, 2x fault/read rejection gate |
| Predictor metrics race with graph execution | UB, corrupt metrics, nondeterminism | Value snapshots, dedicated mutex, lock-free advice execution, sanitizer tests |
| Popularity overfits a prompt or grows forever | Misleading hit rate and memory waste | Bounded/decayed state, explicit prompt disclosure, cold/warm separation |
| `madvise` differs across macOS/Linux | Non-portable behavior | Execute inside Linux VM for primary evidence, count failures, demand-page fallback |
| Reduced repetitions overstate noise | Weak paper claim | Tie-breaker rule near thresholds/anomalies, disclose repetition count |
| 2 GiB controller floor hides lower boundary | Cannot prove sub-2-GiB survival | Report as measurement floor, not physical minimum; do not weaken safety bounds casually |
| Report repeats preliminary inconsistent claims | Credibility loss | Single evidence source and explicit invalid-row filter |
| PPT editing damages preliminary material | Loss of original artifact | Versioned preliminary copies before any finals edit |
| GitLab publisher leaks token or rewrites history | Security/submission failure | Ephemeral helper, no token in URL/config, fresh clone, fast-forward-only gate |
| Teammate pushes during finals work | Missing or conflicting final state | Re-fetch at three checkpoints and rebase protected work |
| Ambitious paper ideas lack tonight's hardware/calibration | Unverifiable claims | Put INT2/3, GPU/NVMe KV, SmartSSD, training-time routing in future work only |

## Explicit Non-Goals for This Finals Window

- retraining or changing the Qwen router;
- INT2/INT3 expert quantization without calibration and quality evaluation;
- custom GPU kernels or GPU-resident expert cache;
- direct NVMe/SmartSSD KV execution;
- distributed expert placement across multiple edge devices;
- speculative decoding without a validated draft model;
- rewriting official GitLab history;
- guaranteeing a competition rank. The deliverable maximizes technical strength and evidence quality but cannot honestly guarantee judging outcomes.
