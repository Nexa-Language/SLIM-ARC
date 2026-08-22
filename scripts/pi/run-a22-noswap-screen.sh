#!/usr/bin/env bash

set -uo pipefail

readonly SWAP_UNIT="dev-zram0.swap"
readonly SETUP_UNIT="systemd-zram-setup@zram0.service"
readonly BENCHMARK="${SLIM_ARC_PI_BENCHMARK:?Set SLIM_ARC_PI_BENCHMARK to llama-bench}"
readonly MODEL="${SLIM_ARC_PI_MODEL:?Set SLIM_ARC_PI_MODEL to the GGUF path}"
readonly RESULT_ROOT="${SLIM_ARC_PI_RESULT_ROOT:?Set SLIM_ARC_PI_RESULT_ROOT to an output directory}"
readonly RESULT_OWNER="${SLIM_ARC_PI_RESULT_OWNER:-yituodabian:yituodabian}"
readonly PP="${SLIM_ARC_PI_PP:-16}"
readonly TG="${SLIM_ARC_PI_TG:-4}"
readonly TIMEOUT_SECONDS="${SLIM_ARC_PI_TIMEOUT_SECONDS:-1800}"
readonly CASES="${SLIM_ARC_PI_CASES:-control,top8,top10,top16}"

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

record_case_metadata() {
    local result="$1"
    local name="$2"
    local gate="$3"
    local topk="$4"

    {
        printf 'name=%s\n' "${name}"
        printf 'cross_layer_gate=%s\n' "${gate}"
        printf 'cross_layer_topk=%s\n' "${topk}"
        printf 'pp=%s\n' "${PP}"
        printf 'tg=%s\n' "${TG}"
        printf 'threads=4\n'
        printf 'swap=off\n'
        printf 'cache=cold\n'
    } > "${result}/configuration.env"
}

run_case() {
    local name="$1"
    local gate="$2"
    local topk="$3"
    local result="${RESULT_ROOT}/${name}"
    local start end rc

    mkdir -p "${result}"
    record_case_metadata "${result}" "${name}" "${gate}" "${topk}"
    sync
    echo 3 > /proc/sys/vm/drop_caches
    sleep 2
    free -b > "${result}/memory-before.txt"
    cat /proc/swaps > "${result}/swaps-before.txt"
    vcgencmd measure_temp > "${result}/temp-before.txt"

    start="$(date +%s)"
    timeout "${TIMEOUT_SECONDS}" env \
        "LD_LIBRARY_PATH=$(dirname "${BENCHMARK}")" \
        SLIM_ARC_SLOW_STORAGE=1 \
        SLIM_ARC_INLINE_ROUTER=1 \
        SLIM_ARC_EXPERT_PIPELINE_MB=32 \
        SLIM_ARC_EXPERT_CONF=0 \
        "SLIM_ARC_CROSS_LAYER_GATE=${gate}" \
        "SLIM_ARC_CROSS_LAYER_TOPK=${topk}" \
        SLIM_ARC_PREFILL_THREADS=4 \
        SLIM_ARC_DECODE_THREADS=4 \
        "${BENCHMARK}" -m "${MODEL}" -t 4 -p "${PP}" -n "${TG}" -r 1 \
        --no-warmup -ctk q4_0 -ctv q4_0 -fa auto -o jsonl \
        > "${result}/stdout.jsonl" 2> "${result}/stderr.log"
    rc=$?
    end="$(date +%s)"

    printf '%s\n' "${rc}" > "${result}/exit-status.txt"
    printf '%s\n' "$((end - start))" > "${result}/wall-seconds.txt"
    free -b > "${result}/memory-after.txt"
    cat /proc/swaps > "${result}/swaps-after.txt"
    vcgencmd measure_temp > "${result}/temp-after.txt"
    printf 'case=%s exit=%s wall=%s\n' "${name}" "${rc}" "$((end - start))"

    [[ "${rc}" -eq 0 ]] || return "${rc}"
    ! swap_is_active
}

run_requested_cases() {
    local name
    local -a requested

    IFS=',' read -r -a requested <<< "${CASES}"
    for name in "${requested[@]}"; do
        case "${name}" in
            control) run_case control 0 10 || return ;;
            top1) run_case top1 1 1 || return ;;
            top2) run_case top2 1 2 || return ;;
            top4) run_case top4 1 4 || return ;;
            top8) run_case top8 1 8 || return ;;
            top10) run_case top10 1 10 || return ;;
            top16) run_case top16 1 16 || return ;;
            *) echo "unknown case: ${name}" >&2; return 2 ;;
        esac
    done
}

main() {
    [[ "${EUID}" -eq 0 ]] || { echo 'run as root' >&2; return 2; }
    if [[ "${1:-}" == "--restore-only" ]]; then
        restore_swap
        return
    fi

    [[ -x "${BENCHMARK}" ]] || { echo "missing benchmark: ${BENCHMARK}" >&2; return 2; }
    [[ -r "${MODEL}" ]] || { echo "missing model: ${MODEL}" >&2; return 2; }
    [[ ! -e "${RESULT_ROOT}" ]] || { echo "result root exists: ${RESULT_ROOT}" >&2; return 2; }
    ! pgrep -x llama-bench >/dev/null || { echo 'llama-bench already running' >&2; return 2; }

    mkdir -p "${RESULT_ROOT}"
    trap 'restore_swap || true' EXIT HUP INT TERM
    disable_swap || { echo 'failed to hold swap disabled' >&2; return 3; }
    run_requested_cases || return
    chown -R "${RESULT_OWNER}" "${RESULT_ROOT}"
    restore_swap
    trap - EXIT HUP INT TERM
}

main "$@"
