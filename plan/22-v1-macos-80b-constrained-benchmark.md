# macOS 80B Constrained Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Apple Silicon Mac 上建立可复现的 Linux cgroups v2 测试环境，测出 Qwen3-Next-80B-A3B Q4_K_M 的最低无 swap 可生存/稳定内存、CPU 缩放曲线和当前 SLIM-ARC 消融结果。

**Architecture:** Colima 提供 16 GB RAM、8 vCPU、100 GB 稀疏磁盘的 ARM64 Linux VM，Docker 容器提供每次运行独立的 `memory.max`、`memory.swap.max` 和 CPU quota。模型存放在 VM 本地 ext4，测试控制器在 macOS 侧发起运行，容器内 wrapper 在退出前保存 cgroup、推理和构建元数据。

**Tech Stack:** zsh/bash、Python 3.11+、Colima、Docker Engine/cgroups v2、CMake、llama.cpp `360e134`、Qwen 官方 GGUF。

## Global Constraints

- 模型固定为 `Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF` 的 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`，页面标注约 48.4 GB。
- llama.cpp 固定为 commit `360e134`；不得静默切换到当前 master。
- VM 固定上限为 16 GB RAM、8 vCPU、100 GB 稀疏磁盘。
- 正式内存结果必须设置 cgroup swap 上限为 0；有 swap 的探索结果单独成表。
- 内存阶梯固定 4 vCPU；CPU 阶梯固定最低稳定内存，不同时改变两个自变量。
- 不运行 macOS `memory_pressure`，不修改 macOS 全局内存或 swap 策略。
- 不把 Linux CPU-only 结果描述为 macOS Metal 性能。
- 不把模型、token、凭据或本机敏感信息提交到 Git。
- 执行前使用 Context7 核对当前 Colima、Docker 与 Hugging Face 下载语法。
- 按用户要求最终成果进入单一 `main`；提交保持线性，不创建 merge commit。

---

### Task 1: Host Preflight and Safe Profile Contract

**Files:**
- Create: `scripts/macos/common.sh`
- Create: `scripts/macos/preflight.sh`
- Create: `scripts/macos/campaign.py`
- Create: `tests/macos/test-common.sh`
- Create: `tests/macos/test_campaign.py`
- Modify: `tests/README.md`

**Interfaces:**
- Produces: `slim_arc_repo_root() -> absolute path`、`slim_arc_profile_name() -> "slim-arc"`、`require_command(name)`、`require_free_disk_gib(minimum)`、`assert_safe_result_dir(path)`。
- Produces: `CampaignWindow(started_at: datetime, deadline_at: datetime)`、`remaining_seconds(now: datetime) -> int`、`run_with_deadline(argv: list[str], window: CampaignWindow) -> int`。
- Consumes: no project runtime code.

- [x] **Step 1: Write failing shell tests for path and safety helpers**

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(git rev-parse --show-toplevel)/scripts/macos/common.sh"

test "$(slim_arc_profile_name)" = "slim-arc"
test "$(slim_arc_repo_root)" = "$(git rev-parse --show-toplevel)"
if assert_safe_result_dir "/"; then
    echo "root must be rejected" >&2
    exit 1
fi
assert_safe_result_dir "$(slim_arc_repo_root)/docs/macos_test_notes/2026-08-11"
```

- [x] **Step 2: Run the test and verify it fails before helpers exist**

Run: `bash tests/macos/test-common.sh`

Expected: non-zero exit because `scripts/macos/common.sh` does not exist.

- [x] **Step 3: Write failing persisted-deadline tests**

```python
def test_campaign_has_one_fixed_twelve_hour_deadline(tmp_path: Path) -> None:
    now = datetime(2026, 8, 11, 20, tzinfo=timezone.utc)
    window = CampaignWindow.start(hours=12, now=now)
    window.save(tmp_path / "campaign.json")
    loaded = CampaignWindow.load(tmp_path / "campaign.json")
    assert loaded.deadline_at - loaded.started_at == timedelta(hours=12)
    assert loaded.remaining_seconds(now + timedelta(hours=1)) == 11 * 3600

def test_expired_campaign_refuses_new_process() -> None:
    window = CampaignWindow.start(hours=12, now=datetime(2026, 8, 11, tzinfo=timezone.utc))
    with pytest.raises(CampaignExpired):
        run_with_deadline(["/usr/bin/true"], window, now=datetime(2026, 8, 12, 13, tzinfo=timezone.utc))
```

