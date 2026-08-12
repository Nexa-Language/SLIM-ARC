#!/usr/bin/env bash
set -euo pipefail

readonly expected_model_path="/models/model.gguf"
readonly result_dir="/results"

require_positive_integer() {
    local name="${1:?name is required}"
    local value="${2:-}"
    if [[ ! "${value}" =~ ^[0-9]+$ ]] || (( value <= 0 )); then
        printf '%s must be a positive integer\n' "${name}" >&2
        exit 2
    fi
}

case "${VARIANT:-}" in
    baseline)
        benchmark="/opt/llama-baseline/build/bin/llama-bench"
        runtime_library_path="/opt/llama-baseline/build/bin"
        ;;
    patched)
        benchmark="/opt/llama-patched/build/bin/llama-bench"
        runtime_library_path="/opt/llama-patched/build/bin"
        ;;
    *) printf 'VARIANT must be baseline or patched\n' >&2; exit 2 ;;
esac
export LD_LIBRARY_PATH="${runtime_library_path}"

if [[ -e /opt/slim-arc-test-enabled && "${BENCHMARK_OVERRIDE:-}" == "/opt/slim-arc-test/fake-llama-bench" ]]; then
    benchmark="${BENCHMARK_OVERRIDE}"
elif [[ -n "${BENCHMARK_OVERRIDE:-}" ]]; then
    printf 'BENCHMARK_OVERRIDE is available only in the fixed test image\n' >&2
    exit 2
fi

if [[ "${MODEL_PATH:-}" != "${expected_model_path}" || ! -f "${MODEL_PATH}" ]]; then
    printf 'MODEL_PATH must be the mounted file %s\n' "${expected_model_path}" >&2
    exit 2
fi
if ! mountpoint -q "${MODEL_PATH}"; then
    printf 'Model file must be a dedicated bind mount\n' >&2
    exit 2
fi
model_mount_options="$(findmnt --noheadings --output OPTIONS --target "${MODEL_PATH}")"
if [[ ",${model_mount_options}," != *,ro,* ]]; then
    printf 'Model bind mount must be read-only\n' >&2
    exit 2
fi
if [[ ! -d "${result_dir}" ]] || ! mountpoint -q "${result_dir}"; then
    printf '/results must be a dedicated directory mount\n' >&2
    exit 2
fi
write_probe="${result_dir}/.write-probe.$$"
if ! : >"${write_probe}"; then
    printf '/results must be writable\n' >&2
    exit 2
fi
rm -f "${write_probe}"

require_positive_integer PP "${PP:-}"
require_positive_integer TG "${TG:-}"
require_positive_integer THREADS "${THREADS:-}"
require_positive_integer REPETITIONS "${REPETITIONS:-}"

readonly allowed_slim_arc_env='^(SLIM_ARC_DECODE_MADV|SLIM_ARC_DISABLE|SLIM_ARC_DYNAMIC_MADV|SLIM_ARC_EXPERT_BUDGET|SLIM_ARC_EXPERT_CONF|SLIM_ARC_EXPERT_POP|SLIM_ARC_EXPERT_RECLAIM_WASTE|SLIM_ARC_EXPERT_RESIDENCY|SLIM_ARC_KV_EVICT|SLIM_ARC_KV_SINK|SLIM_ARC_KV_WINDOW|SLIM_ARC_NO_MADV_RANDOM|SLIM_ARC_NO_PREFETCH|SLIM_ARC_PRESSURE_ADMISSION|SLIM_ARC_PRESSURE_RESERVE_MB)$'
while IFS= read -r variable_name; do
    if [[ "${variable_name}" == SLIM_ARC_* && ! "${variable_name}" =~ ${allowed_slim_arc_env} ]]; then
        printf 'Unsupported SLIM-ARC environment variable: %s\n' "${variable_name}" >&2
        exit 2
    fi
    if [[ ( "${variable_name}" == "SLIM_ARC_EXPERT_RECLAIM_WASTE" || "${variable_name}" == "SLIM_ARC_EXPERT_RESIDENCY" ) && "${!variable_name}" != "1" ]]; then
        printf '%s must be exactly 1\n' "${variable_name}" >&2
        exit 2
    fi
