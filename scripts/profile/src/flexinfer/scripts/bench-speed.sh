#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

if [ -z "${BUILD_PREFIX:-}" ]; then
    UNAME_O=$(uname -o 2>/dev/null || true)
    if [ -d "$REPO_ROOT/android" ] && { [ "$UNAME_O" = "Android" ] || [ ! -d "$REPO_ROOT/host" ]; }; then
        BUILD_PREFIX=$REPO_ROOT/android
    else
        BUILD_PREFIX=$REPO_ROOT/host
    fi
fi
LLAMA_LIBRARY_PATH=${LLAMA_LIBRARY_PATH:-"$BUILD_PREFIX/lib"}
EXEC_PATH=${EXEC_PATH:-"$BUILD_PREFIX/bin"}
MODEL_PREFIX=${MODEL_PREFIX:-"$REPO_ROOT/hf-models"}
BUILD_PREFIX=${BUILD_PREFIX%/}
LLAMA_LIBRARY_PATH=${LLAMA_LIBRARY_PATH%/}
EXEC_PATH=${EXEC_PATH%/}
MODEL_PREFIX=${MODEL_PREFIX%/}
if [ -z "${BENCH_BIN:-}" ]; then
    if [ -x "$EXEC_PATH/flexinfer-bench" ]; then
        BENCH_BIN=$EXEC_PATH/flexinfer-bench
    else
        BENCH_BIN=$EXEC_PATH/llama-bench
    fi
fi

RUN_LD_LIBRARY_PATH=$LLAMA_LIBRARY_PATH
if [ -n "${LD_LIBRARY_PATH:-}" ]; then
    RUN_LD_LIBRARY_PATH=$LLAMA_LIBRARY_PATH:$LD_LIBRARY_PATH
fi

DEFAULT_MODEL_PATH_LIST=(
    ggml-model-Llama3-Med42-8B-q4_0.gguf
    ggml-model-Llama3-Med42-70B-q4_0.gguf
    ggml-model-Llama-3.1-8B-Instruct-q4_0.gguf
    ggml-model-Llama-3.1-70B-Instruct-q4_0.gguf
    ggml-model-Mixtral-8x7B-Instruct-v0.1-q4_0.gguf
    ggml-model-Qwen2.5-3B-Instruct-q4_0.gguf
    qwen2.5-7b-instruct-q4_0.gguf
    meditron3-qwen2.5-14b-q4_0.gguf
    meditron3-qwen2.5-7b-q4_0.gguf
    ggml-model-Qwen2.5-14B-Instruct-q4_0.gguf
    ggml-model-Qwen2.5-32B-Instruct-q4_0.gguf
    ggml-model-Qwen2.5-72B-Instruct-q4_0.gguf
)
MODEL_PATH_LIST=()
if [ -n "${MODEL_LIST:-}" ]; then
    read -r -a MODEL_PATH_LIST <<< "$MODEL_LIST"
else
    MODEL_PATH_LIST=("${DEFAULT_MODEL_PATH_LIST[@]}")
fi

# Cooldown knobs for local Linux or Android benchmark runs. Override them from the
# command line, for example:
#   AM=8 TP=2 COOLDOWN_SECONDS=600 COOLDOWN_TEMP_C=42 bash scripts/bench-speed.sh
COOLDOWN_SECONDS=${COOLDOWN_SECONDS:-300}
COOLDOWN_CHECK_INTERVAL=${COOLDOWN_CHECK_INTERVAL:-10}
COOLDOWN_MAX_WAIT_SECONDS=${COOLDOWN_MAX_WAIT_SECONDS:-1800}
COOLDOWN_TEMP_C=${COOLDOWN_TEMP_C:-45}
COOLDOWN_MIN_FREQ_RATIO=${COOLDOWN_MIN_FREQ_RATIO:-95}
DROP_CACHES=${DROP_CACHES:-0}
DROP_CACHES_CMD=${DROP_CACHES_CMD:-}
TASKSET_CPUS=${TASKSET_CPUS:-}
NUMACTL_ARGS=${NUMACTL_ARGS:-}
CGROUP_SPEC=${CGROUP_SPEC:-}
RUN_PREFIX=${RUN_PREFIX:-}

P=${P:-16}
N=${N:-16}
AM=${AM:-8}
TP=${TP:-2}
T=${T:-}

