#!/usr/bin/env bash
# SLIM-ARC Phase 4: Ablation Study Framework
#
# Runs systematic experiments across:
# - 3 tiers: low (8G+4core), mid (12G+6core), high (16G+8core)
# - 2 models: Qwen3-4B (dense), OLMoE-1B-7B (MoE)
# - Multiple configurations: baseline, +prefetch, +phase-aware
# - Cold/warm cache modes
#
# Usage: bash scripts/bench/run-ablation.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
RESULT_DIR="$PROJECT_ROOT/logs/ablation"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$RESULT_DIR"

# Models
DENSE_MODEL="$PROJECT_ROOT/data/models/Qwen3-4B-Q4_K_M.gguf"
MOE_MODEL="$PROJECT_ROOT/data/models/olmoe-1b-7b-0924-instruct-q4_k_m.gguf"

# Tiers
TIERS=("low" "mid" "high")
TIER_THREADS=("4" "6" "8")

# Test parameters
PROMPT_LEN=64
GEN_LEN=32
REPEATS=3

run_bench() {
    local model=$1
    local tier=$2
    local threads=$3
    local cache_mode=$4  # "warm" or "cold"
    local label=$5
    local result_file="$RESULT_DIR/${label}-${tier}-${cache_mode}-${TIMESTAMP}.txt"

    echo "  [$label] tier=$tier cache=$cache_mode ..."

    if [ "$cache_mode" = "cold" ]; then
        sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
    fi

    local cmd="sudo cgexec -g memory,cpu:slim-arc-$tier env LD_LIBRARY_PATH=$LLAMA_DIR/build/bin timeout 300 $LLAMA_DIR/build/bin/llama-bench -m $model -t $threads -p $PROMPT_LEN -n $GEN_LEN -r $REPEATS"

    echo "=== $label | $tier | $cache_mode ===" > "$result_file"
    echo "Date: $(date -Iseconds)" >> "$result_file"
    echo "Model: $(basename $model)" >> "$result_file"
    echo "Threads: $threads" >> "$result_file"
    echo "" >> "$result_file"

    eval "$cmd" 2>&1 | tee -a "$result_file" | tail -5
    echo ""
}

echo "=============================================="
echo "SLIM-ARC Phase 4: Ablation Study"
echo "Date: $(date -Iseconds)"
echo "=============================================="
echo ""

# Run experiments
for i in "${!TIERS[@]}"; do
    tier=${TIERS[$i]}
    threads=${TIER_THREADS[$i]}

    echo "--- Tier: $tier (${threads} threads) ---"

    # Dense model (Qwen3-4B)
    if [ -f "$DENSE_MODEL" ]; then
        run_bench "$DENSE_MODEL" "$tier" "$threads" "warm" "dense"
        run_bench "$DENSE_MODEL" "$tier" "$threads" "cold" "dense-cold"
    fi

    # MoE model (OLMoE-1B-7B)
    if [ -f "$MOE_MODEL" ]; then
        run_bench "$MOE_MODEL" "$tier" "$threads" "warm" "moe"
        run_bench "$MOE_MODEL" "$tier" "$threads" "cold" "moe-cold"
    fi

    echo ""
done

echo "=============================================="
echo "Ablation study complete."
echo "Results saved to: $RESULT_DIR/"
echo "=============================================="

# Generate summary
echo ""
echo "Generating summary..."
python3 - "$RESULT_DIR" << 'PYEOF'
import sys, os, glob, re

result_dir = sys.argv[1]
files = sorted(glob.glob(os.path.join(result_dir, "*.txt")))

print(f"\n{'='*80}")
print(f"SLIM-ARC Ablation Summary")
print(f"{'='*80}")
print(f"{'Label':<20} {'Tier':<6} {'Cache':<6} {'pp64 (t/s)':<15} {'tg32 (t/s)':<15}")
print(f"{'-'*20} {'-'*6} {'-'*6} {'-'*15} {'-'*15}")

for f in files:
    with open(f) as fh:
        lines = fh.read()
    # Parse label, tier, cache from filename
    basename = os.path.basename(f)
    parts = basename.replace('.txt','').split('-')
    # Extract pp/tg from llama-bench output
    pp_match = re.search(r'pp\d+\s*\|\s*([\d.]+)', lines)
    tg_match = re.search(r'tg\d+\s*\|\s*([\d.]+)', lines)
    pp = f"{pp_match.group(1)}" if pp_match else "N/A"
    tg = f"{tg_match.group(1)}" if tg_match else "N/A"

    # Parse label/tier/cache from filename
    # Format: {label}-{tier}-{cache}-{timestamp}.txt
    timestamp = parts[-1]
    cache = parts[-2] if len(parts) > 2 else "?"
    tier = parts[-3] if len(parts) > 3 else "?"
    label = "-".join(parts[:-3]) if len(parts) > 3 else basename

    print(f"{label:<20} {tier:<6} {cache:<6} {pp:<15} {tg:<15}")

PYEOF