- [x] **Step 4: Implement the minimum host preflight and campaign helpers**

`preflight.sh` must check, without mutating the host:

```bash
require_command brew
require_free_disk_gib 120
test "$(uname -s)" = "Darwin"
test "$(uname -m)" = "arm64"
sysctl -n hw.memsize
sysctl -n hw.logicalcpu
df -g "$(slim_arc_repo_root)"
```

`assert_safe_result_dir` must accept only descendants of `<repo>/docs/macos_test_notes/` and reject empty strings, `/`, `$HOME`, the repository root and paths containing unresolved `..`.

`campaign.py start --hours 12 --state <path>` creates one immutable UTC deadline. Re-running `start` reads the existing state instead of extending it. `campaign.py run --state <path> -- <argv...>` uses `subprocess.Popen(argv, start_new_session=True)`; at the deadline it sends `SIGTERM` to the owned process group, waits at most 30 seconds, sends `SIGKILL` only to that group, and returns exit code 124. It must never use `shell=True`.

- [x] **Step 5: Run shell syntax and helper tests**

Run: `bash -n scripts/macos/common.sh scripts/macos/preflight.sh tests/macos/test-common.sh && bash tests/macos/test-common.sh && uv run --with pytest pytest -q tests/macos/test_campaign.py && bash scripts/macos/preflight.sh`

Expected: all commands exit 0 and preflight prints only non-sensitive hardware/resource facts.

- [x] **Step 6: Document the macOS test entry point**

Add a `macOS constrained tests` section to `tests/README.md` explaining that `tests/test_env.sh` remains Linux-only and `scripts/macos/preflight.sh` is the host entry point.

- [x] **Step 7: Commit the preflight unit**

```text
[chore] Add macOS benchmark preflight

Root cause: NA
Solution: Add non-mutating host checks and strict result-path guards.
Risks: The preflight requires Apple Silicon and 120 GiB of free disk.
Dependency: NA
Links: docs/superpowers/specs/2026-08-11-macos-constrained-80b-design.md
```

### Task 2: Colima VM Provisioning and cgroups Probe

**Files:**
- Create: `scripts/macos/setup-colima.sh`
- Create: `scripts/macos/probe-guest.sh`
- Create: `tests/macos/test-probe-output.sh`
- Create: `docs/macos_test_notes/README.md`

**Interfaces:**
- Consumes: helpers from Task 1.
- Consumes: fixed 12-hour `campaign.json` created immediately before provisioning.
- Produces: Colima profile `slim-arc`; guest directories `/var/lib/slim-arc/models` and `/var/lib/slim-arc/cache`; machine-readable `guest-probe.env`.

- [x] **Step 1: Write a probe-output fixture test**

```bash
#!/usr/bin/env bash
set -euo pipefail
probe="${1:-/tmp/slim-arc-guest-probe.env}"
cat >"$probe" <<'EOF'
CGROUP_VERSION=2
MEMORY_CONTROLLER=1
SWAP_CONTROLLER=1
ARCH=aarch64
EOF
grep -qx 'CGROUP_VERSION=2' "$probe"
grep -qx 'MEMORY_CONTROLLER=1' "$probe"
grep -qx 'SWAP_CONTROLLER=1' "$probe"
grep -qx 'ARCH=aarch64' "$probe"
```

- [x] **Step 2: Run the fixture test**

Run: `bash tests/macos/test-probe-output.sh`

Expected: PASS.

- [x] **Step 3: Implement idempotent Colima setup**

`setup-colima.sh` must:

1. run Task 1 preflight;
2. install missing packages only with `brew install colima docker`;
3. start the dedicated profile with `colima start --profile slim-arc --arch aarch64 --cpu 8 --memory 16 --disk 100 --runtime docker`;
4. refuse to stop, delete or reconfigure any other profile;
5. create only `/var/lib/slim-arc/{models,cache}` inside the dedicated guest;
6. print the active Docker context and profile status.

- [x] **Step 4: Implement the guest probe**

`probe-guest.sh <result-dir>` must collect:

```bash
stat -fc %T /sys/fs/cgroup
test -f /sys/fs/cgroup/cgroup.controllers
grep -qw memory /sys/fs/cgroup/cgroup.controllers
test -f /sys/fs/cgroup/memory.swap.max
uname -m
df -h /var/lib/slim-arc
docker info --format '{{.CgroupVersion}} {{.Architecture}}'
```