done < <(compgen -e)

cgroup_relative="$(awk -F: '$1 == "0" {print $3}' /proc/self/cgroup)"
if [[ -n "${cgroup_relative}" && -f "/sys/fs/cgroup${cgroup_relative}/memory.max" ]]; then
    cgroup_dir="/sys/fs/cgroup${cgroup_relative}"
elif [[ -f /sys/fs/cgroup/memory.max ]]; then
    cgroup_dir="/sys/fs/cgroup"
else
    printf 'Unable to resolve the current cgroups v2 directory\n' >&2
    exit 1
fi
if [[ "$(cat "${cgroup_dir}/memory.max")" == "max" ]]; then
    printf 'Container memory.max must be finite\n' >&2
    exit 1
fi

capture_cgroup() {
    local output="${1:?output path is required}"
    local metric
    {
        printf 'CGROUP_RELATIVE=%s\n' "${cgroup_relative:-/}"
        for metric in \
            memory.current memory.max memory.peak memory.events memory.stat memory.swap.current memory.swap.max memory.pressure \
            cpu.max cpu.stat cpu.pressure io.stat io.pressure; do
            printf '=== %s ===\n' "${metric}"
            if [[ -f "${cgroup_dir}/${metric}" ]]; then
                cat "${cgroup_dir}/${metric}"
            else
                printf 'unsupported\n'
            fi
        done
    } >"${output}"
}

capture_cgroup "${result_dir}/cgroup-before.txt"
{
    printf 'WRAPPER_BEFORE\n'
    sed 's/[[:space:]]*$//' /proc/self/status
    printf 'SELF_CGROUP\n'
    cat /proc/self/cgroup
} >"${result_dir}/proc-status.txt"

benchmark_exit=0
runtime_log_args=()
for ((rep = 1; rep <= REPETITIONS; rep++)); do
    stdout_log="${result_dir}/rep-${rep}.stdout.log"
    stderr_log="${result_dir}/rep-${rep}.stderr.log"
    time_log="${result_dir}/rep-${rep}.time.txt"
    set +e
    /usr/bin/time -v -o "${time_log}" \
        "${benchmark}" \
        --model "${MODEL_PATH}" \
        --threads "${THREADS}" \
        --n-prompt "${PP}" \
        --n-gen "${TG}" \
        --repetitions 1 \
        --output jsonl \
        --no-warmup \
        --n-gpu-layers 0 \
        --load-mode mmap \
        --offline \
        >"${stdout_log}" 2>"${stderr_log}"
    benchmark_exit=$?
    set -e
    runtime_log_args+=(--runtime-log "${stderr_log}")
    printf '%s\n' "${benchmark_exit}" >"${result_dir}/rep-${rep}.exit-status.txt"
    if (( benchmark_exit != 0 )); then
        break
    fi
done

capture_cgroup "${result_dir}/cgroup-after.txt"
{
    printf 'WRAPPER_AFTER\n'
    sed 's/[[:space:]]*$//' /proc/self/status
} >>"${result_dir}/proc-status.txt"

outcome="success"
if (( benchmark_exit != 0 )); then
    outcome="error"
fi
printf '%s\n' "${benchmark_exit}" >"${result_dir}/wrapper-exit-status.txt"
manifest_temp="${result_dir}/.run-manifest.json.$$"
python3 /opt/slim-arc-runner/run_manifest.py \
    --variant "${VARIANT}" \
    --outcome "${outcome}" \
    --exit-code "${benchmark_exit}" \
    --cgroup-dir "${cgroup_dir}" \
    --build-manifest /opt/build-manifest.env \
    --pp "${PP}" \
    --tg "${TG}" \
    --threads "${THREADS}" \
    --repetitions "${REPETITIONS}" \
    "${runtime_log_args[@]}" \
    --output "${manifest_temp}"
mv "${manifest_temp}" "${result_dir}/run-manifest.json"
exit "${benchmark_exit}"
