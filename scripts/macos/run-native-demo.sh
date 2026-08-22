#!/usr/bin/env bash

set -euo pipefail

readonly repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
readonly llama_root="${SLIM_ARC_LLAMA_ROOT:-$repo_root/src/llama-upstream}"
readonly server_bin="${SLIM_ARC_SERVER_BIN:-$llama_root/build/bin/llama-server}"
readonly q4_model="${SLIM_ARC_BASELINE_MODEL:-${SLIM_ARC_MODEL:-$repo_root/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf}}"
readonly iq2_model="${SLIM_ARC_OPTIMIZED_MODEL:-${SLIM_ARC_MODEL:-$repo_root/data/models/Qwen3-Next-80B-A3B-Instruct-IQ2_M-SLIM-ARC.gguf}}"
readonly state_dir="${SLIM_ARC_STATE_DIR:-${TMPDIR:-/tmp}/slim-arc-native-demo}"
readonly pid_file="$state_dir/llama-server.pid"
readonly harness_pid_file="$state_dir/deepseek-harness.pid"
readonly port=18080
readonly server_label=org.slimarc.demo.server
readonly harness_label=org.slimarc.demo.harness
readonly launch_domain="gui/$(id -u)"

usage() {
    cat <<'EOF'
Usage:
  scripts/macos/run-native-demo.sh optimized [llama|harness]
  scripts/macos/run-native-demo.sh cpu-iq2  [llama|harness]
  scripts/macos/run-native-demo.sh baseline  [llama|harness]
  scripts/macos/run-native-demo.sh stop
  scripts/macos/run-native-demo.sh status

optimized: SLIM-ARC IQ2_M + full Metal, measured 46.21 token/s on tg256
cpu-iq2:   same IQ2_M weights, CPU-only and 1 thread, measured 4.96 token/s
baseline:  official Q4_K_M, background CPU-only and 1 thread, about 1 token/s
llama:     open llama.cpp's built-in chat page at http://127.0.0.1:18080/
harness:   also start DeepSeek Harness at http://127.0.0.1:3080/

Environment:
  SLIM_ARC_LLAMA_ROOT       patched llama.cpp checkout
  SLIM_ARC_SERVER_BIN       optional explicit llama-server path
  SLIM_ARC_MODEL            model used by both profiles unless overridden
  SLIM_ARC_BASELINE_MODEL   baseline Q4_K_M model
  SLIM_ARC_OPTIMIZED_MODEL  optimized IQ2_M model
  SLIM_ARC_HARNESS_ROOT     optional DeepSeek Harness checkout
  SLIM_ARC_HARNESS_PATCH    optional Harness patch file
  SLIM_ARC_STATE_DIR        runtime logs and pid files (default: system temp)
EOF
}

stop_pid_file() {
    local file=$1
    if [[ ! -f "$file" ]]; then
        return
    fi
    local pid
    pid=$(<"$file")
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid"
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.25
        done
    fi
    rm -f "$file"
}

service_pid() {
    local label=$1
    launchctl print "$launch_domain/$label" 2>/dev/null |
        awk '$1 == "pid" && $2 == "=" { print $3; exit }'
}

stop_service() {
    local label=$1
    local file=$2
    local pid=""
    pid=$(service_pid "$label" || true)
    launchctl remove "$label" 2>/dev/null || true
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.25
        done
    fi
    stop_pid_file "$file"
}

stop_all() {
    stop_service "$harness_label" "$harness_pid_file"
    stop_service "$server_label" "$pid_file"
}

status() {
    curl -fsS "http://127.0.0.1:$port/health" 2>/dev/null || true
    echo
    [[ -f "$pid_file" ]] && echo "llama-server pid: $(<"$pid_file")"
    [[ -f "$harness_pid_file" ]] && echo "DeepSeek Harness pid: $(<"$harness_pid_file")"
}

start_harness() {
    local harness_root=${SLIM_ARC_HARNESS_ROOT:-}
    local overlay=${SLIM_ARC_HARNESS_PATCH:-}
    local node_bin
    node_bin=$(command -v node)
    if [[ -z "$harness_root" ]]; then
        echo "Set SLIM_ARC_HARNESS_ROOT to use the Harness surface." >&2
        return 1
    fi
    if [[ ! -f "$harness_root/apps/cli/lib/bin.js" ]]; then
        echo "DeepSeek Harness build not found: $harness_root/apps/cli/lib/bin.js" >&2
        return 1
    fi
    if [[ -n "$overlay" && ! -f "$overlay" ]]; then
        echo "Harness patch not found: $overlay" >&2
        return 1
    fi
    local harness_args=(--profile web --port 3080)
    [[ -z "$overlay" ]] || harness_args+=(--patch "$overlay")
    stop_service "$harness_label" "$harness_pid_file"
    launchctl submit -l "$harness_label" \
        -o "$state_dir/deepseek-harness.stdout.log" \
        -e "$state_dir/deepseek-harness.log" -- \
        /bin/zsh -lc 'cd "$1" && shift && exec "$@"' slim-arc-harness \
        "$harness_root" /usr/bin/env \
        SLIM_ARC_LOCAL_API_KEY="${SLIM_ARC_HARNESS_API_KEY:-local}" \
        "$node_bin" apps/cli/lib/bin.js "${harness_args[@]}"
    local pid
    pid=$(service_pid "$harness_label")
    echo "$pid" > "$harness_pid_file"
    local code=""
    for _ in {1..40}; do
        code=$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3080/ 2>/dev/null || true)
        [[ "$code" == "200" ]] && return
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "DeepSeek Harness exited during startup:" >&2
            tail -30 "$state_dir/deepseek-harness.log" >&2
            return 1
        fi
        sleep 0.25
    done
    echo "DeepSeek Harness did not become ready on port 3080." >&2
    return 1
}