RESULT_DIR=${RESULT_DIR:-"$REPO_ROOT/bench-results"}
mkdir -p "$RESULT_DIR"
BENCH_FAILED=0

is_integer() {
    case "$1" in
        ''|-) return 1 ;;
        -*) case "${1#-}" in
                ''|*[!0-9]*) return 1 ;;
                *) return 0 ;;
            esac ;;
        *[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

is_nonnegative_number() {
    case "$1" in
        ''|.*|*.*.*|*[!0-9.]*) return 1 ;;
        *.*) case "$1" in
                *[0-9].[0-9]*|[0-9]*.) return 0 ;;
                *) return 1 ;;
             esac ;;
        *) is_integer "$1" && [ "$1" -ge 0 ] ;;
    esac
}

require_nonnegative_integer() {
    local name=$1
    local value=$2

    if ! is_integer "$value" || [ "$value" -lt 0 ]; then
        echo "$name must be a non-negative integer, got: $value" >&2
        exit 1
    fi
}

require_nonnegative_number() {
    local name=$1
    local value=$2

    if ! is_nonnegative_number "$value"; then
        echo "$name must be a non-negative number, got: $value" >&2
        exit 1
    fi
}

require_positive_integer() {
    local name=$1
    local value=$2

    if ! is_integer "$value" || [ "$value" -le 0 ]; then
        echo "$name must be a positive integer, got: $value" >&2
        exit 1
    fi
}

require_percent_integer() {
    local name=$1
    local value=$2

    require_nonnegative_integer "$name" "$value"
    if [ "$value" -gt 100 ]; then
        echo "$name must be between 0 and 100, got: $value" >&2
        exit 1
    fi
}

require_bool_integer() {
    local name=$1
    local value=$2

    if [ "$value" != "0" ] && [ "$value" != "1" ]; then
        echo "$name must be 0 or 1, got: $value" >&2
        exit 1
    fi
}

normalize_temp_c() {
    local raw=$1

    if ! is_integer "$raw"; then
        return 1
    fi

    if [ "$raw" -ge 1000 ]; then
        echo $((raw / 1000))
    else
        echo "$raw"
    fi
}

require_nonnegative_integer COOLDOWN_SECONDS "$COOLDOWN_SECONDS"
require_positive_integer COOLDOWN_CHECK_INTERVAL "$COOLDOWN_CHECK_INTERVAL"
require_nonnegative_integer COOLDOWN_MAX_WAIT_SECONDS "$COOLDOWN_MAX_WAIT_SECONDS"
require_nonnegative_integer COOLDOWN_TEMP_C "$COOLDOWN_TEMP_C"
require_percent_integer COOLDOWN_MIN_FREQ_RATIO "$COOLDOWN_MIN_FREQ_RATIO"
require_bool_integer DROP_CACHES "$DROP_CACHES"
require_nonnegative_integer P "$P"
require_nonnegative_integer N "$N"
require_nonnegative_number AM "$AM"
require_nonnegative_integer TP "$TP"
if [ -n "$T" ]; then
    require_positive_integer T "$T"
fi

RUN_PREFIX_ARGS=()
if [ -n "$RUN_PREFIX" ]; then
    read -r -a RUN_PREFIX_ARGV <<< "$RUN_PREFIX"
    RUN_PREFIX_ARGS+=("${RUN_PREFIX_ARGV[@]}")
fi
if [ -n "$CGROUP_SPEC" ]; then
    if ! command -v cgexec >/dev/null 2>&1; then
        echo "CGROUP_SPEC was set, but cgexec was not found." >&2
        exit 1
    fi
    RUN_PREFIX_ARGS+=(cgexec -g "$CGROUP_SPEC")
fi
if [ -n "$NUMACTL_ARGS" ]; then
    if ! command -v numactl >/dev/null 2>&1; then
        echo "NUMACTL_ARGS was set, but numactl was not found." >&2
        exit 1
    fi
    read -r -a NUMACTL_ARGV <<< "$NUMACTL_ARGS"
    RUN_PREFIX_ARGS+=(numactl "${NUMACTL_ARGV[@]}")
fi
if [ -n "$TASKSET_CPUS" ]; then
    if ! command -v taskset >/dev/null 2>&1; then
        echo "TASKSET_CPUS was set, but taskset was not found." >&2
        exit 1
    fi
    RUN_PREFIX_ARGS+=(taskset -c "$TASKSET_CPUS")
