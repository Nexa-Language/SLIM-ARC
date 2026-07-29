#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <model_name> <local_dir>"
    exit 1
fi

MODEL_NAME=$1
LOCAL_DIR=$2

huggingface-cli download --resume-download "$MODEL_NAME" --local-dir "$LOCAL_DIR"
