#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <model_path> <quantized_model_path>"
    exit 1
fi

MODEL_PATH=$1
QUANTIZED_MODEL_PATH=$2
ALIGN=${ALIGN:-4096}

if [ -z "${LLAMA_QUANTIZE:-}" ]; then
    if [ -x "$PROJECT_ROOT/host/bin/llama-quantize" ]; then
        LLAMA_QUANTIZE=$PROJECT_ROOT/host/bin/llama-quantize
    elif [ -x "$PROJECT_ROOT/build-host/bin/llama-quantize" ]; then
        LLAMA_QUANTIZE=$PROJECT_ROOT/build-host/bin/llama-quantize
    elif [ -x "$PROJECT_ROOT/llama-quantize" ]; then
        LLAMA_QUANTIZE=$PROJECT_ROOT/llama-quantize
    else
        echo "Could not find llama-quantize. Run bash build-host.sh first or set LLAMA_QUANTIZE." >&2
        exit 1
    fi
fi

python "$PROJECT_ROOT/convert.py" "$MODEL_PATH" --do_sort --alignment "$ALIGN"
GGUF_FILE=$(find "$MODEL_PATH" \( -name "*f16.gguf" -o -name "*F16.gguf" \) | head -n 1)
if [ ! -f "$GGUF_FILE" ]; then
    echo "No gguf file [$GGUF_FILE] found in $MODEL_PATH"
    exit 1
fi
mkdir -p "$(dirname "$QUANTIZED_MODEL_PATH")"
echo "Quantizing $GGUF_FILE to $QUANTIZED_MODEL_PATH with alignment $ALIGN"
"$LLAMA_QUANTIZE" --align "$ALIGN" "$GGUF_FILE" "$QUANTIZED_MODEL_PATH" Q4_0
echo "Finish converting $MODEL_PATH, quantized model is saved in $QUANTIZED_MODEL_PATH"
