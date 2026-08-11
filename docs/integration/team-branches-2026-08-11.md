# Team branch integration record

## Purpose

This record documents how the two team branches were consolidated into the
single competition `main` branch on 2026-08-11. It keeps the final repository
auditable without importing generated artifacts or complete third-party
repository mirrors.

## Fixed source revisions

- Original `main`: `12aaa96996c32502ff3054062073cde54e9983fa`
- Implementation branch `haoma`:
  `51888799d006ac53475aa1d51cadfd348c42a021`
- Archive branch `agent/upload-local-sources-and-papers`:
  `ca40272ff7f5a5a60ce8f7cbf71f2504fae8c326`
- Selected archive commit:
  `b62cb0c0fae822b6d108a712764b729ca5e7851a`

Both team branches were based directly on the original `main`; neither was
behind it at integration time.

## Included content

The six commits from `haoma` were rebased into the local `main` history without
a merge commit. They provide:

- RK3588 experiment records and long-context validation data;
- missing prefetch scheduler interfaces and patch-script build fixes;
- expert-prefetch metrics, confidence gating, budget truncation and popular
  expert-pair support;
- dynamic memory-advice behavior and decode-oriented tuning;
- demo UI scrolling and long-response fixes;
- the corresponding test and Git operation records.

Archive commit `b62cb0c` was imported as the normalized commit `61b3aa3`. It
contains nine reference papers and 26 planning/audit documents. The PDFs are
marked as binary through `.gitattributes` so Git does not treat their internal
bytes as source text.

## Deliberately excluded archive commits

The following archive commits remain reachable from the fixed archive branch
but are not part of `main`:

| Commit | Archived content | Exclusion reason |
| --- | --- | --- |
| `4a8372d` | Profiling source snapshots | Complete third-party source mirror |
| `16b3150` | Main source snapshot | Complete upstream `llama.cpp` mirror |
| `251f81c` | Build support outputs | Generated build artifacts |
| `094d06b` | Build tool outputs | Generated build artifacts |
| `4a3a7a7` | UI source build files | Generated frontend output |
| `8894180` | UI node modules batch 1 | Vendored dependency directory |
| `cf02a04` | UI node modules batch 2 | Vendored dependency directory |
| `94e6953` | UI node modules batch 3 | Vendored dependency directory |
| `fe28fbf` | UI node modules batch 4 | Vendored dependency directory |
| `a79af39` | UI node modules batch 5 | Vendored dependency directory |
| `fa87e1d` | UI node modules batch 6 | Vendored dependency directory |
| `ca40272` | UI node modules batch 7 | Vendored dependency directory |

The project continues to use its patch-carrier layout. Exact third-party source
and build snapshots remain available on the archive branch for historical
reproduction, while the competition mainline contains the authored SLIM-ARC
patches, evidence and presentation material.

## Integration policy

- No merge commit was created.
- No remote integration branch or pull request was created.
- The repository owner explicitly requested direct delivery to `main`.
- Hardware/model-dependent RK3588 and 80B measurements are retained as evidence
  but are not re-executed on the macOS integration host.

## Verification record

The following checks were executed on the integrated local `main` before
delivery:

- `origin/haoma` is an ancestor of `HEAD`, and exactly six `haoma` commits are
  present after the original `main` revision;
- the integration range contains no commit with two or more parents;
- no `node_modules`, build directory, profiling source mirror or
  `src/llama-upstream` path was introduced by the integration;
- the selected archive paths match `b62cb0c`, except for two removed trailing
  spaces in an audit note and the later integration plans;
- all eight Python files under `scripts/` pass AST parsing;
- all Shell files under `scripts/` and `tests/` pass `bash -n`;
- all prefetch-scheduler calls emitted by `scripts/apply-slim-arc.py` have a
  corresponding declaration or definition in the prefetch patch;
- all nine imported paper files are recognized as PDF documents;
- `git fsck --connectivity-only --no-dangling` completes successfully.

`bash tests/test_env.sh` exits with status 1 on the integration host because
macOS has neither the Linux `mountpoint` utility nor `/sys/fs/cgroup`. This test
only validates the three Linux cgroups v2 tiers and is not applicable to the
macOS host. The RK3588 build, 80B inference and cgroup benchmarks were not
re-executed because their hardware, GGUF models and Linux environment are not
available on this machine; the original raw logs remain in the repository.