It must normalize these facts into `guest-probe.env` and fail if cgroups v2, memory controller, swap controller or `aarch64` is absent.

- [x] **Step 5: Start the campaign clock, provision, and verify the VM**

Run: `uv run python scripts/macos/campaign.py start --hours 12 --state docs/macos_test_notes/2026-08-11/campaign.json && uv run python scripts/macos/campaign.py run --state docs/macos_test_notes/2026-08-11/campaign.json -- bash scripts/macos/setup-colima.sh && bash scripts/macos/probe-guest.sh docs/macos_test_notes/2026-08-11/preflight`

Expected: profile `slim-arc` is running; the probe records cgroups v2 and at least 100 GB guest disk capacity.

- [x] **Step 6: Commit the isolated VM unit**

```text
[feat] Provision constrained Linux VM

Root cause: NA
Solution: Add an isolated Colima profile and fail-fast cgroups v2 probe.
Risks: The sparse VM disk can grow to 100 GB on the host.
Dependency: Homebrew, Colima, and Docker CLI.
Links: docs/superpowers/specs/2026-08-11-macos-constrained-80b-design.md
```

### Task 3: Reproducible llama.cpp Baseline and Patched Image

**Files:**
- Create: `scripts/macos/Dockerfile.llama`
- Create: `scripts/macos/build-llama-image.sh`
- Create: `scripts/macos/verify-build.sh`
- Test: `tests/macos/test-build-manifest.sh`

**Interfaces:**
- Consumes: `patches/llama-upstream/*`, `scripts/apply-slim-arc.py`, Docker context from Task 2.
- Produces: image `slim-arc-llama:360e134`; `/opt/llama-baseline/build/bin/{llama-cli,llama-bench}`; `/opt/llama-patched/build/bin/{llama-cli,llama-bench}`; `/opt/build-manifest.env`.

- [x] **Step 1: Write a build-manifest validation test**

```bash
#!/usr/bin/env bash
set -euo pipefail
manifest="$1"
grep -qx 'LLAMA_COMMIT=360e134' "$manifest"
grep -qx 'GGML_CPU_REPACK=OFF' "$manifest"
grep -qx 'GGML_METAL=OFF' "$manifest"
grep -qx 'BASELINE_PATCHED=0' "$manifest"
grep -qx 'SLIM_ARC_PATCHED=1' "$manifest"
```

- [x] **Step 2: Implement the multi-stage Dockerfile**

The Dockerfile must clone `https://github.com/ggml-org/llama.cpp.git`, fetch exactly `360e134`, verify `git rev-parse --short HEAD`, and create two source copies. Build both with:

```bash
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CPU_REPACK=OFF \
  -DGGML_METAL=OFF \
  -DLLAMA_CURL=OFF
cmake --build build --parallel 8 --target llama-cli llama-bench
```

Only the patched copy runs `/opt/slim-arc/scripts/apply-slim-arc.py`. The final image retains the two binaries, their dynamic libraries, source commit, patch application log and compiler/CMake versions.

- [x] **Step 3: Implement a bounded temporary build context**

`build-llama-image.sh` must create a `mktemp -d` context, copy only the Dockerfile, `scripts/apply-slim-arc.py` and `patches/llama-upstream/`, build the fixed tag, and remove only that validated temporary directory via a trap. It must not send PDFs, model files, `.git`, build output or `node_modules` to Docker.

- [x] **Step 4: Build and validate both variants**

Run: `uv run python scripts/macos/campaign.py run --state docs/macos_test_notes/2026-08-11/campaign.json -- bash scripts/macos/build-llama-image.sh && bash scripts/macos/verify-build.sh docs/macos_test_notes/2026-08-11/build`

Expected: both `llama-cli --version` commands succeed; patched build log contains `SLIM-ARC integration complete`; manifest test passes.

- [x] **Step 5: Verify patch idempotence in the pinned source**

Run the apply script a second time in a disposable image layer, rebuild `llama-cli`, and compare the patched source tree hash before and after the second application.

Expected: no source diff after the second application and rebuild succeeds.

- [x] **Step 6: Commit the reproducible build unit**

```text
[feat] Build pinned llama variants

Root cause: NA
Solution: Build baseline and SLIM-ARC binaries from llama.cpp 360e134 in one reproducible ARM64 image.
Risks: The image build requires network access and several gigabytes of disk.
Dependency: Colima profile slim-arc.
Links: docs/superpowers/specs/2026-08-11-macos-constrained-80b-design.md
```

