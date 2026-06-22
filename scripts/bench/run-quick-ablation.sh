#!/usr/bin/env bash
# SLIM-ARC: Quick Ablation - baseline vs optimized comparison
#
# Runs llama-bench under 3 cgroup tiers for Qwen3-4B (dense) and OLMoE (MoE),
# comparing baseline (SLIM_ARC_DISABLE=1) vs SLIM-ARC optimized.
#
# Usage: bash scripts/bench/run-quick-ablation.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
RESULT_DIR="$PROJECT_ROOT/logs/ablation"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CSV_FILE="$RESULT_DIR/ablation-${TIMESTAMP}.csv"
RAW_DIR="$RESULT_DIR/raw-${TIMESTAMP}"
mkdir -p "$RAW_DIR"

# CSV header
echo "model,tier,threads,mode,test,tok_per_s,peak_rss_mb" > "$CSV_FILE"

DENSE_MODEL="$PROJECT_ROOT/data/models/Qwen3-4B-Q4_K_M.gguf"
MOE_MODEL="$PROJECT_ROOT/data/models/olmoe-1b-7b-0924-instruct-q4_k_m.gguf"

TIERS=("low" "mid" "high")
TIER_THREADS=("4" "6" "8")
TIER_MEM_MB=("8192" "12288" "16384")

PROMPT_LEN=64
GEN_LEN=16
REPEATS=3

run_bench() {
    local model=$1
    local tier=$2
    local threads=$3
    local mode=$4  # "baseline" or "slim-arc"
    local model_name=$5
    local mem_mb=${TIER_MEM_MB[$(echo ${TIERS[@]} | tr ' ' '\n' | grep -n "^$tier$" | cut -d: -f1 | awk '{print $1-1}')]}

    local env_prefix=""
    if [ "$mode" = "baseline" ]; then
        env_prefix="SLIM_ARC_DISABLE=1"
    fi

    local raw_file="$RAW_DIR/${model_name}-${tier}-${mode}.txt"

    echo "  [$model_name] tier=$tier mode=$mode ..."

    # Drop page cache for cold-cache measurement (fair baseline vs optimized)
    sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true

    # Reset cgroup memory stat
    echo 0 | sudo tee /sys/fs/cgroup/slim-arc-$tier/memory.peak >/dev/null 2>&1 || true

    local cmd="sudo cgexec -g memory,cpu:slim-arc-$tier env LD_LIBRARY_PATH=$LLAMA_DIR/build/bin $env_prefix timeout 120 $LLAMA_DIR/build/bin/llama-bench -m $model -t $threads -p $PROMPT_LEN -n $GEN_LEN -r $REPEATS -mmp 1"

    eval "$cmd" 2>&1 | tee "$raw_file" | tail -5

    # Parse llama-bench output for t/s values
    # Format: | model | size | params | backend | threads | test | t/s |
    while IFS='|' read -r _ _ _ _ _ _ test_field ts_field; do
        test_field=$(echo "$test_field" | xargs)
        ts_field=$(echo "$ts_field" | xargs)
        if [[ "$test_field" =~ ^pp[0-9]+$ ]] || [[ "$test_field" =~ ^tg[0-9]+$ ]]; then
            # Extract numeric t/s (before ±)
            local ts=$(echo "$ts_field" | grep -oP '[\d.]+' | head -1)
            # Read peak RSS from cgroup
            local peak=$(cat /sys/fs/cgroup/slim-arc-$tier/memory.peak 2>/dev/null || echo 0)
            local peak_mb=$((peak / 1024 / 1024))
            echo "$model_name,$tier,$threads,$mode,$test_field,$ts,$peak_mb" >> "$CSV_FILE"
        fi
    done < "$raw_file"
}

echo "=============================================="
echo "SLIM-ARC Quick Ablation: baseline vs optimized"
echo "Date: $(date -Iseconds)"
echo "Output: $CSV_FILE"
echo "=============================================="

for i in "${!TIERS[@]}"; do
    tier=${TIERS[$i]}
    threads=${TIER_THREADS[$i]}

    echo ""
    echo "--- Tier: $tier ($threads threads) ---"

    # Dense model
    if [ -f "$DENSE_MODEL" ]; then
        run_bench "$DENSE_MODEL" "$tier" "$threads" "baseline" "qwen3-4b"
        run_bench "$DENSE_MODEL" "$tier" "$threads" "slim-arc" "qwen3-4b"
    fi

    # MoE model
    if [ -f "$MOE_MODEL" ]; then
        run_bench "$MOE_MODEL" "$tier" "$threads" "baseline" "olmoe"
        run_bench "$MOE_MODEL" "$tier" "$threads" "slim-arc" "olmoe"
    fi
done

echo ""
echo "=============================================="
echo "Ablation complete. CSV saved to: $CSV_FILE"
echo "=============================================="
echo ""
cat "$CSV_FILE"
