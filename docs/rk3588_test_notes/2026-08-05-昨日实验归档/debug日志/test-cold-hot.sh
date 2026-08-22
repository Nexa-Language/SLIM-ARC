#!/bin/bash
# SLIM-ARC RK3588 T3-4.1/4.5/4.6 测试：冷/热缓存 + 上下文伸缩(-c 512/1024) + RSS 峰值
# 说明：无 root 无法 drop_caches，冷缓存为"模型页不完全在 page cache"的近似，
#       热缓存为连续第二次运行（模型已在 page cache）。
# 注意：无 tty 时 llama-cli 全部输出走 stdout，stderr 为空；MONITOR 行追加到 .out 末尾。

cd /home/orangepi/src/llama-upstream
MODEL=/home/orangepi/SLIM-ARC/data/models/Qwen3-4B-Q4_K_M.gguf
CLI=./build/bin/llama-cli
export LD_LIBRARY_PATH=build/bin
MON=/home/orangepi/SLIM-ARC/docs/rk3588_test_notes/monitor-peak-rss.sh
OUT=/home/orangepi/SLIM-ARC/docs/rk3588_test_notes

echo "########## COLD RUN (c=1024) ##########"
"$MON" env LD_LIBRARY_PATH=build/bin "$CLI" -m "$MODEL" -t 4 -c 1024 \
    -p 'The capital of China is' -n 32 --single-turn \
    < /dev/null > "$OUT/raw-infer-cold-c1024.out" 2> "$OUT/raw-infer-cold-c1024.stderr"

echo "########## HOT RUN (c=1024) ##########"
"$MON" env LD_LIBRARY_PATH=build/bin "$CLI" -m "$MODEL" -t 4 -c 1024 \
    -p 'The capital of China is' -n 32 --single-turn \
    < /dev/null > "$OUT/raw-infer-hot-c1024.out" 2> "$OUT/raw-infer-hot-c1024.stderr"

echo "########## RUN (c=512) ##########"
"$MON" env LD_LIBRARY_PATH=build/bin "$CLI" -m "$MODEL" -t 4 -c 512 \
    -p 'The capital of China is' -n 32 --single-turn \
    < /dev/null > "$OUT/raw-infer-c512.out" 2> "$OUT/raw-infer-c512.stderr"

echo "===== DONE ====="
