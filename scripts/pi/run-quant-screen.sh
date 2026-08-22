#!/usr/bin/env bash

set -uo pipefail

readonly SWAP_UNIT="dev-zram0.swap"
readonly SETUP_UNIT="systemd-zram-setup@zram0.service"
readonly BENCHMARK="${SLIM_ARC_PI_BENCHMARK:?Set SLIM_ARC_PI_BENCHMARK to llama-bench}"
readonly MODEL="${SLIM_ARC_PI_MODEL:-}"
readonly MODEL_SHA256="${SLIM_ARC_PI_MODEL_SHA256:-}"
readonly LABEL="${SLIM_ARC_PI_LABEL:-}"
readonly RESULT_ROOT="${SLIM_ARC_PI_RESULT_ROOT:-}"
readonly RESULT_OWNER="${SLIM_ARC_PI_RESULT_OWNER:-yituodabian:yituodabian}"
readonly PP="${SLIM_ARC_PI_PP:-4}"
readonly TG="${SLIM_ARC_PI_TG:-1}"
readonly TOP_K="${SLIM_ARC_PI_TOP_K:-10}"
readonly TIMEOUT_SECONDS="${SLIM_ARC_PI_TIMEOUT_SECONDS:-1800}"
readonly RUNTIME_LIB_DIR="${SLIM_ARC_PI_RUNTIME_LIB_DIR:-$(dirname "${BENCHMARK}")}"

swap_is_active() {
    [[ -n "$(tail -n +2 /proc/swaps)" ]]
}

restore_swap() {
    systemctl unmask --runtime "${SWAP_UNIT}" >/dev/null 2>&1 || true
    if swap_is_active; then
        return 0
    fi
    systemctl stop "${SETUP_UNIT}" >/dev/null 2>&1 || true
    if [[ -e /dev/zram0 ]]; then
        /usr/sbin/zramctl --reset /dev/zram0 || return 1
    fi
    [[ "$(/usr/sbin/zramctl --find)" == "/dev/zram0" ]] || return 1
    systemctl reset-failed "${SETUP_UNIT}" "${SWAP_UNIT}" >/dev/null 2>&1 || true
    systemctl daemon-reload
    systemctl start "${SETUP_UNIT}"
    systemctl start "${SWAP_UNIT}"
    swap_is_active
}

disable_swap() {
    systemctl unmask --runtime "${SWAP_UNIT}" >/dev/null 2>&1 || true
    systemctl stop "${SWAP_UNIT}"
    systemctl mask --runtime "${SWAP_UNIT}"
    sleep 2
    ! swap_is_active
}

record_contract() {
    {
        printf 'label=%s\n' "${LABEL}"
        printf 'model=%s\n' "${MODEL}"
        printf 'model_bytes=%s\n' "$(stat -c %s "${MODEL}")"
        printf 'model_sha256=%s\n' "${MODEL_SHA256}"
        printf 'pp=%s\n' "${PP}"
        printf 'tg=%s\n' "${TG}"
        printf 'threads=4\n'
        printf 'top_k=%s\n' "${TOP_K}"
        printf 'swap=off\n'
        printf 'cache=cold\n'
        printf 'SLIM_ARC_NO_EXPERT_PREFETCH=1\n'
        printf 'SLIM_ARC_NO_WEIGHT_PREFETCH=1\n'
        printf 'SLIM_ARC_EXPERT_HOT_MB=512\n'
        printf 'SLIM_ARC_EXPERT_HOT_LRU=1\n'
        printf 'SLIM_ARC_SHARED_MLOCK=1\n'
        printf 'SLIM_ARC_TOTAL_BUDGET_MB=16\n'
    } > "${RESULT_ROOT}/configuration.env"
    uname -a > "${RESULT_ROOT}/uname.txt"
    findmnt -T "${MODEL}" > "${RESULT_ROOT}/model-mount.txt"
    cat /sys/block/sda/queue/read_ahead_kb > "${RESULT_ROOT}/read-ahead-kb.txt"
    cat /sys/block/sda/queue/nr_requests > "${RESULT_ROOT}/nr-requests.txt"
}

