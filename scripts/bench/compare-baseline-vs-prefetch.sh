#!/usr/bin/env bash
# SLIM-ARC benchmark comparison: baseline (no prefetch) vs SLIM-ARC prefetch.
# Usage: bash scripts/bench/compare-baseline-vs-prefetch.sh [tier] [model]
# tier: low|mid|high (default: low)
# model: path to GGUF (default: data/models/Qwen3-4B-Q4_K_M.gguf)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
RESULT_DIR="$PROJECT_ROOT/logs"
mkdir -p "$RESULT_DIR"

TIER="${1:-low}"
MODEL="${2:-$PROJECT_ROOT/data/models/Qwen3-4B-Q4_K_M.gguf}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULT_FILE="$RESULT_DIR/comparison-${TIER}-${TIMESTAMP}.txt"

if [ ! -f "$MODEL" ]; then
    echo "Error: model not found at $MODEL" >&2
    exit 1
fi

echo "=== SLIM-ARC Benchmark Comparison ===" | tee "$RESULT_FILE"
echo "Date: $(date -Iseconds)" | tee -a "$RESULT_FILE"
echo "Tier: $TIER" | tee -a "$RESULT_FILE"
echo "Model: $(basename $MODEL)" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# SLIM-ARC prefetch version (current build)
echo "--- SLIM-ARC with Prefetch ---" | tee -a "$RESULT_FILE"
echo "Dropping page cache..." | tee -a "$RESULT_FILE"
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'

BENCH_CMD="sudo cgexec -g memory,cpu:slim-arc-$TIER env LD_LIBRARY_PATH=$LLAMA_DIR/build/bin timeout 180 $LLAMA_DIR/build/bin/llama-bench -m $MODEL -t 4 -p 64 -n 32"

echo "Running SLIM-ARC prefetch benchmark..." | tee -a "$RESULT_FILE"
eval "$BENCH_CMD" 2>&1 | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

echo "Results saved to $RESULT_FILE"
echo ""
echo "To run baseline (no prefetch), revert the patch and rebuild:"
echo "  cd $LLAMA_DIR && git checkout -- src/ && cmake --build build --config Release -j \$(nproc)"