### Task 4: Official Model Download, Resume, and Integrity Manifest

**Files:**
- Create: `scripts/macos/download-model.sh`
- Create: `scripts/macos/query_hf_model.py`
- Test: `tests/macos/test_query_hf_model.py`
- Create at runtime only: `docs/macos_test_notes/2026-08-11/model-manifest.json`

**Interfaces:**
- Consumes: Hugging Face model API response for `Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF`.
- Produces: guest file `/var/lib/slim-arc/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`; manifest fields `repo_id`, `revision`, `filename`, `size`, `expected_sha256`, `actual_sha256`, `verified_at`.

- [ ] **Step 1: Write parser tests with a minimal official-API-shaped fixture**

```python
def test_selects_exact_q4_k_m_file() -> None:
    payload = {
        "sha": "4c8630c",
        "siblings": [{
            "rfilename": "Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf",
            "size": 48_400_000_000,
            "lfs": {"sha256": "a" * 64, "size": 48_400_000_000},
        }],
    }
    model = select_model_file(payload)
    assert model.filename.endswith("Q4_K_M.gguf")
    assert model.expected_sha256 == "a" * 64
```

- [ ] **Step 2: Run the parser test and verify it fails**

Run: `uv run --with pytest pytest -q tests/macos/test_query_hf_model.py`

Expected: FAIL because `select_model_file` is not implemented.

- [ ] **Step 3: Implement strict metadata selection**

`query_hf_model.py` must reject missing LFS metadata, a filename mismatch, a non-64-character lowercase SHA-256, a file smaller than 40 GB, or a file larger than 60 GB. It must emit JSON and never print authentication environment variables.

- [ ] **Step 4: Implement resumable guest-local download**

`download-model.sh` must:

1. query `https://huggingface.co/api/models/Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF?blobs=true`;
2. pin the returned model revision in the resolve URL;
3. download inside the guest with `curl --fail --location --retry 5 --continue-at -` to a `.partial` path;
4. verify byte size and `sha256sum` against API LFS metadata;
5. atomically rename `.partial` only after verification;
6. write the small manifest to the repository result directory;
7. refuse to overwrite a complete file whose hash differs.

- [ ] **Step 5: Run unit tests and start/resume the download**

Run: `uv run --with pytest pytest -q tests/macos/test_query_hf_model.py && uv run python scripts/macos/campaign.py run --state docs/macos_test_notes/2026-08-11/campaign.json -- bash scripts/macos/download-model.sh docs/macos_test_notes/2026-08-11`

Expected: parser tests pass; download resumes after interruption; final hash equals the remote LFS SHA-256.

- [ ] **Step 6: Confirm Git ignores the model and partial file**

Run: `git status --short --ignored | rg 'Qwen3-Next|\.partial'`

Expected: no model path is staged or untracked in the repository.

- [ ] **Step 7: Commit the verified download tooling**

```text
[feat] Add verified 80B model download

Root cause: NA
Solution: Download the official Q4_K_M GGUF with revision pinning, resume support, and SHA-256 verification.
Risks: The model consumes about 48.4 GB in the dedicated VM.
Dependency: Hugging Face model API and Colima profile slim-arc.
Links: https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF
```

### Task 5: Container-Side Run Wrapper and cgroup Evidence

**Files:**
- Create: `scripts/macos/container/run-benchmark.sh`
- Modify: `scripts/macos/Dockerfile.llama`
- Create: `tests/macos/test-run-manifest.py`

**Interfaces:**
- Consumes: `VARIANT=baseline|patched`, `MODEL_PATH`, `PP`, `TG`, `THREADS`, `REPETITIONS`, and SLIM-ARC environment switches.
- Produces: `run-manifest.json`, `rep-N.stdout.log`, `rep-N.stderr.log`, `cgroup-before.txt`, `cgroup-after.txt`, `proc-status.txt`, and wrapper exit status under `/results`.

- [ ] **Step 1: Write manifest schema tests**

```python
def test_manifest_has_resource_and_result_fields(manifest: dict[str, object]) -> None:
    assert manifest["memory_limit_bytes"] > 0
    assert manifest["memory_swap_limit_bytes"] == 0
    assert manifest["cpu_quota"] > 0
    assert manifest["llama_commit"] == "360e134"
    assert manifest["variant"] in {"baseline", "patched"}
    assert manifest["outcome"] in {"success", "oom", "timeout", "error"}
```

