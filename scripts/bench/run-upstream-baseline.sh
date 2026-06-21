#!/usr/bin/env bash
# Run upstream llama.cpp baseline benchmark for Qwen3-4B.
# Usage: bash scripts/bench/run-upstream-baseline.sh [tier]
# tier: low|mid|high (default: none, runs without cgroup)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
MODEL="$PROJECT_ROOT/data/models/Qwen3-4B-Q4_K_M.gguf"
RESULT_DIR="$PROJECT_ROOT/logs"
mkdir -p "$RESULT_DIR"

TIER="${1:-none}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULT_FILE="$RESULT_DIR/baseline-upstream-${TIER}-${TIMESTAMP}.txt"

if [ ! -f "$MODEL" ]; then
    echo "Error: model not found at $MODEL" >&2
    exit 1
fi

echo "Running upstream llama.cpp baseline benchmark..."
echo "Model: $MODEL"
echo "Tier:  $TIER"
echo "Output: $RESULT_FILE"
echo ""

BENCH_CMD="LD_LIBRARY_PATH=$LLAMA_DIR/build/bin $LLAMA_DIR/build/bin/llama-bench -m $MODEL -t 4 -p 64 -n 32 --warmup-batch 0"

if [ "$TIER" != "none" ]; then
    CGROUP="slim-arc-$TIER"
    sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
    BENCH_CMD="sudo cgexec -g memory,cpu:$CGROUP env LD_LIBRARY_PATH=$LLAMA_DIR/build/bin $LLAMA_DIR/build/bin/llama-bench -m $MODEL -t 4 -p 64 -n 32"
fi

echo "=== Upstream llama.cpp Baseline ===" | tee "$RESULT_FILE"
echo "Date: $(date -Iseconds)" | tee -a "$RESULT_FILE"
echo "Model: Qwen3-4B-Q4_K_M" | tee -a "$RESULT_FILE"
echo "Tier: $TIER" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

eval "$BENCH_CMD" 2>&1 | tee -a "$RESULT_FILE"

echo ""
echo "Done. Results saved to $RESULT_FILE"
