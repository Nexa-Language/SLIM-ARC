#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
script="${repo_root}/scripts/macos/build-llama-image.sh"

grep -Fq 'git -C "${repo_root}" archive' "${script}"
grep -Fq -- '--file "${build_context}/scripts/macos/Dockerfile.llama"' "${script}"
grep -Fq 'stat.S_IXUSR' "${script}"

if grep -Fq 'cp "${repo_root}/${source_path}"' "${script}"; then
    printf 'Build context must not copy from the mutable worktree\n' >&2
    exit 1
fi
