#!/usr/bin/env bash
set -euo pipefail

readonly image="${1:-slim-arc-llama-test:360e134}"
readonly docker_context="${DOCKER_CONTEXT:-colima-slim-arc}"
readonly repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! docker --context "${docker_context}" image inspect "${image}" >/dev/null 2>&1; then
    if [[ "${SLIM_ARC_REQUIRE_TEST_IMAGE:-}" == "1" ]]; then
        printf 'Required test image is unavailable: %s\n' "${image}" >&2
        exit 1
    fi
    printf 'SKIP: test image is unavailable (not a pass): %s\n' "${image}"
    exit 0
fi
image_id="$(docker --context "${docker_context}" image inspect "${image}" --format '{{.Id}}')"
if [[ ! "${image_id}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    printf 'Image did not resolve to an immutable SHA-256 identity: %s\n' "${image_id}" >&2
    exit 1
fi

work_dir="$(mktemp -d "${repo_root}/.runtime-metrics-smoke.XXXXXX")"
cleanup() {
    local exit_status=$?
    if [[ -n "${SLIM_ARC_SMOKE_ARTIFACT_DIR:-}" ]]; then
        mkdir -p "${SLIM_ARC_SMOKE_ARTIFACT_DIR}"
        cp -R "${work_dir}/." "${SLIM_ARC_SMOKE_ARTIFACT_DIR}/"
    fi
    rm -rf "${work_dir}"
    return "${exit_status}"
}
trap cleanup EXIT

fixture_model="${work_dir}/fixture-model.gguf"
printf 'SLIM-ARC test fixture\n' >"${fixture_model}"

run_container() {
    local case_name="${1:?case name is required}"
    shift
    local case_dir="${work_dir}/${case_name}"
    local result_dir="${case_dir}/results"
    local stdout_log="${case_dir}/stdout.log"
    local stderr_log="${case_dir}/stderr.log"
    local exit_status
    mkdir -p "${result_dir}"

    set +e
    docker --context "${docker_context}" run --rm \
        --memory 1g \
        --memory-swap 1g \
        --cpus 1 \
        --env VARIANT=patched \
        --env MODEL_PATH=/models/model.gguf \
        --env PP=4 \
        --env TG=1 \
        --env THREADS=1 \
        --env REPETITIONS=1 \
        --env "RUN_IMAGE_ID=${image_id}" \
        --env BENCHMARK_OVERRIDE=/opt/slim-arc-test/fake-llama-bench \
        "$@" \
        --mount "type=bind,source=${fixture_model},target=/models/model.gguf,readonly" \
        --mount "type=bind,source=${result_dir},target=/results" \
        "${image}" /usr/local/bin/slim-arc-run-benchmark \
        >"${stdout_log}" 2>"${stderr_log}"
    exit_status=$?
    set -e
    printf '%s\n' "${exit_status}" >"${case_dir}/exit-status.txt"
    return "${exit_status}"
}

assert_rejected() {
    local case_name="${1:?case name is required}"
    local expected_error="${2:?expected error is required}"
    shift 2
    local exit_status=0

    run_container "${case_name}" "$@" || exit_status=$?
    if (( exit_status != 2 )); then
        printf '%s expected exit 2, got %s\n' "${case_name}" "${exit_status}" >&2
        cat "${work_dir}/${case_name}/stderr.log" >&2
        exit 1
    fi
    if ! grep -Fqx "${expected_error}" "${work_dir}/${case_name}/stderr.log"; then
        printf '%s did not emit the expected runner rejection\n' "${case_name}" >&2
        cat "${work_dir}/${case_name}/stderr.log" >&2
        exit 1
    fi
}

assert_rejected unknown-slim-arc \
    'Unsupported SLIM-ARC environment variable: SLIM_ARC_UNKNOWN' \
    --env SLIM_ARC_UNKNOWN=1

for policy_name in SLIM_ARC_EXPERT_RECLAIM_WASTE SLIM_ARC_EXPERT_RESIDENCY SLIM_ARC_SLOW_STORAGE; do
    for policy_value in 0 01 2 true ''; do
        case_name="${policy_name}-${policy_value:-empty}"
        assert_rejected "${case_name}" "${policy_name} must be exactly 1" \
            --env "${policy_name}=${policy_value}"
    done
done

valid_exit_status=0
run_container valid-finalist-policies \
    --env SLIM_ARC_EXPERT_RECLAIM_WASTE=1 \
    --env SLIM_ARC_EXPERT_RESIDENCY=1 || valid_exit_status=$?
if (( valid_exit_status != 0 )); then
    printf 'valid-finalist-policies expected exit 0, got %s\n' "${valid_exit_status}" >&2
    cat "${work_dir}/valid-finalist-policies/stderr.log" >&2
    exit 1
fi

python3 - "${work_dir}/valid-finalist-policies/results/run-manifest.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert manifest["schema_version"] == 1
assert len(manifest["runtime_metrics"]) == 1
assert manifest["runtime_metrics"][0]["schema"] == 2
assert manifest["runtime_metrics_summary"]["expert_samples"] == 0
assert manifest["memory_swap_limit_bytes"] == 0
assert manifest["image_id"].startswith("sha256:")
assert manifest["workload_contract"] == {
    "seed": 1,
    "seed_source": "implicit_c_rand_default",
    "context_tokens": 5,
    "n_prompt": 4,
    "n_gen": 1,
    "n_depth": 0,
    "threads": 1,
    "no_warmup": True,
    "load_mode": "mmap",
    "offline": True,
}
PY
