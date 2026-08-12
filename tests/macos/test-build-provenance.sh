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

scratch="$(mktemp -d /tmp/slim-arc-provenance-test.XXXXXX)"
cleanup() {
    rm -rf "${scratch}"
}
trap cleanup EXIT

commit="$(git -C "${repo_root}" rev-parse --verify HEAD^{commit})"
mapfile_file="${scratch}/paths.bin"
git -C "${repo_root}" ls-tree -r --name-only -z "${commit}" -- \
    patches/llama-upstream scripts/macos/container >"${mapfile_file}"
python3 - "${mapfile_file}" <<'PY'
from pathlib import Path
import sys

paths = [item for item in Path(sys.argv[1]).read_bytes().split(b"\0") if item]
required = {
    b"patches/llama-upstream/slim-arc-prefetch.cpp",
    b"patches/llama-upstream/slim-arc-runtime.cpp",
    b"scripts/macos/container/run-benchmark.sh",
    b"scripts/macos/container/run_manifest.py",
}
if not required.issubset(paths):
    raise SystemExit("immutable build path discovery is incomplete")
PY