fi

highest_thermal_temp_c() {
    local zone raw temp_c max_temp=''

    for zone in /sys/class/thermal/thermal_zone*; do
        [ -r "$zone/temp" ] || continue

        raw=$(cat "$zone/temp" 2>/dev/null)
        temp_c=$(normalize_temp_c "$raw") || continue

        # Ignore disconnected or clearly bogus sensors.
        if [ "$temp_c" -le 0 ] || [ "$temp_c" -ge 125 ]; then
            continue
        fi

        if [ -z "$max_temp" ] || [ "$temp_c" -gt "$max_temp" ]; then
            max_temp=$temp_c
        fi
    done

    echo "$max_temp"
}

lowest_freq_ratio_pct() {
    local policy scaling_max cpuinfo_max ratio min_ratio=''

    for policy in /sys/devices/system/cpu/cpufreq/policy*; do
        [ -r "$policy/scaling_max_freq" ] || continue
        [ -r "$policy/cpuinfo_max_freq" ] || continue

        scaling_max=$(cat "$policy/scaling_max_freq" 2>/dev/null)
        cpuinfo_max=$(cat "$policy/cpuinfo_max_freq" 2>/dev/null)

        is_integer "$scaling_max" || continue
        is_integer "$cpuinfo_max" || continue
        [ "$cpuinfo_max" -gt 0 ] || continue

        ratio=$((scaling_max * 100 / cpuinfo_max))
        if [ -z "$min_ratio" ] || [ "$ratio" -lt "$min_ratio" ]; then
            min_ratio=$ratio
        fi
    done

    echo "$min_ratio"
}

print_current_frequency() {
    local policy cur_freq scaling_max cpuinfo_max out=''

    for policy in /sys/devices/system/cpu/cpufreq/policy*; do
        [ -d "$policy" ] || continue

        cur_freq=unknown
        scaling_max=unknown
        cpuinfo_max=unknown
        [ -r "$policy/scaling_cur_freq" ] && cur_freq=$(cat "$policy/scaling_cur_freq" 2>/dev/null)
        [ -r "$policy/scaling_max_freq" ] && scaling_max=$(cat "$policy/scaling_max_freq" 2>/dev/null)
        [ -r "$policy/cpuinfo_max_freq" ] && cpuinfo_max=$(cat "$policy/cpuinfo_max_freq" 2>/dev/null)

        out="${out}$(basename "$policy") cur=${cur_freq} max=${scaling_max} hw_max=${cpuinfo_max}; "
    done

    if [ -n "$out" ]; then
        echo "Current frequency: $out"
    else
        echo "Current frequency: unknown"
    fi
}

log_system_state() {
    local label=$1
    local out_file=$2
    local zone type raw temp_c normalized policy governor cur_freq scaling_min scaling_max cpuinfo_max

    {
        echo
        echo "===== $label ====="
        date '+%Y-%m-%d %H:%M:%S %z' 2>/dev/null || date
        echo "cooldown: seconds=${COOLDOWN_SECONDS}, check_interval=${COOLDOWN_CHECK_INTERVAL}, max_wait=${COOLDOWN_MAX_WAIT_SECONDS}, temp_limit_c=${COOLDOWN_TEMP_C}, min_freq_ratio_pct=${COOLDOWN_MIN_FREQ_RATIO}"
        echo "bench: p=${P}, n=${N}, t=${T:-default}, am=${AM}, tp=${TP}"
        echo "run_control: drop_caches=${DROP_CACHES}, taskset_cpus=${TASKSET_CPUS:-unset}, numactl_args=${NUMACTL_ARGS:-unset}, cgroup_spec=${CGROUP_SPEC:-unset}, run_prefix=${RUN_PREFIX:-unset}"

        echo "thermal:"
        for zone in /sys/class/thermal/thermal_zone*; do
            [ -d "$zone" ] || continue

            type=unknown
            raw=unreadable
            temp_c=unknown
            [ -r "$zone/type" ] && type=$(cat "$zone/type" 2>/dev/null)
            [ -r "$zone/temp" ] && raw=$(cat "$zone/temp" 2>/dev/null)
            if normalized=$(normalize_temp_c "$raw" 2>/dev/null); then
                temp_c=$normalized
            fi

            echo "  $(basename "$zone"): type=${type}, temp_c=${temp_c}, raw=${raw}"
        done

        echo "cpufreq:"
        for policy in /sys/devices/system/cpu/cpufreq/policy*; do
            [ -d "$policy" ] || continue

            governor=unknown
            cur_freq=unknown
            scaling_min=unknown
            scaling_max=unknown
            cpuinfo_max=unknown
            [ -r "$policy/scaling_governor" ] && governor=$(cat "$policy/scaling_governor" 2>/dev/null)
            [ -r "$policy/scaling_cur_freq" ] && cur_freq=$(cat "$policy/scaling_cur_freq" 2>/dev/null)
            [ -r "$policy/scaling_min_freq" ] && scaling_min=$(cat "$policy/scaling_min_freq" 2>/dev/null)
            [ -r "$policy/scaling_max_freq" ] && scaling_max=$(cat "$policy/scaling_max_freq" 2>/dev/null)
            [ -r "$policy/cpuinfo_max_freq" ] && cpuinfo_max=$(cat "$policy/cpuinfo_max_freq" 2>/dev/null)

            echo "  $(basename "$policy"): governor=${governor}, cur=${cur_freq}, min=${scaling_min}, max=${scaling_max}, hw_max=${cpuinfo_max}"
        done
    } >> "$out_file"
}

