#!/bin/bash
# SLIM-ARC 串行消融实验（确保无内存竞争，数据可信）
# 每次只跑一个实例，跑完再跑下一个
set -e
cd "$(dirname "$0")/../.."
LLAMA="src/llama-upstream/build/bin/llama-bench"
LIB="src/llama-upstream/build/bin"
LOGDIR="logs/ablation/full-rerun"
mkdir -p "$LOGDIR"
MODEL="data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf"

run_test() {
    local name="$1"; shift
    echo "=== $name ==="
    # 清缓存（需要root）
    echo 3 2>/dev/null > /proc/sys/vm/drop_caches || true
    LD_LIBRARY_PATH="$LIB" stdbuf -oL timeout 300 "$LLAMA" \
        -m "$MODEL" -t 8 -p 64 -n 48 -fa auto "$@" \
        2>&1 | tee "$LOGDIR/80b-32g-ablation-${name}.txt" | grep "t/s"
    echo ""
}

# 串行执行，每个配置独立
run_test "full"        -ctk q4_0 -ctv q4_0
run_test "no-kvq4"     -ctk f16 -ctv f16
run_test "no-madv"     -ctk q4_0 -ctv q4_0   # 需要 SLIM_ARC_DISABLE=1，下面单独处理
run_test "evict"       -ctk q4_0 -ctv q4_0   # 需要 SLIM_ARC_KV_EVICT=1，下面单独处理

# SLIM_ARC_DISABLE 的需要特殊处理
echo "=== no-madv (SLIM_ARC_DISABLE=1) ==="
echo 3 2>/dev/null > /proc/sys/vm/drop_caches || true
LD_LIBRARY_PATH="$LIB" SLIM_ARC_DISABLE=1 stdbuf -oL timeout 300 "$LLAMA" \
    -m "$MODEL" -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa auto \
    2>&1 | tee "$LOGDIR/80b-32g-ablation-no-madv.txt" | grep "t/s"

echo "=== evict (SLIM_ARC_KV_EVICT=1) ==="
echo 3 2>/dev/null > /proc/sys/vm/drop_caches || true
LD_LIBRARY_PATH="$LIB" SLIM_ARC_KV_EVICT=1 SLIM_ARC_KV_SINK=4 SLIM_ARC_KV_WINDOW=32 \
    stdbuf -oL timeout 300 "$LLAMA" \
    -m "$MODEL" -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa auto \
    2>&1 | tee "$LOGDIR/80b-32g-ablation-evict.txt" | grep "t/s"

echo "=== ALL DONE ==="
