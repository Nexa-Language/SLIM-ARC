#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
    printf 'fake llama-bench\n'
    exit 0
fi
printf '{"build_commit":"360e134","model_type":"fixture","n_prompt":4,"n_gen":1,"avg_ts":1.0}\n'
