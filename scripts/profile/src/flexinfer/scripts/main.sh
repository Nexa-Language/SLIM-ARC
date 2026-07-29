#!/usr/bin/env bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
OUTPUT_DIR=${OUTPUT_DIR:-$PROJECT_ROOT/outputs/main}
REPEAT=${REPEAT:-3}
MEM=(5 10 15 20 25 30 35 40)
MODEL_1_PATH=${MODEL_1_PATH:-$PROJECT_ROOT/hf-models/llama-2-7b-chat}
MODEL_2_PATH=${MODEL_2_PATH:-$PROJECT_ROOT/hf-models/llama-2-13b-chat}
MODEL_3_PATH=${MODEL_3_PATH:-$PROJECT_ROOT/hf-models/codellama-34b}
MODEL_4_PATH=${MODEL_4_PATH:-$PROJECT_ROOT/hf-models/llama-2-70b-chat}
LLAMA_CLI=${LLAMA_CLI:-$PROJECT_ROOT/host/bin/llama-cli}
FLEXINFER_CLI=${FLEXINFER_CLI:-$PROJECT_ROOT/host/bin/flexinfer-cli}

function ceil() {
    floor=`echo "scale=0; $1/1" | bc -l`
    add=`awk -v num1=$1 -v num2=$floor 'BEGIN {print(num1>num2)?"1":"0"}'`
    echo `expr $floor + $add`
}

for j in $(seq 1 $REPEAT)
do
    if [ ! -d "$OUTPUT_DIR-$j" ]; then
        mkdir -p $OUTPUT_DIR-$j
    fi

    echo "Evaluating llama-2-7b"
    for i in "${MEM[@]}"
    do
        LIM=$((i*1024*1024*1024/10))
        LIM=`ceil $LIM`
        AM=`bc -l <<< $i/10`
        echo "Memory Limit: $LIM Bytes, Set Available Memory: $AM GB"
        sudo echo $LIM | sudo tee /sys/fs/cgroup/limmem/memory.max
        echo "Run MMAP"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $LLAMA_CLI -m $MODEL_1_PATH/ggml-model-llama-2-7b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -t 48 $NUM_THREAD > $OUTPUT_DIR-$j/main-llama-2-7b-mmap-$i.txt 2>&1

        echo "Run SYNCIO"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_1_PATH/ggml-model-llama-2-7b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -am $AM -tp 0 > $OUTPUT_DIR-$j/main-llama-2-7b-syncio-$i.txt 2>&1

        echo "Run FlexInfer"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_1_PATH/ggml-model-llama-2-7b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -am $AM > $OUTPUT_DIR-$j/main-llama-2-7b-prefetch-$i.txt 2>&1
    done

    echo "Evaluating llama-2-13b"
    for i in "${MEM[@]}"
    do
        LIM=`bc -l <<< $i*1024*1024*1024/5`
        LIM=`ceil $LIM`
        AM=`bc -l <<< $i/5`
        echo "Memory Limit: $LIM Bytes, Set Available Memory: $AM GB"
        sudo echo $LIM | sudo tee /sys/fs/cgroup/limmem/memory.max
        echo "Run MMAP"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $LLAMA_CLI -m $MODEL_2_PATH/ggml-model-llama-2-13b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -t 48 > $OUTPUT_DIR-$j/main-llama-2-13b-mmap-$i.txt 2>&1

        echo "Run SYNCIO"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_2_PATH/ggml-model-llama-2-13b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -am $AM -tp 0 > $OUTPUT_DIR-$j/main-llama-2-13b-syncio-$i.txt 2>&1

        echo "Run FlexInfer"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_2_PATH/ggml-model-llama-2-13b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -am $AM > $OUTPUT_DIR-$j/main-llama-2-13b-prefetch-$i.txt 2>&1
    done

    echo "Evaluating codellama-34b"
    for i in "${MEM[@]}"
    do
        LIM=`bc -l <<< $i*1024*1024*1024/2`
        LIM=`ceil $LIM`
        AM=`bc -l <<< $i/2`
        echo "Memory Limit: $LIM Bytes, Set Available Memory: $AM GB"
        sudo echo $LIM | sudo tee /sys/fs/cgroup/limmem/memory.max
        echo "Run MMAP"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $LLAMA_CLI -m $MODEL_3_PATH/ggml-model-codellama-34b-q4_0.gguf -p "Please write a code of quick sort" -n 16 -c 512 -t 48 > $OUTPUT_DIR-$j/main-codellama-34b-mmap-$i.txt 2>&1

        echo "Run SYNCIO"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_3_PATH/ggml-model-codellama-34b-q4_0.gguf -p "Please write a code of quick sort" -n 16 -c 512 -am $AM -tp 0 > $OUTPUT_DIR-$j/main-codellama-34b-syncio-$i.txt 2>&1

        echo "Run FlexInfer"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_3_PATH/ggml-model-codellama-34b-q4_0.gguf -p "Please write a code of quick sort" -n 16 -c 512 -am $AM > $OUTPUT_DIR-$j/main-codellama-34b-prefetch-$i.txt 2>&1
    done

    echo "Evaluating llama-2-70b"
    for i in "${MEM[@]}"
    do
        LIM=`bc -l <<< $i*1024*1024*1024`
        LIM=`ceil $LIM`
        AM=`bc -l <<< $i`
        echo "Memory Limit: $LIM Bytes, Set Available Memory: $AM GB"
        sudo echo $LIM | sudo tee /sys/fs/cgroup/limmem/memory.max
        echo "Run MMAP"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $LLAMA_CLI -m $MODEL_4_PATH/ggml-model-llama-2-70b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -t 48 > $OUTPUT_DIR-$j/main-llama-2-70b-mmap-$i.txt 2>&1

        echo "Run SYNCIO"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_4_PATH/ggml-model-llama-2-70b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -am $AM -tp 0 > $OUTPUT_DIR-$j/main-llama-2-70b-syncio-$i.txt 2>&1

        echo "Run FlexInfer"
        sudo sh -c 'echo 1 >  /proc/sys/vm/drop_caches'
        sudo cgexec -g memory:limmem $FLEXINFER_CLI -m $MODEL_4_PATH/ggml-model-llama-2-70b-chat-q4_0.gguf -p "I believe the meaning of life is" -n 16 -c 512 -am $AM > $OUTPUT_DIR-$j/main-llama-2-70b-prefetch-$i.txt 2>&1
    done
done

# python $PROJECT_ROOT/scripts/read-results.py --result_dir $OUTPUT_DIR --result_type prefill,decode --output_path $OUTPUT_DIR/main-results.csv
