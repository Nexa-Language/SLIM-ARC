#!/bin/bash
# SLIM-ARC 核心实验重跑：完整 SLIM-ARC 全开下的三档性能
# 串行执行，确保无内存竞争
set -e
cd "$(dirname "$0")/../.."
LLAMA="src/llama-upstream/build/bin/llama-bench"
LIB="src/llama-upstream/build/bin"
LOGDIR="logs/ablation/full-rerun"
mkdir -p "$LOGDIR"
M_IQ4="data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf"
M_Q4K="data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"

run_cgroup() {
    local tier="$1" cg="$2" threads="$3" model="$4" name="$5"
    echo "=== ${name} ${tier} ==="
    echo 3 2>/dev/null > /proc/sys/vm/drop_caches || true
    cgexec -g memory,cpu:$cg bash -c \
        "LD_LIBRARY_PATH=$LIB stdbuf -oL timeout 600 $LLAMA -m $model -t $threads -p 128 -n 64 -ctk q4_0 -ctv q4_0 -fa auto" \
        2>&1 | tee "$LOGDIR/core-${name}-${tier}.txt" | grep "t/s"
    echo ""
}

run_32g() {
    local model="$1" name="$2"
    echo "=== ${name} 32GB warm ==="
    LD_LIBRARY_PATH=$LIB stdbuf -oL timeout 300 $LLAMA \
        -m $model -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa auto \
        2>&1 | tee "$LOGDIR/core-${name}-32g.txt" | grep "t/s"
    echo ""
}

# 1. 80B IQ4_XS 三档（全开：MADV+KVq4+IQ4+FA）
echo "########## 80B IQ4_XS Full SLIM-ARC 三档 ##########"
run_cgroup "8g"  "slim-arc-low"  4 "$M_IQ4" "iq4xs"
run_cgroup "16g" "slim-arc-high" 8 "$M_IQ4" "iq4xs"
run_32g "$M_IQ4" "iq4xs"

# 2. 80B Q4_K_M 三档（全开）
echo "########## 80B Q4_K_M Full SLIM-ARC 三档 ##########"
run_cgroup "8g"  "slim-arc-low"  4 "$M_Q4K" "q4km"
run_cgroup "16g" "slim-arc-high" 8 "$M_Q4K" "q4km"
run_32g "$M_Q4K" "q4km"

# 3. 小模型 2GB+1核 极端
echo "########## 小模型 2GB+1核 ##########"
M_4B="data/models/Qwen3-4B-Q4_K_M.gguf"
M_OLMOE="data/models/olmoe-1b-7b-0924-instruct-q4_k_m.gguf"
for model in "$M_4B" "$M_OLMOE"; do
    name=$(basename "$model" .gguf | cut -c1-15)
    echo "=== $name 2g-1core ==="
    echo 3 2>/dev/null > /proc/sys/vm/drop_caches || true
    # 用 slim-arc-low (8GB) 但限制 -t 1 模拟单核
    cgexec -g memory,cpu:slim-arc-low bash -c \
        "LD_LIBRARY_PATH=$LIB stdbuf -oL timeout 120 $LLAMA -m $model -t 1 -p 64 -n 16 -fa auto" \
        2>&1 | tee "$LOGDIR/core-${name}-2g-1core.txt" | grep "t/s" || echo "OOM/timeout"
    echo ""
done

echo "=== ALL CORE EXPERIMENTS DONE ==="
