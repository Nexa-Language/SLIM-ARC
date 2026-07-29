# Benchmarking

FlexInfer provides `flexinfer-bench`, a prefetch-aware benchmark binary based on
the upstream `llama-bench` workflow. The helper scripts are intended for repeated
Linux host and Android runs where thermal state and CPU frequency matter.

## Direct Benchmark Command

After a host build:

```bash
LD_LIBRARY_PATH=host/lib ./host/bin/flexinfer-bench \
  -m hf-models/model-q4_0.gguf \
  -p 16 -n 16 -am 2 -tp 1
```

After an Android build, run the matching Android binary on an Android device or
inside a Termux environment:

```bash
LD_LIBRARY_PATH=android/lib ./android/bin/flexinfer-bench \
  -m hf-models/model-q4_0.gguf \
  -p 16 -n 16 -am 2 -tp 1
```

## Benchmark Helper

`scripts/bench-speed.sh` expects the build tree, scripts, and model directory to
be available on the host or Android device. It records benchmark output, thermal
zones, and CPU frequency state into one result file per model.

Example from a Linux or Android shell:

```bash
cd /path/to/FlexInfer
AM=8 TP=2 P=16 N=16 bash scripts/bench-speed.sh
```

Limit a run to selected models by passing GGUF file names relative to
`MODEL_PREFIX`:

```bash
MODEL_LIST="ggml-model-llama-2-7b-chat-q4_0.gguf ggml-model-llama-2-70b-chat-q4_0.gguf" \
AM=2 TP=2 T=48 P=16 N=16 bash scripts/bench-speed.sh
```

For cold-cache Linux runs with a CPU affinity and a memory cgroup:

```bash
sudo cgcreate -g memory:/limmem
echo 2147483648 | sudo tee /sys/fs/cgroup/limmem/memory.max
DROP_CACHES=1 CGROUP_SPEC=memory:limmem TASKSET_CPUS=4-7 \
  AM=2 TP=2 P=16 N=16 bash scripts/bench-speed.sh
```

On rooted Android devices, provide the cache-drop command explicitly:

```bash
DROP_CACHES=1 \
DROP_CACHES_CMD="su -c 'sync; echo 3 > /proc/sys/vm/drop_caches'" \
TASKSET_CPUS=4-7 AM=2 TP=2 P=16 N=16 bash scripts/bench-speed.sh
```

Run a memory-budget sweep:

```bash
MEMORY_CONFIGS="0.5 1 2 4" TP=4 P=16 N=16 bash scripts/bench-speed-memory-sweep.sh
```

The default model directory is `hf-models/`, and the default output directory is
`bench-results/`. Both are ignored by git.

## Configuration

Common environment variables:

- `BUILD_PREFIX`: install tree containing `bin/` and `lib/`; defaults to
  `android/` on Android devices when available, otherwise `host/`.
- `EXEC_PATH`: directory containing benchmark binaries; defaults to
  `$BUILD_PREFIX/bin`.
- `LLAMA_LIBRARY_PATH`: library directory; defaults to `$BUILD_PREFIX/lib`.
- `BENCH_BIN`: benchmark binary to run. If unset, the script prefers
  `flexinfer-bench`, then `llama-bench`.
- `MODEL_PREFIX`: directory containing GGUF models; defaults to `hf-models/`.
- `MODEL_LIST`: optional space-separated GGUF file names relative to
  `MODEL_PREFIX`. If unset, the built-in benchmark model list is used.
- `RESULT_DIR`: benchmark output directory; defaults to `bench-results/`.
- `P`: prompt tokens passed to the benchmark; defaults to `16`.
- `N`: generated tokens passed to the benchmark; defaults to `16`.
- `T`: optional CPU thread count passed to `llama-bench` or
  `flexinfer-bench` with `-t`. If unset, the benchmark binary default is used.
- `AM`: available memory budget in GB; defaults to `8`. Fractional budgets
  such as `0.5` are supported.
- `TP`: prefetch thread count; defaults to `2`. Set `TP=0` to benchmark the
  synchronous read path without threaded prefetching.

Cooldown controls:

- `COOLDOWN_SECONDS`: initial sleep before each benchmark; defaults to `300`.
- `COOLDOWN_CHECK_INTERVAL`: polling interval after the initial sleep; defaults
  to `10`.
- `COOLDOWN_MAX_WAIT_SECONDS`: maximum cooldown wait; defaults to `1800`.
- `COOLDOWN_TEMP_C`: maximum accepted thermal-zone temperature; defaults to
  `45`.
- `COOLDOWN_MIN_FREQ_RATIO`: minimum accepted CPU max-frequency ratio in percent;
  defaults to `95`.

Experiment-control variables:

- `DROP_CACHES`: set to `1` to clear the Linux page cache immediately before
  each benchmark. The default is `0`.
- `DROP_CACHES_CMD`: optional device-specific cache-drop command. This is useful
  on rooted Android devices, where direct writes to `/proc/sys/vm/drop_caches`
  usually require `su`.
- `TASKSET_CPUS`: optional CPU list passed to `taskset -c`, for example `4-7`.
- `NUMACTL_ARGS`: optional arguments passed to `numactl`, for example
  `--cpunodebind=0 --membind=0`.
- `CGROUP_SPEC`: optional cgroup passed to `cgexec -g`, for example
  `memory:limmem`.
- `RUN_PREFIX`: optional command prefix inserted before the benchmark command,
  for local wrappers such as `perf stat --`.

For FlexInfer cold-start and I/O-sensitive comparisons, use cold-cache runs when
possible. Without cache control, repeated benchmark invocations may reuse Linux
page cache state, especially for mmap-based baselines. FlexInfer's Linux
direct-I/O tensor path reduces page-cache effects for streaming reads, but
baseline and metadata paths can still be affected.

## Output

For each model present in `MODEL_PREFIX`, the helper writes:

```text
bench-results/<model>.p<P>_n<N>[_t<T>]_am<AM>_tp<TP>.txt
```

Each result file contains the model path, benchmark command, benchmark table,
exit status, thermal readings, and CPU frequency readings. Missing model files
are skipped.

## Model List

The default benchmark suite is defined by `DEFAULT_MODEL_PATH_LIST` in
`scripts/bench-speed.sh`. Use `MODEL_LIST` for one-off subsets, or set up
symlinks in `MODEL_PREFIX` to match the built-in names.
