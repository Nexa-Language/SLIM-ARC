#!/usr/bin/env bash
set -euo pipefail

manifest="${1:?usage: test-build-manifest.sh <manifest>}"
grep -qx 'LLAMA_COMMIT=360e134' "${manifest}"
grep -Eq '^LLAMA_RESOLVED_COMMIT=360e134[0-9a-f]{33}$' "${manifest}"
grep -qx 'GGML_CPU_REPACK=OFF' "${manifest}"
grep -qx 'GGML_METAL=OFF' "${manifest}"
grep -qx 'BASELINE_PATCHED=0' "${manifest}"
grep -qx 'SLIM_ARC_PATCHED=1' "${manifest}"
grep -qx 'PATCH_IDEMPOTENT=1' "${manifest}"