- [ ] **Step 2: Implement strict wrapper validation**

The wrapper must reject unknown variants, missing model/result mounts, non-positive integer parameters and writable model files. It selects only one of:

```bash
/opt/llama-baseline/build/bin/llama-bench
/opt/llama-patched/build/bin/llama-bench
```

- [ ] **Step 3: Capture cgroup and process evidence before exit**

Read the current container cgroup path from `/proc/self/cgroup`. Save available values from `memory.current`, `memory.peak`, `memory.events`, `memory.stat`, `memory.swap.current`, `cpu.stat`, `io.stat` and pressure files. Missing optional files are recorded as `unsupported`; missing `memory.max` is fatal.

- [ ] **Step 4: Run repetitions inside one container**

Use the pinned binary's `--help` output to map the accepted prompt/generation flags, then run exact `pp` and `tg` values. Preserve all stdout/stderr and use `/usr/bin/time -v` for major/minor faults, RSS, CPU and I/O. Warm repetitions remain in the same cgroup.

- [ ] **Step 5: Test with a tiny fixture before the 80B model**

Run the wrapper with a deterministic fake benchmark executable injected by a test-only image target.

Expected: success manifest, two repetition logs, `memory.max` present and swap limit reported as zero.

- [ ] **Step 6: Commit the evidence wrapper**

```text
[feat] Capture constrained run evidence

Root cause: NA
Solution: Wrap each benchmark with cgroup, process, output, and build metadata capture.
Risks: Kernel-specific optional metrics may be reported as unsupported.
Dependency: Pinned llama image and cgroups v2.
Links: docs/superpowers/specs/2026-08-11-macos-constrained-80b-design.md
```

### Task 6: Host Controller and Resource-Safety Tests

**Files:**
- Create: `scripts/macos/run_constrained.py`
- Create: `tests/macos/test_run_constrained.py`
- Create: `scripts/macos/configs/current-ablation.json`

**Interfaces:**
- Produces: `RunConfig(memory_gib: int, cpus: int, pp: int, tg: int, repetitions: int, timeout_seconds: int, variant: str, env: dict[str, str])`; `run_once(config: RunConfig, result_dir: Path) -> RunResult`.
- Consumes: image/model/profile from Tasks 2–5.

- [ ] **Step 1: Write validation and command-construction tests**

```python
def test_no_swap_docker_limits_are_exact() -> None:
    cfg = RunConfig(memory_gib=8, cpus=4, pp=4, tg=1, repetitions=2, timeout_seconds=1800, variant="patched", env={})
    cmd = build_docker_command(cfg, Path("/results"))
    assert ["--memory", "8g"] == cmd[cmd.index("--memory"):cmd.index("--memory") + 2]
    assert ["--memory-swap", "8g"] == cmd[cmd.index("--memory-swap"):cmd.index("--memory-swap") + 2]
    assert ["--cpus", "4"] == cmd[cmd.index("--cpus"):cmd.index("--cpus") + 2]

def test_rejects_unbounded_or_too_large_values() -> None:
    with pytest.raises(ValueError):
        RunConfig(memory_gib=17, cpus=4, pp=4, tg=1, repetitions=1, timeout_seconds=1, variant="patched", env={}).validate()
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run --with pytest pytest -q tests/macos/test_run_constrained.py`

Expected: FAIL because the controller does not exist.

- [ ] **Step 3: Implement immutable configuration and safe argv construction**

Use `@dataclass(frozen=True)` and `subprocess.run(argv, shell=False, timeout=...)`. Accept only allowlisted SLIM-ARC environment variable names. Container names must include timestamp plus a random suffix and never interpolate user data into a shell command.

- [ ] **Step 4: Implement guest-cache reset and OOM classification**

Cold runs invoke only the dedicated profile:

```text
colima ssh --profile slim-arc -- sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

After the wrapper exits, inspect the stopped container before removal. Classify `State.OOMKilled=true` or an increased `oom_kill` counter as `oom`; classify controller timeout as `timeout`; otherwise preserve exit code and stderr summary.

- [ ] **Step 5: Test command construction, timeout and fake OOM paths**

Run: `uv run --with pytest pytest -q tests/macos/test_run_constrained.py`

Expected: PASS without starting a real VM or Docker daemon.

- [ ] **Step 6: Execute one 12 GB patched smoke run**

Run: `uv run python scripts/macos/run_constrained.py --memory-gib 12 --cpus 4 --pp 4 --tg 1 --repetitions 2 --timeout-seconds 1800 --variant patched --cold-cache --result-dir docs/macos_test_notes/2026-08-11/runs/12g-patched-smoke`

Expected: two valid outputs, no OOM, `memory.swap.current=0`, complete manifest.

- [ ] **Step 7: Commit the safe controller**

```text
[feat] Run cgroup-limited benchmarks