wait_for_cooldown() {
    local state_file=$1
    local waited=0
    local temp_c freq_ratio need_wait

    log_system_state "before cooldown" "$state_file"

    if [ "$COOLDOWN_SECONDS" -gt 0 ]; then
        sleep "$COOLDOWN_SECONDS"
        waited=$((waited + COOLDOWN_SECONDS))
    fi

    while [ "$waited" -lt "$COOLDOWN_MAX_WAIT_SECONDS" ]; do
        need_wait=0
        temp_c=$(highest_thermal_temp_c)
        freq_ratio=$(lowest_freq_ratio_pct)

        if [ -n "$temp_c" ] && [ "$temp_c" -gt "$COOLDOWN_TEMP_C" ]; then
            need_wait=1
        fi

        if [ -n "$freq_ratio" ] && [ "$freq_ratio" -lt "$COOLDOWN_MIN_FREQ_RATIO" ]; then
            need_wait=1
        fi

        if [ "$need_wait" -eq 0 ]; then
            break
        fi

        sleep "$COOLDOWN_CHECK_INTERVAL"
        waited=$((waited + COOLDOWN_CHECK_INTERVAL))
    done

    if [ "$waited" -ge "$COOLDOWN_MAX_WAIT_SECONDS" ]; then
        echo "Cooldown max wait reached; running anyway." >> "$state_file"
    fi

    log_system_state "before benchmark" "$state_file"
    print_current_frequency >> "$state_file"
}

drop_page_cache() {
    local state_file=$1

    if [ "$DROP_CACHES" -eq 0 ]; then
        return 0
    fi

    {
        echo
        echo "===== cache control ====="
        date '+%Y-%m-%d %H:%M:%S %z' 2>/dev/null || date
    } >> "$state_file"

    if [ -n "$DROP_CACHES_CMD" ]; then
        if sh -c "$DROP_CACHES_CMD" >> "$state_file" 2>&1; then
            echo "drop_caches: custom command succeeded" >> "$state_file"
            return 0
        fi
        echo "drop_caches: custom command failed" >> "$state_file"
        return 1
    fi

    if [ -w /proc/sys/vm/drop_caches ]; then
        sync
        if echo 3 > /proc/sys/vm/drop_caches 2>> "$state_file"; then
            echo "drop_caches: wrote 3 to /proc/sys/vm/drop_caches" >> "$state_file"
            return 0
        fi
    elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        if sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' >> "$state_file" 2>&1; then
            echo "drop_caches: sudo command succeeded" >> "$state_file"
            return 0
        fi
    fi

    echo "drop_caches: requested, but no non-interactive method is available" >> "$state_file"
    echo "Set DROP_CACHES_CMD to a device-specific command, for example a rooted Android su command." >> "$state_file"
    return 1
}

