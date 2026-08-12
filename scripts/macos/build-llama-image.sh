#!/usr/bin/env bash
set -euo pipefail
umask 022

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${script_dir}/common.sh"

if [[ $# -ne 0 ]]; then
    printf 'usage: build-llama-image.sh\n' >&2
    exit 2
fi

require_command docker
profile="$(slim_arc_profile_name)"
docker_context="colima-${profile}"
repo_root="$(slim_arc_repo_root)"
image_tag="slim-arc-llama:360e134"
build_context="$(mktemp -d /tmp/slim-arc-llama-build.XXXXXX)"
build_archive="${build_context}.tar"
context_source_paths=(
    "scripts/macos/Dockerfile.llama"
    "scripts/apply-slim-arc.py"
)

cleanup() {
    if [[ -n "${build_context:-}" && "${build_context}" == /tmp/slim-arc-llama-build.* && -d "${build_context}" ]]; then
        rm -rf "${build_context}"
    fi
    if [[ -n "${build_archive:-}" && "${build_archive}" == /tmp/slim-arc-llama-build.*.tar && -f "${build_archive}" ]]; then
        rm -f "${build_archive}"
    fi
}
trap cleanup EXIT

slim_arc_git_commit="$(git -C "${repo_root}" rev-parse --verify HEAD^{commit})"
if [[ ! "${slim_arc_git_commit}" =~ ^[0-9a-f]{40}$ ]]; then
    printf 'Unable to resolve a full HEAD commit\n' >&2
    exit 1
fi

while IFS= read -r -d '' source_path; do
    context_source_paths+=("${source_path}")
done < <(
    git -C "${repo_root}" ls-tree -r --name-only -z "${slim_arc_git_commit}" -- \
        patches/llama-upstream \
        scripts/macos/container
)

if ! git -C "${repo_root}" diff --quiet HEAD -- "${context_source_paths[@]}"; then
    printf 'Refusing to build from tracked build-context files that differ from HEAD\n' >&2
    exit 1
fi

git -C "${repo_root}" archive \
    --format=tar \
    --output="${build_archive}" \
    "${slim_arc_git_commit}" \
    -- "${context_source_paths[@]}"
tar -xf "${build_archive}" -C "${build_context}"
if find "${build_context}" -type l -print -quit | grep -q .; then
    printf 'Build context contains a forbidden symlink\n' >&2
    exit 1
fi

build_context_sha256="$(python3 - "${build_context}" <<'PY'
from __future__ import annotations

import hashlib
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
    relative_path = path.relative_to(root).as_posix().encode("utf-8")
    content = path.read_bytes()
    mode = b"755" if path.stat().st_mode & stat.S_IXUSR else b"644"
    digest.update(relative_path)
    digest.update(b"\0")
    digest.update(mode)
    digest.update(b"\0")
    digest.update(str(len(content)).encode("ascii"))
    digest.update(b"\0")
    digest.update(content)
print(digest.hexdigest())
PY
)"
if [[ ! "${build_context_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
    printf 'Unable to calculate the sanitized build-context SHA256\n' >&2
    exit 1
fi

if find "${build_context}" -type f \( -name '*.pdf' -o -name '*.gguf' -o -name '.env' \) -print -quit | grep -q .; then
    printf 'Build context contains a forbidden artifact\n' >&2
    exit 1
fi

DOCKER_CONTEXT="${docker_context}" docker build \
    --file "${build_context}/scripts/macos/Dockerfile.llama" \
    --target runtime \
    --tag "${image_tag}" \
    --build-arg "SLIM_ARC_GIT_COMMIT=${slim_arc_git_commit}" \
    --build-arg "SLIM_ARC_BUILD_CONTEXT_SHA256=${build_context_sha256}" \
    "${build_context}"

DOCKER_CONTEXT="${docker_context}" docker build \
    --file "${build_context}/scripts/macos/Dockerfile.llama" \
    --target test \
    --tag "slim-arc-llama-test:360e134" \
    --build-arg "SLIM_ARC_GIT_COMMIT=${slim_arc_git_commit}" \
    --build-arg "SLIM_ARC_BUILD_CONTEXT_SHA256=${build_context_sha256}" \
    "${build_context}"

DOCKER_CONTEXT="${docker_context}" docker image inspect "${image_tag}" --format '{{.Id}}'
