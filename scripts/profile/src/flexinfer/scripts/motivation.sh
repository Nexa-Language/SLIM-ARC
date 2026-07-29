#!/usr/bin/env bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
OUTPUT_DIR=${OUTPUT_DIR:-$PROJECT_ROOT/outputs/motivation}
MEM=(5 10 15 20 25 30 35 40)
MODEL_PATH=${MODEL_PATH:-$PROJECT_ROOT/hf-models/llama-2-70b-chat}
LLAMA_CLI=${LLAMA_CLI:-$PROJECT_ROOT/host/bin/llama-cli}

if [ ! -d "$OUTPUT_DIR" ]; then
    mkdir -p $OUTPUT_DIR
fi

for i in "${MEM[@]}"
do
    LIM=$((i*1024*1024*1024))
    sudo echo $LIM | sudo tee /sys/fs/cgroup/limmem/memory.max
    sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
    sudo cgexec -g memory:limmem $LLAMA_CLI -m $MODEL_PATH/ggml-model-llama-2-70b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -t 48 > $OUTPUT_DIR/motivation-llama-2-70b-mmap-$i.txt 2>&1
done
