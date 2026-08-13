# SLIM-ARC Finals Research Closure Design v2

> **Status:** Overall design confirmed; this revision closes lifecycle, deterministic-pressure-test, and runtime-metrics gaps found by independent plan review.
>
> **Supersedes:** The runtime ownership and test-seam details in `plan/25-v1-finals-research-closure.md`. All experiment, material, GitHub, GitLab, timeline, and publication gates from v1 remain unchanged.

## Goal

Preserve the confirmed `predict -> admit -> prefetch -> observe -> reclaim` research loop while making every address lifetime, pressure transition, and emitted metric mechanically testable before the 80A3B benchmark.

## Preconditions

- Confirmed design baseline: `912ec91f`.
- Pinned upstream code inspection: llama.cpp `360e134` stores model mappings in `llama_model::impl::mappings` and destroys `impl` after the `llama_model` destructor body.
- Independent review result: v1 implementation plan was `ITERATE` because raw global scheduler pointers, non-owned mmap registries, host-only pressure reads, and an undefined metrics-to-manifest path could not prove the required invariants.

## Revised Runtime Ownership

The runtime is model-owned, not process-static.

```text
llama_model::impl
  |- mappings / buffers / tensor storage
  `- slim_arc_runtime  (declared last, therefore destroyed first)
       |- prefetch_scheduler
       |- unified_io_scheduler
       |- mmap/tensor/expert registries
       `- lease registry + shutdown barrier
```

`slim_arc_runtime` is the final `llama_model::impl` member. It activates only after mappings have transferred from `llama_model_loader` to the model and every tensor view has been registered. Its destruction order is:

1. remove the runtime from the global acquisition registry;
2. reject new leases;
3. wait until every in-flight graph-hook lease is released;
4. stop and join prefetch workers;
5. emit final metrics;
6. destroy schedulers and their address registries;
7. allow `llama_model::impl` to destroy mappings.

Graph hooks obtain a move-only `runtime_lease`; no hook receives a raw global scheduler pointer. This makes use-after-destruction impossible for valid upstream model/context lifetimes and prevents a runtime address registry from outliving the model mappings it describes.

Worker requests use a bounded queue of `(generation, layer)` values. Each worker claims by popping under the queue mutex, so two workers cannot process one generation. The queue holds at most 64 unclaimed requests; overflow drops the oldest unclaimed request and records a counter.

## Revised Pressure and Waste State

Production uses `/sys/fs/cgroup`; tests inject a `pressure_snapshot_provider`.

Fixed pressure thresholds are:

| Transition | Condition |
|---|---|
| any -> critical | `current/max >= 95%` |
| normal -> high | `current/max >= 85%` |
| critical -> high | two consecutive samples `<= 90%` |
| high -> normal | two consecutive samples `<= 75%` |
| any -> missing | invalid, zero maximum, overflow, or `current > maximum` |

Waste EWMA is initialized from the first sample and then calculated as `floor((3 * previous + sample) / 4)` in permille. High waste begins at 600 permille; recovery requires two consecutive samples below 400 permille. Popularity uses saturating `uint32_t` counters and halves all counts every 64 valid router samples.

An invalid pressure snapshot selects explicit compatibility fallback. It is never interpreted as zero headroom or critical pressure.

## Revised Runtime Metrics Contract

Each patched benchmark process emits exactly one strict line:

```text
[SLIM-ARC-RUNTIME] schema=1 expert_samples=<u64> expert_issued_bytes=<u64> expert_hit_bytes=<u64> expert_waste_bytes=<u64> reclaim_candidates=<u64> reclaim_calls=<u64> reclaimed_bytes=<u64> reclaim_skipped_bytes=<u64> reclaim_failures=<u64> residency_samples=<u64> residency_admitted_experts=<u64> residency_admitted_bytes=<u64> residency_skipped_bytes=<u64> residency_fallbacks=<u64> pressure_normal=<u64> pressure_high=<u64> pressure_critical=<u64>
```

The Mac wrapper passes every repetition stderr log to `run_manifest.py`. The parser rejects duplicate/missing/unknown fields, duplicate lines, non-decimal or overflowing values, and a successful patched repetition without exactly one row. It stores per-repetition rows plus saturating counter sums. Baseline runs require zero runtime rows.

A test-image fake benchmark produces the same line, allowing the complete wrapper/cgroup/manifest path to be tested without loading the 48.4 GB model.

## Steps

1. Execute `plan/26-v1-finals-runtime-implementation.md` with TDD.
2. Require the model-owned runtime and lease teardown test before long benchmarks.
3. Require deterministic pressure sequences and strict metric-parser fixtures.
4. Build pinned baseline/patched images, prove double-apply idempotence and variant linkage.
5. Run the no-weight wrapper/metrics smoke.
6. Only then run the reduced-repeat 80A3B comparison and apply v1 promotion gates.

## Acceptance Criteria

- No `get_global_prefetch_scheduler()` or `get_global_unified_scheduler()` raw pointer remains in generated hooks.
- All registered mmap/tensor/expert addresses are owned by the runtime that is destroyed before their model mappings.
- Runtime deactivation waits for active leases and prevents new advice.
- Two workers process two same-layer notifications exactly twice, without duplicate claims.
- High, critical, normal, recovery, and missing pressure are reproducible from injected snapshots.
- Metrics parser behavior is deterministic and tested end to end with no model weights.
- The final 80A3B manifest contains exact per-repetition runtime counters used by reports and charts.

## Risks

- Moving runtime creation from model loader to `llama_model::impl` touches a broader pinned-upstream seam; double-apply fixtures and a full pinned build are mandatory.
- A lease held by a hung graph hook can delay model destruction; this is preferable to unmapping live addresses, and shutdown wait behavior must be visible in tests/logs.
- Fixed thresholds may not promote on the current Mac workload; the policy remains opt-in and negative results remain publishable boundary evidence.
- Strict metrics parsing can turn previously tolerated logging drift into a failed run; this is intentional because silent malformed evidence is worse than an explicit invalid row.
