#!/usr/bin/env bash

set -euo pipefail

rm -rf build-host host

if command -v nproc >/dev/null 2>&1; then
    BUILD_JOBS=${BUILD_JOBS:-$(nproc)}
elif command -v sysctl >/dev/null 2>&1; then
    BUILD_JOBS=${BUILD_JOBS:-$(sysctl -n hw.logicalcpu)}
else
    BUILD_JOBS=${BUILD_JOBS:-4}
fi

cmake -DGGML_OPENMP=OFF \
    -DGGML_LLAMAFILE=OFF \
    -B build-host

cmake --build build-host --config Release -j "$BUILD_JOBS"

cmake --install build-host --prefix host --config Release
