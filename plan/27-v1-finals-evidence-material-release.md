# SLIM-ARC Finals Evidence, Materials, and Release Plan

> **Date:** 2026-08-12
>
> **Status:** Authorized by the repository owner's confirmation of the overall design.
>
> **Dependencies:** `plan/25-v2-finals-research-closure.md` and a reviewed GREEN result for Tasks 8--10 in `plan/26-v1-finals-runtime-implementation.md`.

## Goal

Turn the reviewed finals runtime into reproducible 80A3B evidence, make only evidence-backed incremental changes to the finals presentation and report, and publish an auditable fast-forward snapshot to GitHub and the official GitLab without rewriting preliminary history.

The execution order is fixed:

```text
reviewed source
  -> pinned image and linkage gate
  -> packaged no-weight metrics gate
  -> constrained 80A3B comparisons
  -> machine-derived promotion decision
  -> frozen preliminary materials
  -> finals-only material deltas
  -> rendered visual QA
  -> GitHub push
  -> fresh GitLab clone and allowlisted overlay
  -> release gates and fast-forward push
  -> post-push fresh-clone verification
```

## Preconditions

- Local work stays on `main` as explicitly requested by the repository owner.
- Fetch `origin` before the build, before material freeze, and immediately before both publications. If `origin/main` advances, preserve the worktree and integrate with rebase/fast-forward only.
- The frozen model is `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`, size `48410988384`, SHA-256 `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`.
- The pinned llama.cpp revision is `360e134`.
- Colima must expose cgroup v2 with finite `memory.max`, `memory.swap.max=0`, four benchmark CPUs, and the model mounted read-only.
- Pre-linkage patched Mac measurements remain invalid for performance claims.
- User-owned untracked files are preserved. `.DS_Store`, caches, credentials, model weights, build outputs, and scratch evidence never enter a publication commit.

## Task 1: Freeze the Reviewed Runtime and Build the Pinned Images

1. Complete Task 8 normal, ASan/UBSan, Python patcher, and idempotence tests.
2. Obtain an independent code review and fix every Critical or Important finding.
3. Run the complete Task 10 short gate from the current worktree.
4. Build both `slim-arc-llama:360e134` and `slim-arc-llama-test:360e134` from a sanitized build context.
5. Require full patched-source double-apply equality, baseline/patched shared-library isolation, and a strict packaged-image runtime-metrics smoke.
6. Store build manifests and verification logs under `docs/macos_test_notes/2026-08-12/build/`.

### Acceptance

- All relevant Python and C++ tests pass without compiler warnings.
- Selected safety targets pass under ASan/UBSan.
- `PATCH_IDEMPOTENT=1` is recorded.
- Each executable resolves only its own `libllama.so`.
- The test image rejects invalid finals flags and produces one exact schema-1 runtime line for a successful patched fake repetition.

## Task 2: Run the Reduced-Repeat 80A3B Finals Matrix

Use one fixed tier: 2 GiB, four vCPU, no swap, `pp64`, `tg16`, identical prompt/seed/context. Run these five configurations in the frozen order:

1. `baseline`;
2. `patched-control`;
3. `patched-reclaim`;
4. `patched-residency`;
5. `patched-combined`.

Run exactly two complete rounds. Each round contains one labeled cold repetition and one labeled warm repetition for every configuration, for 20 attempts in total. Cold/warm preparation must be identical across variants. A failed repetition remains in the evidence set with its original outcome and is never silently retried into a success. Do not add a third round or add repetitions only to the apparent winner.

Each successful patched repetition must contain exactly one strict runtime-metrics row. Every row must bind:

- local Git commit and full patched source hash;
- model and llama.cpp identity;
- image ID and variant linkage result;
- memory, CPU, swap, prompt/token, seed, and cache labels;
- wall time, prompt/decode throughput, cgroup peak, OOM/swap/fault/I/O counters;
- expert issue/hit/waste, reclaim, residency, and pressure counters;
- raw run directory.

### Acceptance

- No result is accepted without finite cgroup/no-swap evidence and matching identities.
- Baseline has no runtime row; each successful patched repetition has exactly one.
- The accepted campaign contains exactly rounds 1 and 2, and each configuration/cache pair has two samples.
- Cold and warm rows are not mixed into one speedup.
- Different hardware or workload settings are never divided into one ratio.

## Task 3: Build the Single Source of Truth and Decide Promotion

Create a deterministic finals results JSON and a human-readable decision summary under `docs/macos_test_notes/2026-08-12/`. Generate all tables and charts from that JSON; never transcribe benchmark values manually.

Apply the fixed gates from `plan/25-v1-finals-research-closure.md`:

- reclaim promotes only if it lowers the stable tier or reduces `memory.peak` by at least 10% with wall regression no worse than 15%, while major faults and read bytes remain within 2x control;
- adaptive residency promotes only with at least 10% improvement in waste, storage reads, or decode throughput, no worse stable tier, and wall regression no worse than 15%;
- combined is synergistic only if it beats control and at least one single-feature finalist on a primary metric while satisfying the same regression gates.

Classify each feature as `promoted`, `kept_opt_in`, `rejected`, or `insufficient_evidence`. Negative results are retained as boundary evidence but do not become default claims.

### Acceptance

- Every reported number maps to a run ID and raw manifest.
- Invalidated historical Mac patched rows are mechanically excluded.
- The decision tool is deterministic and tested on missing, invalid, failed, and incomparable rows.
- Chart source data and document tables agree byte-for-byte on displayed values.

## Task 4: Freeze Preliminary Materials and Produce Finals Deltas

This task starts only at or after 22:00 CST.

1. Copy the current preliminary TeX tree, editable PPTX, and tracked PPT PDF to explicit preliminary paths before editing.
2. Create `reports/Competition_Report_Finals/` from the preliminary TeX source; never overwrite the preliminary copy.
3. Preserve the original 31-slide order and append only:
   - Safe Expert Waste Reclamation;
   - Pressure/Accuracy-Aware Expert Residency;
   - finals ablation results;
   - memory/throughput boundary or Pareto evidence;
   - limitations and paper-oriented future work when needed.
4. An implemented optimization without performance evidence is labeled correctness-validated, not accelerated.
5. Correct preliminary overclaims and condition all historical values by device, memory tier, cache state, workload, commit, and validity status.
6. Cite the authoritative Bilibili demo as P2 at `https://www.bilibili.com/video/BV1fXTF6HEAw`; do not create or upload a new video.
7. Build the finals LaTeX PDF, export the finals PPT PDF, render every page/slide, and inspect for overflow, overlap, font substitution, unreadable charts, stale labels, and inconsistent numbers.

### Acceptance

- Preliminary PPTX/PDF and TeX tree remain available and unchanged after the freeze.
- Finals PPTX/PDF and report source/PDF are independently named.
- One incremental optimization slide exists per completed optimization.
- All achieved-performance claims come from the finals JSON; literature is used only for motivation and comparison.
- Every rendered page and slide passes visual QA.

## Task 5: Publish GitHub and the Official GitLab

1. Fetch `origin`; rebase only if required; rerun affected gates.
2. Commit logical source, evidence, and materials changes with the repository five-section message format.
3. Push local `main` to GitHub and verify the remote head.
4. At or after 23:00 CST, fresh-clone the official GitLab `main` into a bounded temporary directory using an ephemeral credential helper that reads `SLIM_ARC_GITLAB_TOKEN` without printing or persisting it.
5. Verify the official preliminary head/history before mutation.
6. Overlay only normalized allowlisted paths and generate a deterministic SHA-256 manifest. Delete only files explicitly owned by the prior release manifest.
7. Block symlinks, traversal, secrets, credentials, model weights, caches, `.DS_Store`, `node_modules`, compiled outputs, unexpected large files, raw scratch evidence, and unsupported binaries.
8. Run source tests plus PDF/PPTX structure and rendered-artifact gates from the staged tree.
9. Commit honestly on top of official `main`; push without force and require fast-forward.
10. Compare `ls-remote`, then fresh-clone the pushed head and verify its manifest against the staged snapshot.

### Acceptance

- GitHub and GitLab commit IDs are recorded.
- Official preliminary history remains an ancestor of the pushed GitLab head.
- No token appears in command output, URL, Git config, manifest, process arguments, or committed files.
- Post-push fresh clone matches the staged source manifest.
- If any release gate fails, no GitLab push occurs; the failure and best validated local/GitHub snapshot are reported.

## Risks

| Risk | Consequence | Gate |
|---|---|---|
| Runtime source changes after image build | Results do not represent the commit | Rebuild on any relevant source/hash change |
| Cache or repetition bias | False winner | Fixed order, explicit cache labels, symmetric extra repetitions |
| Strict metric drift | Silent invalid evidence | Parser rejects missing/duplicate/unknown/overflow rows |
| Low-memory run stalls beyond the deadline | Materials or release miss | Reduced matrix, bounded timeout, publish only completed rows |
| PPTX editing corrupts preliminary assets | Loss of submission source | Copy and hash preliminary files before edits |
| Unsupported literature claim becomes our result | Scientific overclaim | Separate motivation, implementation, and measured evidence |
| Teammate pushes during execution | Divergent main | Fetch at every publication checkpoint and rebase/fast-forward only |
| GitLab cleanup removes unrelated history/files | Submission damage | Fresh clone, manifest-owned deletion, no recursive unresolved delete |
| Credential leakage | Account/repository compromise | Ephemeral helper, redacted output, secret scan, no token arguments |
