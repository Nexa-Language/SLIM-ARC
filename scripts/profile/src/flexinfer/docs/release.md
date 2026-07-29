# Open-Source Release Checklist

Use this checklist before publishing FlexInfer to a public repository.

## Git History

This repository is prepared as a fork-style history: `main` starts at upstream
`llama.cpp` commit `c7499c557`, followed by a small sequence of FlexInfer
commits. Before publishing, make sure only the intended public branch is pushed.
Do not push private development refs, old experiment branches, generated
benchmark logs, local result paths, or model artifacts.

## Upstream Delta Notes

Record the upstream relationship in the public release notes: the public
FlexInfer history starts from upstream `llama.cpp` commit `c7499c557`
(build `b3903`, dated 2024-10-10). FlexInfer then imports selected later GGUF
conversion utilities before adding the runtime changes. This is not a full
rebase onto a later `llama.cpp` revision; the core runtime delta should be
reviewed against `c7499c557`.

The prefetch-specific runtime code is compiled under the `FLEXINFER`
definition. Some changes are intentionally shared with the upstream-style
`llama-cli` and `llama-bench` builds, including 4096-byte alignment defaults,
public debug/benchmark parameters, Linux/Android build plumbing, and diagnostic
logging changes.

Document that FlexInfer's Linux direct-I/O streaming path requires 4096-byte
GGUF tensor alignment. Models produced by `scripts/convert-hf-models.sh` satisfy
this by default; externally generated GGUF files should be regenerated or
requantized with 4096-byte alignment before use.

Recommended pre-push checks:

```bash
git status --short --branch
git diff --check
git ls-tree -r --name-only HEAD | rg "build-host\.sh|build-android\.sh|README\.md|CITATION\.cff|LICENSE|NOTICE"
rg -n "<old project name>|<private username>|<absolute local path>" . --glob '!.git/**'
```

Also run a credential scanner over both the current tree and any history that
will be pushed.

## Files To Exclude

Keep these generated or local files out of the public repository:

- Model checkpoints and converted GGUF files.
- `hf-models/`, `models/` downloads, and other model caches.
- Benchmark outputs such as `bench-results/` and `bench-results-pixel9/`.
- Build/install trees such as `build-*`, `host/`, and `android/`.
- Local logs, profiler traces, and temporary experiment outputs.

## License And Notices

Keep the top-level `LICENSE` and `NOTICE` files. The public repository uses
the MIT License, matching the upstream `llama.cpp` and `ggml` license terms.
Substantial portions of the codebase are derived from `llama.cpp`, `ggml`,
`gguf-py`, and other third-party components with their own notices.

Before release:

- Retain upstream copyright and permission notices.
- Retain `gguf-py/LICENSE`.
- Retain source-file SPDX/license notices.
- Do not include model weights unless their licenses explicitly permit
  redistribution.

## Citation

Keep `CITATION.cff` and the BibTeX entry in `README.md` in sync with the
published EuroMLSys '25 paper metadata:

- Title: FlexInfer: Breaking Memory Constraint via Flexible and Efficient
  Offloading for On-Device LLM Inference
- Authors: Hongchao Du, Shangyu Wu, Arina Kharlamova, Nan Guan, and Chun Jason
  Xue
- DOI: `10.1145/3721146.3721961`
- Pages: 56--65

## Suggested Public Push

Create the public repository in the target organization, then push only the
prepared `main` branch:

```bash
git remote add public git@github.com:MarmotTech/FlexInfer.git
git push public main:main
```