Root cause: NA
Solution: Add a typed controller with exact no-swap limits, hard timeouts, and OOM classification.
Risks: A guest kernel without writable drop_caches fails cold-run setup.
Dependency: Tasks 2 through 5.
Links: docs/superpowers/specs/2026-08-11-macos-constrained-80b-design.md
```

### Task 7: Adaptive Memory Staircase, Stable Tier, and CPU Matrix

**Files:**
- Create: `scripts/macos/run_matrix.py`
- Create: `tests/macos/test_run_matrix.py`
- Create at runtime only: `docs/macos_test_notes/2026-08-11/matrix-state.json`

**Interfaces:**
- Consumes: `run_once` from Task 6.
- Produces: resumable matrix state with per-tier attempts and `lowest_survival_gib`, `lowest_stable_gib`, `stop_reason`.

- [ ] **Step 1: Write the staircase state-machine tests**

```python
def test_descends_to_three_after_four_succeeds_twice() -> None:
    state = MatrixState()
    for outcome in ["success", "success"]:
        state.record(memory_gib=4, outcome=outcome)
    assert state.next_survival_tier() == 3

def test_tests_five_after_four_fails_twice() -> None:
    state = MatrixState()
    for outcome in ["oom", "oom"]:
        state.record(memory_gib=4, outcome=outcome)
    assert state.next_survival_tier() == 5
```

- [ ] **Step 2: Implement checkpointed matrix transitions**

The no-swap survival order is 12 → 8 → 6 → 4 → conditional 3 → conditional 2, or 4 failure → 5. Each tier requires two successes or two failures. A process restart must resume from `matrix-state.json` without repeating completed tiers unless `--rerun` is explicit.

- [ ] **Step 3: Implement the stable-tier search**

Start `pp64 + tg16` at `lowest_survival_gib`, use a 5400-second timeout, and move upward through the already tested tier order until one cold and one warm repetition succeed without OOM.

- [ ] **Step 4: Implement the CPU matrix**

At `lowest_stable_gib`, run 2, 4, 6 and 8 vCPU with matching `THREADS`. Do not run this task if a stable tier was not found.

- [ ] **Step 5: Run unit tests and the 12-hour matrix**

Run: `uv run --with pytest pytest -q tests/macos/test_run_matrix.py && uv run python scripts/macos/run_matrix.py --campaign-state docs/macos_test_notes/2026-08-11/campaign.json --result-root docs/macos_test_notes/2026-08-11`

Expected: the controller stops launching new work at the deadline, terminates the active child through the Task 6 timeout path, and saves a resumable state.

- [ ] **Step 6: Commit the adaptive matrix**

```text
[feat] Automate constrained 80B matrix

Root cause: NA
Solution: Add checkpointed memory, stable-tier, and CPU searches with fixed stopping rules.
Risks: Low-memory tiers can consume most of the 12-hour window through timeouts.
Dependency: Safe constrained-run controller.
Links: docs/superpowers/specs/2026-08-11-macos-constrained-80b-design.md
```

### Task 8: Current-Code Ablation and Evidence Summary

**Files:**
- Create: `scripts/macos/summarize_results.py`
- Create: `tests/macos/test_summarize_results.py`
- Create at runtime: `docs/macos_test_notes/2026-08-11/results.json`
- Create at runtime: `docs/macos_test_notes/2026-08-11/summary.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: all manifests and logs from Tasks 5–7.
- Produces: normalized comparison rows and a human-readable evidence report used as the gate for plans 23 and 24.

- [ ] **Step 1: Write aggregation tests for success, OOM and missing metrics**

```python
def test_selects_lowest_stable_no_swap_tier(rows: list[RunRow]) -> None:
    assert select_lowest_stable(rows).memory_gib == 6

def test_never_promotes_swap_row_to_no_swap_result(rows: list[RunRow]) -> None:
    assert all(row.swap_limit_bytes == 0 for row in no_swap_rows(rows))
```