record_snapshot() {
    local suffix="$1"
    free -b > "${RESULT_ROOT}/memory-${suffix}.txt"
    cat /proc/swaps > "${RESULT_ROOT}/swaps-${suffix}.txt"
    cat /proc/vmstat > "${RESULT_ROOT}/vmstat-${suffix}.txt"
    cat /proc/diskstats > "${RESULT_ROOT}/diskstats-${suffix}.txt"
    vcgencmd measure_temp > "${RESULT_ROOT}/temp-${suffix}.txt"
}

run_benchmark() {
    local start end rc
    sync
    echo 3 > /proc/sys/vm/drop_caches
    sleep 2
    record_snapshot before
    start="$(date +%s)"
    timeout "${TIMEOUT_SECONDS}" env \
        "LD_LIBRARY_PATH=$(dirname "${BENCHMARK}"):${RUNTIME_LIB_DIR}" \
        "SLIM_ARC_EXPERT_TOP_K=${TOP_K}" \
        SLIM_ARC_SLOW_STORAGE=1 \
        SLIM_ARC_INLINE_ROUTER=1 \
        SLIM_ARC_EXPERT_PIPELINE_MB=32 \
        SLIM_ARC_EXPERT_CONF=0 \
        SLIM_ARC_NO_EXPERT_PREFETCH=1 \
        SLIM_ARC_NO_WEIGHT_PREFETCH=1 \
        SLIM_ARC_EXPERT_HOT_MB=512 \
        SLIM_ARC_EXPERT_HOT_LRU=1 \
        SLIM_ARC_SHARED_MLOCK=1 \
        SLIM_ARC_TOTAL_BUDGET_MB=16 \
        "${BENCHMARK}" -m "${MODEL}" -t 4 -p "${PP}" -n "${TG}" -r 1 \
        --no-warmup -ctk q4_0 -ctv q4_0 -fa auto -o jsonl \
        > "${RESULT_ROOT}/stdout.jsonl" 2> "${RESULT_ROOT}/stderr.log"
    rc=$?
    end="$(date +%s)"
    printf '%s\n' "${rc}" > "${RESULT_ROOT}/exit-status.txt"
    printf '%s\n' "$((end - start))" > "${RESULT_ROOT}/wall-seconds.txt"
    record_snapshot after
    return "${rc}"
}

validate_inputs() {
    [[ "${EUID}" -eq 0 ]] || { echo 'run as root' >&2; return 2; }
    [[ -n "${MODEL}" && -r "${MODEL}" ]] || { echo "missing model: ${MODEL}" >&2; return 2; }
    [[ "${MODEL_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
        echo 'SLIM_ARC_PI_MODEL_SHA256 must be a lowercase SHA-256 digest' >&2
        return 2
    }
    [[ -n "${LABEL}" ]] || { echo 'SLIM_ARC_PI_LABEL is required' >&2; return 2; }
    [[ -n "${RESULT_ROOT}" && ! -e "${RESULT_ROOT}" ]] || {
        echo "result root is empty or exists: ${RESULT_ROOT}" >&2
        return 2
    }
    [[ -x "${BENCHMARK}" ]] || { echo "missing benchmark: ${BENCHMARK}" >&2; return 2; }
    [[ "${PP}" =~ ^[1-9][0-9]*$ && "${TG}" =~ ^[1-9][0-9]*$ ]] || return 2
    [[ "${TOP_K}" =~ ^[1-9][0-9]*$ && "${TOP_K}" -le 10 ]] || return 2
    ! pgrep -x llama-bench >/dev/null || { echo 'llama-bench already running' >&2; return 2; }
}

main() {
    validate_inputs || return
    mkdir -p "${RESULT_ROOT}"
    trap 'restore_swap || true' EXIT HUP INT TERM
    disable_swap || { echo 'failed to hold swap disabled' >&2; return 3; }
    record_contract
    run_benchmark
    local rc=$?
    chown -R "${RESULT_OWNER}" "${RESULT_ROOT}"
    restore_swap
    trap - EXIT HUP INT TERM
    printf 'label=%s exit=%s wall=%s\n' "${LABEL}" "${rc}" "$(cat "${RESULT_ROOT}/wall-seconds.txt")"
    return "${rc}"
}

main "$@"