command=${1:-optimized}
surface=${2:-llama}
mkdir -p "$state_dir"

case "$command" in
    stop)
        stop_all
        echo "SLIM-ARC demo stopped."
        exit 0
        ;;
    status)
        status
        exit 0
        ;;
    optimized|cpu-iq2|baseline) ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

[[ "$surface" == "llama" || "$surface" == "harness" ]] || {
    usage >&2
    exit 2
}
[[ -x "$server_bin" ]] || {
    echo "Missing native SLIM-ARC server: $server_bin" >&2
    exit 1
}
stop_all
log="$state_dir/$command-server.log"

if [[ "$command" == "optimized" ]]; then
    model=$iq2_model
    # Once all weights fit in Metal's working set, host mmap prefetch only
    # competes with the GPU. The optimized profile therefore selects the
    # full-residency branch of SLIM-ARC instead of issuing redundant advice.
    export SLIM_ARC_DYNAMIC_MADV=0
    export SLIM_ARC_PREFETCH=0
    export SLIM_ARC_NO_WEIGHT_PREFETCH=1
    export SLIM_ARC_NO_EXPERT_PREFETCH=1
    export SLIM_ARC_DECODE_THREADS=6
    threads=6
    batch_threads=6
    gpu_layers=99
    flash_attention=on
else
    if [[ "$command" == "cpu-iq2" ]]; then
        model=$iq2_model
    else
        model=$q4_model
    fi
    export SLIM_ARC_DYNAMIC_MADV=0
    export SLIM_ARC_PREFETCH=0
    export SLIM_ARC_NO_WEIGHT_PREFETCH=1
    export SLIM_ARC_NO_EXPERT_PREFETCH=1
    export SLIM_ARC_EXPERT_CONF=0
    export SLIM_ARC_EXPERT_RECLAIM_WASTE=0
    export SLIM_ARC_EXPERT_RESIDENCY=0
    export SLIM_ARC_EXPERT_TRANSITION=0
    threads=1
    batch_threads=1
    gpu_layers=0
    flash_attention=off
fi

[[ -f "$model" ]] || {
    echo "Missing model: $model" >&2
    exit 1
}

server_command=("$server_bin")
if [[ "$command" == "baseline" ]]; then
    # Use macOS's real background QoS to model a resource-starved edge task.
    # This changes scheduling priority only; it does not inject artificial delay.
    server_command=(/usr/sbin/taskpolicy -b "$server_bin")
fi

launchctl submit -l "$server_label" \
    -o "$state_dir/$command-server.stdout.log" \
    -e "$log" -- /usr/bin/env \
    SLIM_ARC_DYNAMIC_MADV="$SLIM_ARC_DYNAMIC_MADV" \
    SLIM_ARC_PREFETCH="$SLIM_ARC_PREFETCH" \
    SLIM_ARC_NO_WEIGHT_PREFETCH="$SLIM_ARC_NO_WEIGHT_PREFETCH" \
    SLIM_ARC_NO_EXPERT_PREFETCH="$SLIM_ARC_NO_EXPERT_PREFETCH" \
    SLIM_ARC_DECODE_THREADS="${SLIM_ARC_DECODE_THREADS:-$threads}" \
    SLIM_ARC_EXPERT_CONF="${SLIM_ARC_EXPERT_CONF:-0}" \
    SLIM_ARC_EXPERT_RECLAIM_WASTE="${SLIM_ARC_EXPERT_RECLAIM_WASTE:-0}" \
    SLIM_ARC_EXPERT_RESIDENCY="${SLIM_ARC_EXPERT_RESIDENCY:-0}" \
    SLIM_ARC_EXPERT_TRANSITION="${SLIM_ARC_EXPERT_TRANSITION:-0}" \
    "${server_command[@]}" \
    -m "$model" --alias qwen3-next-80b-a3b \
    --host 127.0.0.1 --port "$port" --ui --metrics --slots --jinja \
    -t "$threads" -tb "$batch_threads" -c 4096 -np 1 \
    -b 512 -ub 256 -ngl "$gpu_layers" -fa "$flash_attention" -ctk f16 -ctv f16
server_pid=$(service_pid "$server_label")
echo "$server_pid" > "$pid_file"

echo "Starting $command profile (pid $(<"$pid_file"))..."
for i in {1..120}; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health" 2>/dev/null || true)
    if [[ "$code" == "200" ]]; then
        break
    fi
    if ! kill -0 "$(<"$pid_file")" 2>/dev/null; then
        echo "llama-server exited during model load:" >&2
        tail -30 "$log" >&2
        exit 1
    fi
    if (( i % 10 == 0 )); then
        echo "  loading $(basename "$model")... ${i}s"
    fi
    sleep 1
done

curl -fsS "http://127.0.0.1:$port/health" >/dev/null || {
    echo "Model is still loading; follow: tail -f '$log'" >&2
    exit 1
}

url="http://127.0.0.1:$port/"
if [[ "$surface" == "harness" ]]; then
    start_harness
    url=http://127.0.0.1:3080/
fi

echo "Ready: $url"
echo "API:   http://127.0.0.1:$port/v1"
echo "Log:   $log"
open "$url" >/dev/null 2>&1 || true
