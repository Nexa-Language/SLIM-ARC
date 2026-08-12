#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${script_dir}/common.sh"

if [[ $# -ne 2 ]]; then
    printf 'usage: verify-build.sh <result-dir> <model-manifest>\n' >&2
    exit 2
fi
result_dir="$1"
model_manifest="$2"
assert_safe_result_dir "${result_dir}"
mkdir -p "${result_dir}"

profile="$(slim_arc_profile_name)"
docker_context="colima-${profile}"
image_tag="slim-arc-llama:360e134"
manifest_path="${result_dir}/build-manifest.env"

DOCKER_CONTEXT="${docker_context}" docker run --rm "${image_tag}" cat /opt/build-manifest.env >"${manifest_path}"
bash "$(slim_arc_repo_root)/tests/macos/test-build-manifest.sh" "${manifest_path}"

{
    printf 'BASELINE_VERSION\n'
    DOCKER_CONTEXT="${docker_context}" docker run --rm "${image_tag}" /opt/llama-baseline/build/bin/llama-cli --version
    printf 'PATCHED_VERSION\n'
    DOCKER_CONTEXT="${docker_context}" docker run --rm "${image_tag}" /opt/llama-patched/build/bin/llama-cli --version
    printf 'BINARY_HASHES\n'
    DOCKER_CONTEXT="${docker_context}" docker run --rm "${image_tag}" sha256sum \
        /opt/llama-baseline/build/bin/llama-cli \
        /opt/llama-baseline/build/bin/llama-bench \
        /opt/llama-patched/build/bin/llama-cli \
        /opt/llama-patched/build/bin/llama-bench
} >"${result_dir}/build-versions.txt" 2>&1

DOCKER_CONTEXT="${docker_context}" docker run --rm "${image_tag}" cat /opt/patch-apply-first.log >"${result_dir}/patch-apply.log"
grep -q 'SLIM-ARC integration complete' "${result_dir}/patch-apply.log"
DOCKER_CONTEXT="${docker_context}" docker image inspect "${image_tag}" --format '{{json .RepoTags}} {{.Id}} {{.Architecture}} {{.Os}}' >"${result_dir}/image-inspect.txt"
bash "$(slim_arc_repo_root)/tests/macos/test-variant-linkage.sh" "${image_tag}"

image_id="$(DOCKER_CONTEXT="${docker_context}" docker image inspect "${image_tag}" --format '{{.Id}}')"
if [[ ! "${image_id}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    printf 'Runtime image id is missing or malformed\n' >&2
    exit 1
fi
python3 "$(slim_arc_repo_root)/scripts/macos/write_build_evidence.py" \
    "${result_dir}" \
    --build-manifest "${manifest_path}" \
    --model-manifest "${model_manifest}" \
    --image-id "${image_id}"

cat "${manifest_path}"
