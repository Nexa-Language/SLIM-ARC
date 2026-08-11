#!/usr/bin/env bash
set -euo pipefail

readonly image="${1:-slim-arc-llama:360e134}"
readonly docker_context="${DOCKER_CONTEXT:-colima-slim-arc}"

assert_variant_linkage() {
    local variant="${1:?variant is required}"
    local other="baseline"
    if [[ "${variant}" == "baseline" ]]; then
        other="patched"
    fi
    local output
    output="$(docker --context "${docker_context}" run --rm "${image}" \
        ldd "/opt/llama-${variant}/build/bin/llama-bench")"
    grep -q "/opt/llama-${variant}/build/bin/libllama.so" <<<"${output}"
    if grep -q "/opt/llama-${other}/build/bin/libllama" <<<"${output}"; then
        printf '%s executable resolved %s libraries\n' "${variant}" "${other}" >&2
        exit 1
    fi
}

assert_variant_linkage baseline
assert_variant_linkage patched
