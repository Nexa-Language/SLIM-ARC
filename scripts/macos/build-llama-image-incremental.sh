#!/usr/bin/env bash
set -euo pipefail
umask 022

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${script_dir}/common.sh"

if [[ $# -ne 0 ]]; then
    printf 'usage: build-llama-image-incremental.sh\n' >&2
    exit 2
fi

profile="$(slim_arc_profile_name)"
docker_context="colima-${profile}"
repo_root="$(slim_arc_repo_root)"
image_tag="slim-arc-llama:360e134"
test_image_tag="slim-arc-llama-test:360e134"
build_context="$(mktemp -d /tmp/slim-arc-llama-incremental.XXXXXX)"
build_archive="${build_context}.tar"
base_image_tag=""

cleanup() {
    if [[ -n "${base_image_tag}" ]]; then
        docker --context "${docker_context}" image rm "${base_image_tag}" >/dev/null 2>&1 || true
    fi
    case "${build_context}" in /tmp/slim-arc-llama-incremental.*) rm -rf -- "${build_context}" ;; esac
    case "${build_archive}" in /tmp/slim-arc-llama-incremental.*.tar) rm -f -- "${build_archive}" ;; esac
}
trap cleanup EXIT

head_commit="$(git -C "${repo_root}" rev-parse --verify HEAD^{commit})"
base_commit="$(docker --context "${docker_context}" run --rm "${image_tag}" \
    sh -c "sed -n 's/^SLIM_ARC_GIT_COMMIT=//p' /opt/build-manifest.env")"
if [[ ! "${head_commit}" =~ ^[0-9a-f]{40}$ || ! "${base_commit}" =~ ^[0-9a-f]{40}$ ]]; then
    printf 'Unable to resolve full source and base commits\n' >&2
    exit 1
fi
if ! git -C "${repo_root}" merge-base --is-ancestor "${base_commit}" "${head_commit}"; then
    printf 'Current image is not an ancestor of HEAD\n' >&2
    exit 1
fi
base_image_id="$(docker --context "${docker_context}" image inspect "${image_tag}" --format '{{.Id}}')"
base_image_tag="slim-arc-incremental-base:${base_commit:0:12}"
docker --context "${docker_context}" image tag "${base_image_id}" "${base_image_tag}"

context_paths=(
    scripts/macos/Dockerfile.llama.incremental
    scripts/apply-slim-arc.py
)
while IFS= read -r -d '' source_path; do
    context_paths+=("${source_path}")
done < <(git -C "${repo_root}" ls-tree -r --name-only -z "${head_commit}" -- patches/llama-upstream scripts/macos/container)

if ! git -C "${repo_root}" diff --quiet HEAD -- "${context_paths[@]}"; then
    printf 'Refusing to build from tracked context files that differ from HEAD\n' >&2
    exit 1
fi
git -C "${repo_root}" archive --format=tar --output="${build_archive}" "${head_commit}" -- "${context_paths[@]}"
tar -xf "${build_archive}" -C "${build_context}"

context_sha="$(python3 - "${build_context}" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
    content = path.read_bytes()
    relative = path.relative_to(root).as_posix().encode()
    digest.update(relative + b"\0" + str(len(content)).encode() + b"\0" + content)
print(digest.hexdigest())
PY
)"

build_args=(
    --build-arg "BASE_IMAGE=${base_image_tag}"
    --build-arg "SLIM_ARC_BASE_GIT_COMMIT=${base_commit}"
    --build-arg "SLIM_ARC_GIT_COMMIT=${head_commit}"
    --build-arg "SLIM_ARC_BUILD_CONTEXT_SHA256=${context_sha}"
)
docker --context "${docker_context}" build -f "${build_context}/scripts/macos/Dockerfile.llama.incremental" \
    --target runtime -t "${image_tag}" "${build_args[@]}" "${build_context}"
docker --context "${docker_context}" build -f "${build_context}/scripts/macos/Dockerfile.llama.incremental" \
    --target test -t "${test_image_tag}" "${build_args[@]}" "${build_context}"
docker --context "${docker_context}" image inspect "${image_tag}" --format '{{.Id}}'