build_bench_command() {
    local model_file=$1

    BENCH_CMD=("$BENCH_BIN" -m "$model_file" -p "$P" -n "$N")
    if [ -n "$T" ]; then
        BENCH_CMD+=(-t "$T")
    fi
    case "$(basename "$BENCH_BIN")" in
        flexinfer-bench|*prefetch*)
            BENCH_CMD+=(-am "$AM" -tp "$TP")
            ;;
    esac
}

print_shell_command() {
    printf "LD_LIBRARY_PATH=%q" "$RUN_LD_LIBRARY_PATH"
    if [ "${#RUN_PREFIX_ARGS[@]}" -gt 0 ]; then
        printf " %q" "${RUN_PREFIX_ARGS[@]}"
    fi
    printf " %q" "${BENCH_CMD[@]}"
    printf "\n"
}

if [ ! -x "$BENCH_BIN" ]; then
    echo "Benchmark binary does not exist or is not executable: $BENCH_BIN" >&2
    echo "Run bash build-host.sh or bash build-android.sh first, or set BENCH_BIN/EXEC_PATH/LLAMA_LIBRARY_PATH explicitly." >&2
    exit 1
fi

if [ ! -d "$LLAMA_LIBRARY_PATH" ]; then
    echo "Library directory does not exist: $LLAMA_LIBRARY_PATH" >&2
    echo "Run bash build-host.sh or bash build-android.sh first, or set LLAMA_LIBRARY_PATH explicitly." >&2
    exit 1
fi

for MODEL in "${MODEL_PATH_LIST[@]}"
do
    MODEL_FILE=$MODEL_PREFIX/$MODEL
    MODEL_OUTPUT_NAME=$(basename "${MODEL%.gguf}")
    PARAM_TAG=p${P}_n${N}
    if [ -n "$T" ]; then
        PARAM_TAG=${PARAM_TAG}_t${T}
    fi
    PARAM_TAG=${PARAM_TAG}_am${AM}_tp${TP}
    RESULT_FILE=$RESULT_DIR/${MODEL_OUTPUT_NAME}.${PARAM_TAG}.txt
    if [ -f "$MODEL_FILE" ]; then
        echo "Running benchmark: model=${MODEL}, p=${P}, n=${N}, t=${T:-default}, am=${AM}, tp=${TP}, output=${RESULT_FILE}"
        : > "$RESULT_FILE"
        {
            echo "model: ${MODEL}"
            echo "model_file: ${MODEL_FILE}"
            echo "result_file: ${RESULT_FILE}"
            echo "params: p=${P}, n=${N}, t=${T:-default}, am=${AM}, tp=${TP}"
            echo "bench_bin: ${BENCH_BIN}"
            echo "run_control: drop_caches=${DROP_CACHES}, taskset_cpus=${TASKSET_CPUS:-unset}, numactl_args=${NUMACTL_ARGS:-unset}, cgroup_spec=${CGROUP_SPEC:-unset}, run_prefix=${RUN_PREFIX:-unset}"
        } >> "$RESULT_FILE"
        wait_for_cooldown "$RESULT_FILE"
        if ! drop_page_cache "$RESULT_FILE"; then
            echo "Cache drop failed, output=${RESULT_FILE}"
            BENCH_FAILED=1
            continue
        fi
        build_bench_command "$MODEL_FILE"
        {
            echo
            echo "===== benchmark command ====="
            print_shell_command
            echo
            echo "===== benchmark output ====="
        } >> "$RESULT_FILE"
        LD_LIBRARY_PATH=$RUN_LD_LIBRARY_PATH "${RUN_PREFIX_ARGS[@]}" "${BENCH_CMD[@]}" >> "$RESULT_FILE" 2>&1
        bench_status=$?
        {
            echo
            echo "benchmark_exit_status=$bench_status"
        } >> "$RESULT_FILE"
        log_system_state "after benchmark" "$RESULT_FILE"
        if [ "$bench_status" -ne 0 ]; then
            echo "Benchmark failed (exit status: $bench_status), output=${RESULT_FILE}"
            if [ "$bench_status" -gt 128 ]; then
                echo "Terminated by signal: $((bench_status - 128))"
            fi
            if [ "$bench_status" -eq 139 ]; then
                echo "Exit status 139 means segmentation fault."
            fi
            echo "Last output lines:"
            tail -n 40 "$RESULT_FILE"
            BENCH_FAILED=1
        fi
    fi
done

exit "$BENCH_FAILED"
