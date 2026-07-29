# Android

FlexInfer can be cross-compiled for Android with the Android NDK. The public
artifact keeps the command-line runtime path for Android experiments and does
not include the old app/JNI wrapper code.

## Cross-Compile

Install the Android SDK and NDK, then set `ANDROID_NDK_ROOT`:

```bash
export ANDROID_NDK_ROOT=/path/to/android-ndk
bash build-android.sh
```

The script configures CMake for `arm64-v8a` and installs binaries and shared
libraries under:

```text
android/bin/
android/lib/
```

## Push To A Device

Push the install tree and a GGUF model to the device:

```bash
adb shell "mkdir -p /data/local/tmp/flexinfer/hf-models"
adb push android /data/local/tmp/flexinfer/
adb push scripts /data/local/tmp/flexinfer/
adb push hf-models/ggml-model-llama-2-7b-chat-q4_0.gguf /data/local/tmp/flexinfer/hf-models/
adb shell
```

Run the prefetch-aware CLI from the device shell:

```bash
cd /data/local/tmp/flexinfer
LD_LIBRARY_PATH=android/lib ./android/bin/flexinfer-cli \
  -m hf-models/ggml-model-llama-2-7b-chat-q4_0.gguf \
  -p "I believe the meaning of life is" \
  -n 64 -t 1 -c 512 -am 2 -tp 1
```

Use `-am` to set the available memory budget in GB and `-tp` to set the number
of prefetch threads.

## Benchmarks

The benchmark helper is a bash script and should run in a bash-capable Android
shell such as Termux, or in another Android environment where bash is available.
After pushing scripts, artifacts, and models, run it from the device:

```bash
cd /data/local/tmp/flexinfer
AM=8 TP=2 P=16 N=16 bash scripts/bench-speed.sh
```

Cold-cache runs on Android require root access. If the device is rooted, pass a
cache-drop command explicitly:

```bash
DROP_CACHES=1 \
DROP_CACHES_CMD="su -c 'sync; echo 3 > /proc/sys/vm/drop_caches'" \
AM=8 TP=2 P=16 N=16 bash scripts/bench-speed.sh
```

Use `TASKSET_CPUS=<cpu-list>` to pin benchmark processes when `taskset` is
available. CPU numbering is device-specific; choose the core cluster that
matches your evaluation setup.

Override paths if your device layout differs:

```bash
cd /data/local/tmp/flexinfer
BUILD_PREFIX=$PWD/android \
MODEL_PREFIX=$PWD/hf-models \
RESULT_DIR=$PWD/bench-results \
AM=8 TP=2 bash scripts/bench-speed.sh
```

See `benchmark.md` for the full set of benchmark variables.
