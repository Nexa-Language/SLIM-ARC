#!/usr/bin/env bash

set -euo pipefail

readonly repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly llama_root="${SLIM_ARC_LLAMA_ROOT:-$repo_root/src/llama-upstream}"
readonly llama_revision="360e1349f0009c5ad99d21e3c4546b707addc68a"
readonly llama_repository="https://github.com/ggml-org/llama.cpp.git"

for command in git cmake c++ python3 uv; do
    command -v "$command" >/dev/null || {
        echo "Missing required command: $command" >&2
        exit 1
    }
done

uv sync --dev

if [[ ! -d "$llama_root/.git" ]]; then
    if [[ -e "$llama_root" ]]; then
        echo "Refusing to replace non-Git path: $llama_root" >&2
        exit 1
    fi
    git clone --filter=blob:none "$llama_repository" "$llama_root"
fi

git -C "$llama_root" fetch --depth=1 origin "$llama_revision"
git -C "$llama_root" checkout --detach "$llama_revision"
python3 "$repo_root/scripts/apply-slim-arc.py" "$llama_root"

cmake_args=(
    -S "$llama_root"
    -B "$llama_root/build"
    -DCMAKE_BUILD_TYPE=Release
    -DGGML_CPU_REPACK=OFF
    -DLLAMA_BUILD_TESTS=OFF
    -DLLAMA_BUILD_EXAMPLES=ON
    -DLLAMA_BUILD_SERVER=ON
)
if [[ "$(uname -s)" == "Darwin" ]]; then
    cmake_args+=(-DGGML_METAL=ON)
else
    cmake_args+=(-DGGML_METAL=OFF)
fi

cmake "${cmake_args[@]}"
echo "SLIM-ARC development tree is ready at $llama_root"
echo "Build with: cmake --build '$llama_root/build' --config Release -j"