- [ ] **Step 2: Implement strict log normalization**

Reject duplicate run IDs, model hashes, llama commits or resource limits that disagree within an A/B group. Preserve unsupported metrics as null; do not convert them to zero.

- [ ] **Step 3: Run the existing-feature ablation at the lowest stable tier**

Execute, in this order:

1. upstream baseline;
2. patched default;
3. patched `SLIM_ARC_NO_PREFETCH=1`;
4. patched decode MADV `SEQUENTIAL`;
5. patched decode MADV `NORMAL`;
6. patched decode MADV `RANDOM`;
7. patched `SLIM_ARC_EXPERT_CONF=1`;
8. patched `SLIM_ARC_EXPERT_BUDGET=1` plus confidence gating.

Every row uses the same model hash, stable memory, 4 vCPU, `pp64 + tg16`, one cold run and one warm run. If the 12-hour deadline prevents all rows, stop after item 4 and record the remaining rows as `not_run_due_to_deadline`, not zero.

- [ ] **Step 4: Generate summary and validate claims against raw rows**

The report must state lowest survival/stable memory, no-swap status, CPU curve, best existing config, OOM boundaries and whether prefetch waste/pressure justifies plan 23. Every percentage must name numerator and denominator run IDs.

- [ ] **Step 5: Run tests and repository checks**

Run: `uv run --with pytest pytest -q tests/macos && bash -n scripts/macos/*.sh scripts/macos/container/*.sh && git diff --check`

Expected: all tests pass; summary contains no absolute home path, token or hardware identifier.

- [ ] **Step 6: Record the executed result in ROADMAP**

Add a newest-first entry with the tested model hash, lowest stable tier, completed configurations, failed tiers, links to raw evidence and the decision to start or skip plan 23.

- [ ] **Step 7: Commit the benchmark evidence and summary**

```text
[milestone] Record constrained 80B results

Root cause: NA
Solution: Record reproducible memory, CPU, and current-feature ablation evidence.
Risks: Linux VM CPU results do not represent native Metal throughput.
Dependency: Qwen Q4_K_M model and llama.cpp 360e134.
Links: docs/macos_test_notes/2026-08-11/summary.md
```

### Task 9: Controlled Swap Sensitivity and Final Safety Audit

**Files:**
- Modify: `scripts/macos/run_matrix.py`
- Modify: `scripts/macos/summarize_results.py`
- Modify at runtime: `docs/macos_test_notes/2026-08-11/summary.md`

**Interfaces:**
- Consumes: no-swap failure boundary from Task 7.
- Produces: separately labeled swap rows and a clean host/guest process audit.

- [ ] **Step 1: Add swap-mode command tests**

For `memory_gib=4, swap_gib=2`, assert Docker argv uses `--memory 4g --memory-swap 6g`; reject negative swap and reject swap mode unless `--exploratory-swap` is explicit.

- [ ] **Step 2: Run one controlled swap test only when required**

If 4 GB or a lower no-swap tier failed, run the closest failed tier with 2 GB extra swap. If it still OOMs and deadline remains, run once with 4 GB extra swap. Do not run swap sensitivity when all attempted no-swap tiers succeeded.

- [ ] **Step 3: Keep swap results out of the primary table**

Summary must report physical peak, swap peak, total wall time and slowdown versus the lowest no-swap stable run in a separate `Exploratory swap` section.

- [ ] **Step 4: Audit cleanup without deleting retained artifacts**

Run: `docker ps --filter name=slim-arc-run --format '{{.ID}} {{.Names}}'`, `colima status --profile slim-arc`, and a guest process search for llama binaries. Stop only runner-owned containers that are still active; retain the VM, model, images, cache and logs for resumed testing.

- [ ] **Step 5: Run final verification**

Run: `uv run --with pytest pytest -q tests/macos && bash -n scripts/macos/*.sh scripts/macos/container/*.sh && git diff --check && git status --short`

Expected: no runner-owned process remains; all retained large artifacts are outside Git; repository changes are intentional and documented.

- [ ] **Step 6: Commit the final benchmark state**

```text
[doc] Finalize macOS constrained benchmark

Root cause: NA
Solution: Separate controlled swap sensitivity and record the final process and artifact audit.
Risks: The retained VM and model continue to use host disk capacity.
Dependency: Constrained 80B result matrix.
Links: docs/macos_test_notes/2026-08-11/summary.md
```
