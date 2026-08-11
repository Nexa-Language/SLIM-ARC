#!/usr/bin/env bash
set -euo pipefail

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

cleanup() {
    if [[ -n "${build_context:-}" && "${build_context}" == /tmp/slim-arc-llama-build.* && -d "${build_context}" ]]; then
        rm -rf "${build_context}"
    fi
}
trap cleanup EXIT

install -d "${build_context}/scripts" "${build_context}/patches/llama-upstream"
cp "${script_dir}/Dockerfile.llama" "${build_context}/Dockerfile"
cp "${repo_root}/scripts/apply-slim-arc.py" "${build_context}/scripts/apply-slim-arc.py"
cp -R "${repo_root}/patches/llama-upstream/." "${build_context}/patches/llama-upstream/"

if find "${build_context}" -type f \( -name '*.pdf' -o -name '*.gguf' -o -name '.env' \) -print -quit | grep -q .; then
    printf 'Build context contains a forbidden artifact\n' >&2
    exit 1
fi

DOCKER_CONTEXT="${docker_context}" docker build \
    --tag "${image_tag}" \
    "${build_context}"

DOCKER_CONTEXT="${docker_context}" docker image inspect "${image_tag}" --format '{{.Id}}'
