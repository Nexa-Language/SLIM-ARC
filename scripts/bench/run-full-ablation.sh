#!/bin/bash
# SLIM-ARC 完整消融实验脚本
# 在完整 SLIM-ARC 下重跑所有实验，含逐个关闭优化的消融
# 用法: bash scripts/bench/run-full-ablation.sh

set -e
cd "$(dirname "$0")/../.."
LLAMA="src/llama-upstream/build/bin/llama-bench"
LIB="src/llama-upstream/build/bin"
LOGDIR="logs/ablation/full-rerun"
mkdir -p "$LOGDIR"

# 模型
M80B_IQ4="data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf"
M80B_Q4K="data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
M4B="data/models/Qwen3-4B-Q4_K_M.gguf"
MOLMOE="data/models/olmoe-1b-7b-0924-instruct-q4_k_m.gguf"

echo "=== 1. 80B IQ4_XS + SLIM-ARC 全开 三档 ==="
# 8GB + 4核
for tier in "8G:slim-arc-low:4" "16G:slim-arc-high:8"; do
    mem=${tier%%:*}
    cg=${tier#*:}; cg=${cg%:*}
    t=${tier##*:}
    echo "--- ${mem} ${cg} ${t}threads ---"
    cgexec -g memory,cpu:$cg bash -c "LD_LIBRARY_PATH=$LIB $LLAMA -m $M80B_IQ4 -t $t -p 128 -n 64 -ctk q4_0 -ctv q4_0 -fa auto --repeat 3" 2>&1 | tee "$LOGDIR/80b-${mem}-full.png" | grep -E "pp|tg|t/s"
done

echo "=== 2. 80B 32GB 热缓存 消融（逐个关闭）==="
# Full SLIM-ARC (MADV + KVq4 + IQ4 + FA)
echo "--- Full SLIM-ARC ---"
LD_LIBRARY_PATH=$LIB $LLAMA -m $M80B_IQ4 -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa auto 2>&1 | tee "$LOGDIR/80b-32g-ablation-full.txt" | grep "t/s"
# -FA (关 FlashAttention)
echo "--- -FlashAttention ---"
LD_LIBRARY_PATH=$LIB $LLAMA -m $M80B_IQ4 -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa off 2>&1 | tee "$LOGDIR/80b-32g-ablation-no-fa.txt" | grep "t/s" || echo "fa off failed (expected for Qwen3)"
# -KVq4 (KV 用 f16)
echo "--- -KVq4 (f16) ---"
LD_LIBRARY_PATH=$LIB $LLAMA -m $M80B_IQ4 -t 8 -p 64 -n 48 -ctk f16 -ctv f16 -fa auto 2>&1 | tee "$LOGDIR/80b-32g-ablation-no-kvq4.txt" | grep "t/s"
# -MADV (SLIM_ARC_DISABLE)
echo "--- -MADV (SLIM_ARC_DISABLE) ---"
LD_LIBRARY_PATH=$LIB SLIM_ARC_DISABLE=1 $LLAMA -m $M80B_IQ4 -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa auto 2>&1 | tee "$LOGDIR/80b-32g-ablation-no-madv.txt" | grep "t/s"
# +Eviction
echo "--- +Eviction ---"
LD_LIBRARY_PATH=$LIB SLIM_ARC_KV_EVICT=1 SLIM_ARC_KV_SINK=4 SLIM_ARC_KV_WINDOW=32 $LLAMA -m $M80B_IQ4 -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa auto 2>&1 | tee "$LOGDIR/80b-32g-ablation-evict.txt" | grep "t/s"

echo "=== 3. Q4_K_M vs IQ4_XS 对比（32GB全开）==="
LD_LIBRARY_PATH=$LIB $LLAMA -m $M80B_Q4K -t 8 -p 64 -n 48 -ctk q4_0 -ctv q4_0 -fa auto 2>&1 | tee "$LOGDIR/80b-32g-q4km-full.txt" | grep "t/s"

echo "=== 4. 小模型 2GB+1核 极端环境 ==="
for model in "$M4B" "$MOLMOE"; do
    name=$(basename "$model" .gguf | head -c 20)
    echo "--- $name 2GB+1核 ---"
    cgexec -g memory,cpu:slim-arc-low bash -c "LD_LIBRARY_PATH=$LIB $LLAMA -m $model -t 1 -p 64 -n 16 -fa auto" 2>&1 | tee "$LOGDIR/${name}-2gb-1core.txt" | grep "t/s" || echo "OOM or timeout"
done

echo "=== 5. KV 量化相关性（KV q4 对带宽影响）==="
for kv in f16 q8_0 q4_0; do
    echo "--- KV=$kv ---"
    LD_LIBRARY_PATH=$LIB $LLAMA -m $M80B_IQ4 -t 8 -p 64 -n 48 -ctk $kv -ctv $kv -fa auto 2>&1 | tee "$LOGDIR/80b-32g-kv-${kv}.txt" | grep "t/s"
done

echo "=== DONE ==="
echo "Results in $LOGDIR/"
