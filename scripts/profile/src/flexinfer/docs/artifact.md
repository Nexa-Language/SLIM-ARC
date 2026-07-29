# Artifact Guide

This document describes how to build and run the FlexInfer code artifact from a
clean checkout. Model weights, converted GGUF files, benchmark logs, and local
runtime logs are intentionally not tracked by git.

## Contents

The artifact includes:

- FlexInfer runtime changes on top of the `llama.cpp` and `ggml` stack.
- Linux host and Android build helper scripts.
- Prefetch-aware command-line tools: `flexinfer-cli` and `flexinfer-bench`.
- Model conversion and benchmark helper scripts.

The artifact does not include:

- Model weights or downloaded Hugging Face checkpoints.
- Generated GGUF files.
- Benchmark output directories such as `bench-results/`.

Use only models whose licenses allow your intended use.

## Relationship To llama.cpp

The public FlexInfer history starts from upstream `llama.cpp` commit
`c7499c557` (build `b3903`, dated 2024-10-10). FlexInfer then imports selected
later GGUF conversion utilities before adding the runtime changes. This is not a
full rebase onto a later `llama.cpp` revision; the core runtime delta should be
reviewed against `c7499c557`.

The FlexInfer prefetch implementation is guarded by the `FLEXINFER`
compile definition. CMake and Makefile prefetch targets define it for
`ggml-prefetch`, `llama-prefetch`, `common-prefetch`, `flexinfer-cli`, and
`flexinfer-bench`; the upstream-style `llama-cli` and `llama-bench` targets are
built without that definition.

A few shared changes intentionally apply to both paths rather than being hidden
behind `FLEXINFER`:

- GGUF and CPU tensor alignment defaults use 4096-byte alignment.
- Linux direct-I/O reads assume GGUF tensor offsets, destination buffers, and
  read lengths are 4096-byte aligned. The FlexInfer tensor-read path checks
  these invariants before issuing direct reads.
- Public parameters include benchmarking/debug helpers such as
  `dump_gemm_shapes`, quantization alignment, and dummy input generation.
- Build and diagnostic logging changes are shared with the upstream-style
  binaries.

## Environment

Host builds require CMake, a C/C++ compiler, and Python 3. Android builds
require the Android NDK.

Install Python dependencies when converting Hugging Face checkpoints:

```bash
python -m pip install -r requirements.txt
```

## Build

Build host binaries and libraries:

```bash
bash build-host.sh
```

Expected host outputs:

```text
host/bin/flexinfer-cli
host/bin/flexinfer-bench
host/bin/llama-cli
host/bin/llama-bench
host/lib/
```

Build Android command-line artifacts:

```bash
export ANDROID_NDK_ROOT=/path/to/android-ndk
bash build-android.sh
```

Expected Android outputs:

```text
android/bin/flexinfer-cli
android/bin/flexinfer-bench
android/lib/
```

## Prepare Models

FlexInfer consumes GGUF models. To convert and quantize a local Hugging Face
checkpoint, first build host tools, then run:

```bash
bash scripts/convert-hf-models.sh /path/to/hf/checkpoint hf-models/model-q4_0.gguf
```

The script uses `host/bin/llama-quantize` by default. Override it with
`LLAMA_QUANTIZE=/path/to/llama-quantize` if needed.

The conversion script writes GGUF files with 4096-byte alignment and invokes
quantization with `--align 4096` by default. This is required for FlexInfer's
Linux direct-I/O path. If you use an external GGUF file, make sure it was
created with 4096-byte GGUF alignment before running FlexInfer with the
direct-I/O streaming path.

Keep converted models under `hf-models/` or another ignored directory. Do not
commit model weights.

## Smoke Test

Run the standard upstream-style CLI:

```bash
LD_LIBRARY_PATH=host/lib ./host/bin/llama-cli \
  -m hf-models/model-q4_0.gguf \
  -p "I believe the meaning of life is" \
  -n 64 -t 1 -c 512
```

Run the FlexInfer prefetch-aware CLI:

```bash
LD_LIBRARY_PATH=host/lib ./host/bin/flexinfer-cli \
  -m hf-models/model-q4_0.gguf \
  -p "I believe the meaning of life is" \
  -n 64 -t 1 -c 512 -am 2 -tp 1
```

The key FlexInfer options are:

- `-am`: available memory budget in GB for FlexInfer planning. Fractional
  budgets such as `0.5` are supported.
- `-tp`: number of prefetch threads. Use `0` for the synchronous read path.

## Benchmarks

Use `flexinfer-bench` directly for quick checks:

```bash
LD_LIBRARY_PATH=host/lib ./host/bin/flexinfer-bench \
  -m hf-models/model-q4_0.gguf \
  -p 16 -n 16 -am 2 -tp 1
```

For repeated Linux host or Android benchmark runs with cooldown and system-state
logging, see `docs/benchmark.md`.
