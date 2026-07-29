#!/usr/bin/env bash

set -euo pipefail

if [ -z "${ANDROID_NDK_ROOT:-}" ]; then
    echo "ANDROID_NDK_ROOT must point to an installed Android NDK." >&2
    exit 1
fi

rm -rf build-android android
mkdir build-android

BUILD_JOBS=${BUILD_JOBS:-4}

cmake \
-DANDROID=ON \
-DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK_ROOT/build/cmake/android.toolchain.cmake \
-DANDROID_ABI=arm64-v8a \
-DANDROID_PLATFORM=android-32 \
-DCMAKE_C_FLAGS="-march=armv8-a" \
-DCMAKE_CXX_FLAGS="-march=armv8-a" \
-DGGML_OPENMP=OFF \
-DGGML_LLAMAFILE=OFF \
-B build-android

cmake --build build-android --config Release -j "$BUILD_JOBS"

cmake --install build-android --prefix android --config Release
