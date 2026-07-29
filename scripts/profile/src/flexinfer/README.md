# FlexInfer

FlexInfer is a mobile-oriented LLM inference runtime for running large
quantized models under tight memory budgets. It extends the `llama.cpp` and
`ggml` stack with prefetch-aware execution paths, memory planning, and Linux
host plus Android experiment scripts.

This repository contains the code artifact for the FlexInfer paper. Model
weights are not included; use GGUF models that you are licensed to use.

## Repository Layout

- `src/`, `include/`, `common/`, `ggml/`, `gguf-py/`: runtime and model format
  code derived from the `llama.cpp` ecosystem, with FlexInfer modifications.
- `examples/main/`: command line inference binaries, including the FlexInfer
  prefetch-aware CLI `flexinfer-cli`.
- `scripts/`: conversion, benchmark, and experiment helper scripts.
- `docs/`: artifact, Android, benchmark, and release notes.

Upstream baseline executables intentionally retain the `llama.cpp` naming style,
such as `llama-cli` and `llama-bench`. FlexInfer-specific executables use
FlexInfer names, including `flexinfer-cli` and `flexinfer-bench`.

The FlexInfer prefetch path is compiled with the `FLEXINFER` definition.
The `flexinfer-cli` and `flexinfer-bench` binaries enable it through their
prefetch libraries; upstream-style binaries do not. Some shared compatibility
changes intentionally affect both paths, including alignment defaults, public
debug/benchmark parameters, and build/logging plumbing.

## Requirements

- CMake 3.14 or newer
- A C/C++ compiler with C++11 support
- Python 3 for model conversion scripts
- Android NDK for Android cross-compilation

Install Python dependencies when you need model conversion utilities:

```bash
python -m pip install -r requirements.txt
```

## Convert a Hugging Face Model

Convert a local Hugging Face model checkpoint to GGUF:

```bash
bash scripts/convert-hf-models.sh <local_model_path> hf-models/ggml-model-<model_name>-q4_0.gguf
```

Replace `<local_model_path>` and `<model_name>` with your own model path and
output name. Keep generated model files outside git; `hf-models/` is ignored.

## Build

Build for the host machine:

```bash
bash build-host.sh
```

Cross-compile command-line Android artifacts:

```bash
export ANDROID_NDK_ROOT=/path/to/android-ndk
bash build-android.sh
```

The build scripts install artifacts into `host/` or `android/`. See
`docs/artifact.md` for a fuller artifact setup guide.

## Run

Standard `llama.cpp` style inference:

```bash
LD_LIBRARY_PATH=host/lib ./host/bin/llama-cli \
  -m hf-models/ggml-model-llama-2-7b-chat-q4_0.gguf \
  -p "I believe the meaning of life is" \
  -n 64 -t 1 -c 512
```

FlexInfer prefetch-aware inference:

```bash
LD_LIBRARY_PATH=host/lib ./host/bin/flexinfer-cli \
  -m hf-models/ggml-model-llama-2-7b-chat-q4_0.gguf \
  -p "I believe the meaning of life is" \
  -n 64 -t 1 -c 512 -am 2 -tp 1
```

The key FlexInfer flags are:

- `-am`: available memory budget in GB for FlexInfer planning. Fractional
  budgets such as `0.5` are supported.
- `-tp`: number of threads used for prefetching. Use `0` to disable threaded
  prefetching and use synchronous reads.

FlexInfer's Linux direct-I/O path expects GGUF tensor data to be 4096-byte
aligned. Models produced by `scripts/convert-hf-models.sh` use this alignment
by default. If you use externally generated GGUF files, regenerate or quantize
them with 4096-byte GGUF alignment before using the direct-I/O FlexInfer path.

On Android, use the installed Android tree after pushing it to the target
device:

```bash
LD_LIBRARY_PATH=android/lib ./android/bin/flexinfer-cli \
  -m hf-models/ggml-model-llama-2-7b-chat-q4_0.gguf \
  -p "I believe the meaning of life is" \
  -n 64 -t 1 -c 512 -am 2 -tp 1
```

## Benchmark

The benchmark helper supports Linux host artifacts from `build-host.sh` and
Android artifacts from `build-android.sh`:

```bash
AM=8 TP=2 P=16 N=16 bash scripts/bench-speed.sh
```

Limit a helper run to selected models by passing file names relative to
`MODEL_PREFIX`:

```bash
MODEL_LIST="ggml-model-llama-2-7b-chat-q4_0.gguf" \
AM=2 TP=2 T=48 P=16 N=16 bash scripts/bench-speed.sh
```

Run a sweep over multiple memory budgets:

```bash
MEMORY_CONFIGS="0.5 1 2 4" TP=4 bash scripts/bench-speed-memory-sweep.sh
```

Benchmark output is written to `bench-results/` unless `RESULT_DIR` is set.
Generated benchmark logs are ignored by git.
For I/O-sensitive comparisons, enable cold-cache and resource-control options
such as `DROP_CACHES=1`, `TASKSET_CPUS`, and `CGROUP_SPEC` when the platform
allows them. See `docs/benchmark.md` for benchmark variables, cooldown controls,
cache control, CPU binding, and result file layout.

## Limited-Memory Linux Runs

You can use cgroups to emulate smaller memory budgets on Linux:

```bash
sudo cgcreate -g memory:/limmem
echo 2147483648 | sudo tee /sys/fs/cgroup/limmem/memory.max
sudo sh -c 'echo 1 > /proc/sys/vm/drop_caches'
sudo cgexec -g memory:limmem ./host/bin/flexinfer-cli \
  -m hf-models/ggml-model-llama-2-70b-chat-q4_0.gguf \
  -p "I believe the meaning of life is" \
  -n 16 -am 2 -tp 1
```

## Citation

If you use FlexInfer in your research, please cite:

```bibtex
@inproceedings{du2025flexinfer,
  author = {Du, Hongchao and Wu, Shangyu and Kharlamova, Arina and Guan, Nan and Xue, Chun Jason},
  title = {FlexInfer: Breaking Memory Constraint via Flexible and Efficient Offloading for On-Device LLM Inference},
  booktitle = {Proceedings of the 5th Workshop on Machine Learning and Systems},
  series = {EuroMLSys '25},
  year = {2025},
  isbn = {979-8-4007-1538-9},
  publisher = {Association for Computing Machinery},
  address = {New York, NY, USA},
  location = {Rotterdam, Netherlands},
  pages = {56--65},
  numpages = {10},
  doi = {10.1145/3721146.3721961}
}
```

## License and Attribution

This repository is distributed under the MIT License. FlexInfer changes are
released under the same terms unless a source file states otherwise. Portions
of the code are derived from `llama.cpp`, `ggml`, and `gguf-py`; retain their
copyright and permission notices when redistributing source or binary artifacts.
See `NOTICE` and embedded third-party license files for details.
