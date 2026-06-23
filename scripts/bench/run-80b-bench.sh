#!/usr/bin/env bash
# SLIM-ARC: 80B Qwen3-Next benchmark with log saving
#
# Runs Qwen3-Next-80B in 8GB/16GB cgroups, comparing baseline vs slim-arc.
# Saves complete raw logs to logs/ablation/raw-80b/
#
# Usage: bash scripts/bench/run-80b-bench.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
MODEL="$PROJECT_ROOT/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
LOG_DIR="$PROJECT_ROOT/logs/ablation/raw-80b"
mkdir -p "$LOG_DIR"

run_80b() {
    local tier=$1
    local mode=$2  # "baseline" or "slim-arc"
    local pp=$3
    local tg=$4
    local threads=$5
    local label="${tier}-${mode}-pp${pp}-tg${tg}"
    local log_file="$LOG_DIR/80b-${label}.txt"

    local env_prefix=""
    if [ "$mode" = "baseline" ]; then
        env_prefix="SLIM_ARC_DISABLE=1"
    fi

    echo "=== 80B $label ==="
    sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true

    sudo cgexec -g memory,cpu:slim-arc-$tier \
        env LD_LIBRARY_PATH=$LLAMA_DIR/build/bin $env_prefix \
        timeout 600 $LLAMA_DIR/build/bin/llama-bench \
        -m "$MODEL" -t "$threads" -p "$pp" -n "$tg" -r 2 -mmp 1 2>&1 \
        | tee "$log_file" | tail -5

    echo ""
}

echo "=============================================="
echo "SLIM-ARC 80B Benchmark (Qwen3-Next-80B)"
echo "Date: $(date -Iseconds)"
echo "Logs: $LOG_DIR"
echo "=============================================="

# 8GB cgroup (low tier, 4 threads)
run_80b "low" "baseline"  4 1 4
run_80b "low" "slim-arc"  4 1 4
run_80b "low" "baseline"  16 4 4
run_80b "low" "slim-arc"  16 4 4

# 16GB cgroup (high tier, 8 threads)
run_80b "high" "baseline" 4 1 8
run_80b "high" "slim-arc" 4 1 8

echo "=============================================="
echo "80B benchmark complete. Logs saved to: $LOG_DIR"
echo "=============================================="
