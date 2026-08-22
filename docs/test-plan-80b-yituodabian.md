# SLIM-ARC 80B 模型测试计划 —— 本开发板（yituodabian）

> - **文档版本**: v1.0
> - **创建日期**: 2026-08-11（Asia/Shanghai）
> - **编制依据**: [`docs/rk3588_test_notes/`](rk3588_test_notes/) 实验记录、[`docs/rk3588_improvement/`](rk3588_improvement/) 改进记录、[`scripts/apply-slim-arc.py`](../scripts/apply-slim-arc.py) 源码、[`config/slim-arc.toml`](../config/slim-arc.toml) 配置、[`ROADMAP.md`](../ROADMAP.md)
> - **测试目标板**: 本开发板（主机名/用户 `yituodabian`，工作目录 `/home/yituodabian`）
> - **对照板**: RK3588 开发板（用户 `orangepi`，已完成 80B 实验，记录见 [`docs/rk3588_improvement/`](rk3588_improvement/)）
> - **适用范围**: 仅本板 80B（Qwen3-Next-80B-A3B-Instruct）推理测试与留痕

---

## 1. 测试目标

1. **在本开发板（yituodabian）上完成 Qwen3-Next-80B-A3B-Instruct 模型的 SLIM-ARC 推理测试**，产出可溯源的性能数据（prefill t/s、decode t/s）与消融对比。
2. 复现并验证 RK3588 板已确认的关键结论在本板是否成立：
   - 动态 MADV（prefill=SEQUENTIAL / decode=SEQUENTIAL）消除负优化、追平禁用基线；
   - 专家预取机制正确触发（`[SLIM-ARC-METRICS]` 指标输出）；
   - KV eviction 协同正常、长上下文不 OOM。
3. 产出本板与 RK3588 板的横向对比数据，为比赛报告补充"多板/多架构"证据。
4. 为后续子任务（下载模型到 `/home/yituodabian/data`、源码模型识别改为两板可切换）提供路径、方法与验收依据。

---

## 2. 环境与硬件说明

### 2.1 两块开发板差异（已知 / 待确认）

| 维度 | 对照板 RK3588（orangepi） | 本板（yituodabian） |
|:---|:---|:---|
| 用户/家目录 | `/home/orangepi` | `/home/yituodabian` |
| 架构 | ARM（无 AVX2） | **待确认**（测试首步采集，见 §5.1） |
| 物理内存 | 8 GB（7.8 GiB） | **待确认** |
| CPU 核数 | 4 核可用 | **待确认** |
| 存储/SSD | SSD 读 2.1 GB/s | **待确认**（注意：demo 记录提及"28G 仅剩 17G"，见 [`demo-ui-summary-2026-08-10.md`](rk3588_test_notes/修复记录/demo-ui-summary-2026-08-10.md:27)，需核实本板可用磁盘是否足够容纳 80B 模型） |
| OS 内核 | Linux（RK3588） | Linux 6.18（可能为 WSL2，见 [`ROADMAP.md`](../ROADMAP.md:8) "WSL2 内核 6.18.35.2"） |
| 模型实际路径 | `/home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf` | 计划：`/home/yituodabian/...`（见 §3，**路径待与脚本/配置对齐**） |
| cgroups | slim-arc-low(8G)/mid(12G)/high(16G) | **待确认是否已配置**（见 §5.2） |

> **关键差异提示**：RK3588 为 ARM 无 AVX2、8GB 极端内存比例（45GB/8GB）；本板若为 WSL2/x86（[`docs/guide/environment.md`](guide/environment.md:6) 记载 Intel i9-13900H / 32GB），则内存相对充足，MADV 策略最优解可能不同（decode 可用 RANDOM/NORMAL，见 [`改进记录.md`](rk3588_improvement/改进记录.md:54) 阶段 3）。测试时须按本板实际内存选择 cgroup 档位与 `SLIM_ARC_DECODE_MADV` 取值。

### 2.2 本板环境信息采集（测试前必做，结果写入 §8 记录表）

执行以下命令并将输出存入 `logs/ablation/raw-80b/env-yituodabian-<时间戳>.txt`：

```bash
{
  echo "=== date ===";        date -Iseconds
  echo "=== uname ===";       uname -a
  echo "=== cpu ===";         lscpu | grep -E 'Architecture|Model name|^CPU\(s\)|Thread|MHz'
  echo "=== mem ===";         free -h
  echo "=== disk ===";        df -h /home/yituodabian
  echo "=== ssd bench ===";   sudo hdparm -tT /dev/nvme0n1 2>/dev/null || echo "hdparm N/A"
  echo "=== cgroups ===";     ls /sys/fs/cgroup/ | grep slim-arc || echo "no slim-arc cgroups"
  echo "=== os release ===";  cat /etc/os-release | head -5
  echo "=== kernel wsl ===";  uname -r
} | tee logs/ablation/raw-80b/env-yituodabian-$(date +%Y%m%d-%H%M%S).txt
```

---

## 3. 模型准备

### 3.1 模型名称与来源

| 项 | 值 |
|:---|:---|
| 模型全称 | **Qwen3-Next-80B-A3B-Instruct** |
| 架构 | `qwen3next`（48 层，512 专家 MoE，每 token 激活 10 专家，稀疏率 98%） |
| 主测量化 | **Q4_K_M**，文件 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`，大小 **45.09 GiB**（见 [`phase1-memory-profile-qwen3next-80b.md`](../reports/raw_analysis/phase1-memory-profile-qwen3next-80b.md:13)） |
| 备选量化 | IQ4_XS，文件 `Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf`，约 **40 GB**（见 [`config/slim-arc.toml`](../config/slim-arc.toml:8)、[`ROADMAP.md`](../ROADMAP.md:181)） |
| HuggingFace 来源（GGUF） | `Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF`（Q4_K_M / IQ4_XS 单文件） |
| HuggingFace 来源（原始权重） | `Qwen/Qwen3-Next-80B-A3B-Instruct`（需自行 convert，见 [`environment.md`](guide/environment.md:114)） |

> **来源依据**：[`data/README.md`](../data/README.md:23) 示范了 `huggingface-cli download Qwen/Qwen3-4B-GGUF ...` 模式；[`config/slim-arc.toml`](../config/slim-arc.toml:7) 明确文件名 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`。RK3588 实测使用同文件（[`raw-80b-metrics.txt`](rk3588_test_notes/80b专家预取消融-2026-08-08/raw-80b-metrics.txt:14)）。

### 3.2 下载目标路径

- **任务要求路径**：`/home/yituodabian/data`
- **配置/脚本引用路径**：[`config/slim-arc.toml`](../config/slim-arc.toml:7) 写的是 `data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`（相对于项目根 `/home/yituodabian/SLIM-ARC`，即 `/home/yituodabian/SLIM-ARC/data/models/...`）
- [`scripts/bench/run-80b-bench.sh`](../scripts/bench/run-80b-bench.sh:13) 硬编码 `MODEL="$PROJECT_ROOT/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"`

> ⚠️ **路径不一致（后续子任务依据）**：任务要求下载到 `/home/yituodabian/data`，但脚本/配置期望 `/home/yituodabian/SLIM-ARC/data/models/`。RK3588 板实际把模型放在仓库外 `/home/orangepi/ssd/models/`。**这正是后续"检查源码模型识别是否硬编码并改为两板可切换"子任务的依据**。本测试计划建议：
> - 方案 A（推荐，零改码）：下载到脚本期望路径 `/home/yituodabian/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`，或用软链接 `ln -s /home/yituodabian/data/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf /home/yituodabian/SLIM-ARC/data/models/`。
> - 方案 B（后续子任务）：将 `run-80b-bench.sh` / `config` 的模型路径改为环境变量 `SLIM_ARC_MODEL_80B` 或按主机名自动选择，支持两板切换。**本子任务不实施 B，仅记录**。

### 3.3 下载与校验方式

```bash
# 代理（如需，见 environment.md §4）
export http_proxy=http://127.0.0.1:7897 https_proxy=http://127.0.0.1:7897 no_proxy=localhost,127.0.0.1

# 下载 Q4_K_M（主测，约 45 GiB）
huggingface-cli download Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF \
    Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf \
    --local-dir /home/yituodabian/SLIM-ARC/data/models

# 校验：文件大小 + sha256（HF 页面提供）
ls -lh /home/yituodabian/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
sha256sum /home/yituodabian/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
# 与 HuggingFace 仓库公布的 sha256 比对，记录到 §8 校验表
```

### 3.4 存储占用预估

| 文件 | 大小 | 说明 |
|:---|:---|:---|
| Q4_K_M gguf | 45.09 GiB | 主测，必下 |
| IQ4_XS gguf（备选） | ~40 GiB | 内存极紧张时备选；磁盘不足可跳过 |
| 构建产物 `src/llama-upstream/build/` | ~2-4 GiB | llama-bench/llama-cli/llama-server |
| **合计（仅 Q4_K_M）** | **~48 GiB** | 须确认本板可用磁盘 ≥ 50 GiB |

> ⚠️ 若本板磁盘不足（demo 记录提及 28G 总/17G 剩余），**必须先清理或外挂存储**，不得在磁盘满状态下测试（会导致日志写失败、模型损坏）。

---

## 4. 代码与构建准备

### 4.1 源码模型引用位置清单（后续"硬编码改可切换"子任务依据）

| 文件 | 行 | 引用内容 | 性质 |
|:---|:---|:---|:---|
| [`config/slim-arc.toml`](../config/slim-arc.toml:7) | 7 | `moe_large_q4km = "data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"` | 配置（相对路径） |
| [`config/slim-arc.toml`](../config/slim-arc.toml:8) | 8 | `moe_large_iq4xs = "data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf"` | 配置（相对路径） |
| [`scripts/bench/run-80b-bench.sh`](../scripts/bench/run-80b-bench.sh:13) | 13 | `MODEL="$PROJECT_ROOT/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"` | **硬编码** |
| [`scripts/bench/run-ablation.sh`](../scripts/bench/run-ablation.sh:21) | 21-22 | `DENSE_MODEL` / `MOE_MODEL`（4B/OLMoE，非 80B） | 硬编码（非本次重点） |
| [`scripts/demo/start-demo.sh`](../scripts/demo/start-demo.sh:12) | 12-17 | `LLAMA_DIR` 自动探测两种布局 | 已可切换（demo 修复） |
| [`scripts/demo/llama_cli_server.py`](../scripts/demo/llama_cli_server.py:36) | 36-40 | `LLAMA_CLI` 自动探测 | 已可切换（demo 修复） |
| [`scripts/apply-slim-arc.py`](../scripts/apply-slim-arc.py:22) | 22-24 | `patches_dir` 基于脚本自身位置解析 | 已修复（不再依赖 CWD） |
| RK3588 实测日志 | — | `/home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf` | 仓库外绝对路径 |

> **结论**：`run-80b-bench.sh` 第 13 行的 `MODEL` 是**硬编码相对路径**，未做主机名/环境变量切换。RK3588 板绕过方式是直接改脚本或软链接。后续子任务应将其改为 `SLIM_ARC_MODEL_80B` 环境变量优先、缺省回退当前路径，实现两板可切换。**本子任务不修改，仅记录依据。**

### 4.2 构建步骤（apply-slim-arc.py + cmake）

依据 [`apply-slim-arc.py`](../scripts/apply-slim-arc.py:64) 末尾提示与 [`AGENT.md`](../AGENT.md:20)：

```bash
cd /home/yituodabian/SLIM-ARC

# 1. 确认 upstream 已 clone（独立 git clone，.gitignore 忽略，不被主仓库跟踪）
ls src/llama-upstream/src/llama-bench 2>/dev/null || \
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git src/llama-upstream

# 2. 应用 SLIM-ARC 补丁（幂等，可重复运行）
python3 scripts/apply-slim-arc.py src/llama-upstream
#   预期输出：Step1 复制 8 个 slim-arc 文件（无 WARNING）；Step2-5 各 patch 完成

# 3. 镜像同步校验（red-line：patches/ 与 src/ 必须一致）
for f in slim-arc-prefetch.h slim-arc-prefetch.cpp slim-arc-unified-scheduler.h \
         slim-arc-unified-scheduler.cpp slim-arc-kv-eviction.h slim-arc-kv-eviction.cpp \
         slim-arc-on-demand.h slim-arc-on-demand.cpp; do
  diff -q patches/llama-upstream/$f src/llama-upstream/src/$f || echo "MISMATCH: $f"
done
#   预期：全部一致（8/8 SYNC）

# 4. 编译（纯 CPU，禁用 repack，见 AGENT.md / ROADMAP）
cd src/llama-upstream
mkdir -p build && cd build
cmake -DGGML_CPU_REPACK=OFF -DLLAMA_BUILD_SERVER=ON ..
cmake --build . --target llama-bench llama-cli llama-server -j$(nproc)
#   产物：build/bin/{llama-bench,llama-cli,llama-server}
```

### 4.3 cgroups 配置（若本板未配置）

依据 [`environment.md`](guide/environment.md:50)：

```bash
sudo cgcreate -g memory,cpu:/slim-arc-low
sudo cgcreate -g memory,cpu:/slim-arc-mid
sudo cgcreate -g memory,cpu:/slim-arc-high
echo 8589934592  | sudo tee /sys/fs/cgroup/slim-arc-low/memory.max
echo 12884901888 | sudo tee /sys/fs/cgroup/slim-arc-mid/memory.max
echo 17179869184 | sudo tee /sys/fs/cgroup/slim-arc-high/memory.max
echo "0-3" | sudo tee /sys/fs/cgroup/slim-arc-low/cpuset.cpus
echo "0-5" | sudo tee /sys/fs/cgroup/slim-arc-mid/cpuset.cpus
echo "0-7" | sudo tee /sys/fs/cgroup/slim-arc-high/cpuset.cpus
echo "0"   | sudo tee /sys/fs/cgroup/slim-arc-*/cpuset.mems
```

> 若本板为 WSL2 且内存 32GB，cgroups v2 通常可用；若不可用，记录原因并降级为不限内存的裸跑（在记录中标注）。

---

## 5. 测试步骤（可操作清单）

### 步骤 0：环境采集与前置检查
- [ ] 执行 §2.2 环境采集命令，存日志
- [ ] 确认磁盘可用空间 ≥ 50 GiB（`df -h /home/yituodabian`）
- [ ] 确认 cgroups 是否就绪（`ls /sys/fs/cgroup/ | grep slim-arc`）

### 步骤 1：下载并校验模型
- [ ] 按 §3.3 下载 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`
- [ ] `sha256sum` 校验，结果记入 §8 校验表
- [ ] 确认文件在脚本期望路径（或建立软链接，见 §3.2 方案 A）

### 步骤 2：构建
- [ ] 按 §4.2 执行 `apply-slim-arc.py` + cmake 构建
- [ ] 镜像同步校验 8/8 SYNC
- [ ] `./build/bin/llama-bench --version` 确认可执行

### 步骤 3：基线复现（SLIM_ARC_DISABLE=1，上游基线）
- [ ] 冷启动基线：`sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'`
- [ ] 短上下文：`llama-bench -m <MODEL> -p 32 -n 16 -t <N> -r 2 --no-warmup`（`SLIM_ARC_DISABLE=1`）
- [ ] 长上下文：`llama-bench -m <MODEL> -p 512 -n 128 -t <N> -r 2 --no-warmup`（`SLIM_ARC_DISABLE=1`）
- [ ] 每条命令 `tee` 到 `logs/ablation/raw-80b/80b-yituodabian-baseline-<规格>.txt`

### 步骤 4：SLIM-ARC 全开测试
- [ ] 同规格，去掉 `SLIM_ARC_DISABLE=1`，默认全开（动态 MADV）
- [ ] 短/长上下文各跑，日志 `80b-yituodabian-slimarc-<规格>.txt`
- [ ] 确认 `[SLIM-ARC-METRICS]` 行出现（专家预取指标）

### 步骤 5：消融开关测试（按本板内存选做）
- [ ] `SLIM_ARC_DECODE_MADV=RANDOM` vs `SEQUENTIAL` vs `NORMAL`（参考 [`测试数据.md`](rk3588_improvement/测试数据.md:34) §4）
- [ ] `SLIM_ARC_EXPERT_CONF=1`（置信度门控，RK3588 已验证 WIN，见 [`改进记录.md`](rk3588_improvement/改进记录.md:167) 阶段 12）
- [ ] `SLIM_ARC_EXPERT_BUDGET=1`（预算截断）
- [ ] `SLIM_ARC_KV_EVICT=1`（KV eviction，长上下文）
- [ ] 每组 A/B 交错跑 ≥2 次取均值（参考 [`测试数据.md`](rk3588_improvement/测试数据.md:107) 交错法）

### 步骤 6：端到端生成质量验证
- [ ] `llama-cli` 跑一段开放生成，确认输出连贯、事实正确（参考 [`ROADMAP.md`](../ROADMAP.md:156) 80B demo）
- [ ] 可选：GSM8K 精度（[`scripts/bench/run-gsm8k-api.py`](../scripts/bench/run-gsm8k-api.py)，注意 IQ4_XS+KVq4_0 曾 0% 崩溃，见 [`ROADMAP.md`](../ROADMAP.md:61)）

### 步骤 7：汇总与留痕
- [ ] 填写 §8 结果记录表
- [ ] 更新实验记录文件（§10.4 模板）
- [ ] git add + commit（§10.3）

> **命令模板**（以短上下文 baseline 为例，cgroup low/4 线程）：
> ```bash
> MODEL=/home/yituodabian/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
> LLAMA=/home/yituodabian/SLIM-ARC/src/llama-upstream/build/bin/llama-bench
> LOG=logs/ablation/raw-80b/80b-yituodabian-baseline-pp32-tg16-t4.txt
> sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
> sudo cgexec -g memory,cpu:slim-arc-low env SLIM_ARC_DISABLE=1 \
>   LD_LIBRARY_PATH=$(dirname $LLAMA) timeout 600 $LLAMA \
>   -m "$MODEL" -t 4 -p 32 -n 16 -r 2 --no-warmup 2>&1 | tee "$LOG"
> ```
> 也可直接用 [`scripts/bench/run-80b-bench.sh`](../scripts/bench/run-80b-bench.sh)（注意其硬编码 MODEL 路径与 cgroup 规格，按本板调整）。

---

## 6. 测试用例与验收标准

| 用例 ID | 配置 | 规格 | 验收标准（参考 RK3588 数据） |
|:---|:---|:---|:---|
| TC-01 | baseline（DISABLE=1）短 | pp32/tg16 | 进程不 OOM、产出 pp/tg 数值；记录本板基线 |
| TC-02 | SLIM-ARC 全开 短 | pp32/tg16 | 全开 vs baseline 差距 ≤ ±10%（RK3588 为持平，见 [`测试数据.md`](rk3588_improvement/测试数据.md:48)）；**不得出现 4-6× 负优化**（即不得回退到静态 MADV_RANDOM 行为） |
| TC-03 | baseline 长 | pp512/tg128 | 不 OOM、产出数值 |
| TC-04 | SLIM-ARC 全开 长 | pp512/tg128 | 全开 vs baseline ≤ ±10%；KV eviction（若开）日志 `ENABLED` 且输出连贯 |
| TC-05 | 专家预取指标 | n≥64 | `[SLIM-ARC-METRICS]` 行存在，`hit_rate` 与 `issued` 自洽（hit+waste≈accounted）；temporal 命中率应 ~30%+（RK3588 31%，见 [`raw-80b-ablation-base.txt`](rk3588_test_notes/80b专家预取消融-2026-08-08/raw-80b-ablation-base.txt:33)） |
| TC-06 | CONF=1 | n≥64 | `issued` 较 baseline 下降 ≥40%、`hit_rate` 上升 ≥15pp（RK3588：27.8GB→12.1GB、31%→55%，见 [`raw-80b-ablation-confbud.txt`](rk3588_test_notes/80b专家预取消融-2026-08-08/raw-80b-ablation-confbud.txt:33)） |
| TC-07 | decode MADV 消融 | tg16 | 产出 RANDOM/SEQUENTIAL/NORMAL 三组 tg；记录本板最优（RK3588 为 SEQUENTIAL，本板若内存充足可能不同） |
| TC-08 | 端到端生成 | 开放 prompt | 输出语义连贯、事实正确；不崩溃不截断 |

> **核心验收红线**：TC-02/TC-04 不得出现负优化（全开远慢于 baseline）。若出现，说明动态 MADV 未生效或回退到静态 RANDOM，须排查 `apply-slim-arc.py` 是否正确 patch（参考 [`改进记录.md`](rk3588_improvement/改进记录.md:92) 阶段 5 镜像同步断裂事故）。

---

## 7. 测试数据与结果记录格式

### 7.1 原始日志命名规范

```
logs/ablation/raw-80b/80b-yituodabian-<mode>-<spec>-<tier>.txt
```
- `<mode>`: baseline / slimarc / conf / budget / madv-random / madv-normal
- `<spec>`: pp32-tg16 / pp512-tg128 / n64
- `<tier>`: low / mid / high / nocg（无 cgroup）

示例：`80b-yituodabian-slimarc-pp32-tg16-low.txt`

### 7.2 结果汇总表（填入本板数据，对照 RK3588）

| 配置 | 规格 | 本板 pp (t/s) | 本板 tg (t/s) | RK3588 pp | RK3588 tg | 日志文件 |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| baseline | pp32/tg16 | _待填_ | _待填_ | 2.74 | 1.41 | |
| 全开 | pp32/tg16 | _待填_ | _待填_ | 2.84 | 1.40 | |
| baseline | pp512/tg128 | _待填_ | _待填_ | 6.33 | 2.15 | |
| 全开 | pp512/tg128 | _待填_ | _待填_ | 6.09 | 2.08 | |
| CONF=1 指标 | n64 | issued=_, hit_rate=_ | tg=_ | 12.1GB, 55.4%, 1.9 | | |

### 7.3 模型校验记录表

| 文件 | 大小 | sha256 | 与 HF 一致 | 下载耗时 | 存放路径 |
|:---|:---|:---|:---:|:---|:---|
| Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf | _待填_ | _待填_ | ☐ | _待填_ | _待填_ |

---

## 8. 🔴 红线规则（Red Lines）

> 以下操作**绝对禁止**，违反即中止测试并上报。规则编号 RL-01 ~ RL-12。

| 编号 | 红线内容 | 违反后果 |
|:---|:---|:---|
| **RL-01** | **不得擅自修改已留痕的源代码文件**。`scripts/apply-slim-arc.py`、`patches/llama-upstream/` 下 8 个 slim-arc 文件、`src/llama-upstream/src/` 已 patch 文件，在本测试子任务中**只读**。如需改码须另起子任务并经审核（参考 [`AGENT.md`](../AGENT.md:84) "修改第三方代码后必须 git add -f / patch / 集成脚本"）。 | 代码丢失/镜像断裂（2026-06-23 事故，见 [`ROADMAP.md`](../ROADMAP.md:265)） |
| **RL-02** | **不得覆盖、删除、篡改另一块板（RK3588）的实验记录**。[`docs/rk3588_test_notes/`](rk3588_test_notes/)、[`docs/rk3588_improvement/`](rk3588_improvement/) 下所有文件**只读**；本板数据写入独立目录/独立文件名（含 `yituodabian` 标识）。 | 历史数据丢失、无法横向对比 |
| **RL-03** | **不得修改或删除已下载的模型文件**。模型下载/校验后视为只读；测试期间不得 `rm`、不得覆盖写入。 | 45GB 重新下载、校验失效 |
| **RL-04** | **测试期间不得断电、拔卡、强制重启**。80B 冷启动加载慢（RK3588 曾 36 分钟未完成，见 [`ROADMAP.md`](../ROADMAP.md:510)），中断会导致 page cache 丢失、测试不可复现。 | 测试作废、数据不可比 |
| **RL-05** | **不得在磁盘空间不足（< 5GB 剩余）时继续测试**。日志写失败会丢数据，模型 mmap 写脏页可能损坏。 | 数据丢失/文件损坏 |
| **RL-06** | **不得绕过 `apply-slim-arc.py` 手改 upstream 源码**。所有 SLIM-ARC 修改必须经集成脚本应用，确保 patches/ 与 src/ 镜像同步（[`AGENT.md`](../AGENT.md:88)）。 | 代码不可恢复（2026-06-23 事故根因） |
| **RL-07** | **不得 ignore 已修改的源文件**。`.gitignore` 只能 ignore 构建产物（build/、*.o）和外部依赖（data/models/），不得 ignore 修改过的源文件（[`AGENT.md`](../AGENT.md:83)）。 | WSL 重启丢码（2026-06-23 事故） |
| **RL-08** | **不得无 commit message 提交、不得批量无注释提交**。每次提交须符合 `:<gitmoji>: <type>(<scope>): <subject>`（[`AGENT.md`](../AGENT.md:39)）。 | 历史不可溯源 |
| **RL-09** | **不得在测试中新增核心功能/机制**。本测试只验证已有机制，不新增 C++ HTTP 端点、不改核心调度逻辑（参考 [`demo-ui-summary-2026-08-10.md`](rk3588_test_notes/修复记录/demo-ui-summary-2026-08-10.md:118) red-line #1）。 | 范围蔓延、引入未验证变更 |
| **RL-10** | **不得盲目 `kill -9` 未知 PID**。曾误杀 VSCode Server（[`ROADMAP.md`](../ROADMAP.md:20)）；停服务前先 `ps aux \| grep` 确认。 | 误杀系统进程 |
| **RL-11** | **不得在一条命令链中混合编译+git 提交**。编译耗时长可能导致 git 超时回退（[`AGENT.md`](../AGENT.md:101)）。 | 提交被覆盖回退（2026-06-26 事故） |
| **RL-12** | **冷启动测试前必须 `drop_caches`**。否则 page cache 残留使数据不可复现（RK3588 数据波动根因，见 [`ROADMAP.md`](../ROADMAP.md:207)）。 | 数据虚高、不可比 |

---

## 9. 📝 留痕规则（Traceability）

> 每一步测试都必须可溯源。规则编号 TR-01 ~ TR-08，具体到文件路径与格式。

### TR-01：命令日志保存
- **每条测试命令**执行后，完整 stdout+stderr 用 `| tee <日志路径>` 保存。
- 路径：`logs/ablation/raw-80b/80b-yituodabian-<mode>-<spec>-<tier>-<时间戳>.txt`
- 日志头部必须含：`date -Iseconds`、`uname -a`、模型路径、命令全文、环境变量（`SLIM_ARC_*`）。

### TR-02：环境快照
- 测试开始前执行 §2.2 命令，存 `logs/ablation/raw-80b/env-yituodabian-<时间戳>.txt`。
- 含 CPU/内存/磁盘/cgroups/内核版本。

### TR-03：模型校验留痕
- 下载后 `sha256sum` 输出存 `logs/ablation/raw-80b/model-sha256-<时间戳>.txt`。
- 与 HuggingFace 公布值比对结果记入 §7.3 表。

### TR-04：镜像同步校验留痕
- 每次 `apply-slim-arc.py` 后执行 §4.2 步骤 3 的 `diff` 校验，输出存 `logs/ablation/raw-80b/patch-sync-check-<时间戳>.txt`。
- 必须显示 8/8 SYNC，任何 MISMATCH 须中止。

### TR-05：版本控制留痕
- **所有改动文件必须 `git add` + `commit`**（日志、记录文档、配置）。
- commit message 格式：`:test:(80b-yituodabian): <做了什么>`，如 `:test:(80b-yituodabian): 完成 baseline 短上下文测试并记录日志`。
- **write_to_file 后立即 git add + commit**，不放在长命令链末尾（[`AGENT.md`](../AGENT.md:97)）。
- 每次提交后 `git log --oneline -1` 确认，输出存 `logs/ablation/raw-80b/git-commits-<时间戳>.txt`。

### TR-06：截图/串口输出（若适用）
- 若本板有串口/外接显示，关键步骤（启动、OOM、生成输出）截图存 `docs/rk3588_test_notes/` **之外**的本板目录 `docs/yituodabian_test_notes/screenshots/`。
- 命名：`<时间戳>-<步骤>.png`，如 `20260811-1030-baseline-pp32.png`。
- **不得**存入 `docs/rk3588_test_notes/`（RL-02）。

### TR-07：实验记录文件更新
- 本板实验记录写入新建文件 `docs/yituodabian_test_notes/80b-test-record-<日期>.md`（**新建目录，不混入 rk3588_test_notes**）。
- 模板见 §10.4。
- 每次测试会话结束前更新，含时间戳、配置、数据、结论、异常。

### TR-08：时间戳要求
- 所有日志文件名、记录条目使用 `date +%Y%m%d-%H%M%S`（本地 Asia/Shanghai）。
- 记录文档内每条数据标注测试时刻（ISO 8601 带时区，如 `2026-08-11T10:30:00+08:00`）。

### 9.1 留痕文件目录结构（本板）

```
SLIM-ARC/
├── logs/ablation/raw-80b/              # 原始命令日志（本板文件名含 yituodabian）
│   ├── env-yituodabian-<ts>.txt
│   ├── model-sha256-<ts>.txt
│   ├── patch-sync-check-<ts>.txt
│   ├── 80b-yituodabian-baseline-pp32-tg16-low-<ts>.txt
│   ├── 80b-yituodabian-slimarc-pp32-tg16-low-<ts>.txt
│   └── git-commits-<ts>.txt
└── docs/
    ├── yituodabian_test_notes/         # 本板实验记录（新建，与 rk3588_test_notes 平级）
    │   ├── 80b-test-record-<日期>.md
    │   └── screenshots/
    └── test-plan-80b-yituodabian.md    # 本文档
```

---

## 10. 附录

### 10.1 关键环境变量速查（来自 [`rk3588_improvement/README.md`](rk3588_improvement/README.md:74)）

| 变量 | 默认 | 作用 |
|:---|:---|:---|
| `SLIM_ARC_DISABLE` | 未设 | =1 完全禁用 SLIM-ARC（baseline） |
| `SLIM_ARC_NO_MADV_RANDOM` | 未设 | =1 禁用 MADV 建议 |
| `SLIM_ARC_NO_PREFETCH` | 未设 | =1 禁用预取（保留 MADV） |
| `SLIM_ARC_DYNAMIC_MADV` | 启用 | =0 禁用动态切换 |
| `SLIM_ARC_DECODE_MADV` | SEQUENTIAL | decode 建议：SEQUENTIAL/RANDOM/NORMAL |
| `SLIM_ARC_EXPERT_CONF` | 关闭 | =1 置信度门控（**推荐开启**） |
| `SLIM_ARC_EXPERT_BUDGET` | 关闭 | =1 专家预算截断 |
| `SLIM_ARC_EXPERT_POP` | 0 | K=热门专家并集（**不建议**） |
| `SLIM_ARC_KV_EVICT` | 未设 | =1 启用 KV eviction |
| `SLIM_ARC_KV_SINK` | 4 | attention sink token 数 |
| `SLIM_ARC_KV_WINDOW` | 1024 | KV 滑动窗口 |

### 10.2 RK3588 关键基线数据（对照用，来自 [`测试数据.md`](rk3588_improvement/测试数据.md)）

| 配置 | pp32 | tg16 | pp512 | tg128 |
|:---|:---:|:---:|:---:|:---:|
| 全开（改进后） | 2.84 | 1.40 | 6.09 | 2.08 |
| 禁用（baseline） | 2.74 | 1.41 | 6.33 | 2.15 |
| 全开（改进前，静态 RANDOM） | 0.44 | 0.26 | 2.41 | 0.53 |

### 10.3 模型架构速查（来自 [`phase1-memory-profile-qwen3next-80b.md`](../reports/raw_analysis/phase1-memory-profile-qwen3next-80b.md)）

- 架构 `qwen3next`，48 层，512 专家，每 token 激活 10，稀疏率 98%
- 总张量 45.08 GiB，专家张量 43.59 GiB（144 个），非专家 1.49 GiB
- 每层 ~953 MiB；完美预测可省 98% 带宽

### 10.4 本板实验记录文件模板

```markdown
# 80B 测试记录 —— yituodabian（<日期>）

- 测试人：
- 测试时段：<ISO 8601 起止>
- 环境：CPU=, 内存=, 磁盘=, 内核=, cgroup=

## 模型
- 文件：Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
- sha256：<填>
- 路径：<填>

## 测试数据
| 时间 | 配置 | 规格 | tier | pp | tg | 日志文件 | 备注 |
|:---|:---|:---|:---|:---:|:---:|:---|:---|

## 指标（SLIM-ARC-METRICS）
| 配置 | samples | issued(MB) | hit(MB) | waste(MB) | hit_rate | tg |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|

## 结论
- 全开 vs baseline：<填>
- 是否负优化：<是/否>
- 与 RK3588 对比：<填>

## 异常
- <无 / 描述>

## git 留痕
- commit hash：<填>
```

---

## 11. 后续子任务依据（本计划产出，供后续执行）

1. **下载模型到 `/home/yituodabian/data`**：见 §3，模型 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`（45 GiB），来源 `Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF`。注意路径与脚本期望对齐（§3.2 方案 A 软链接 / 方案 B 改码）。
2. **检查源码模型识别是否硬编码并改为两板可切换**：见 §4.1 清单，核心硬编码点为 [`scripts/bench/run-80b-bench.sh`](../scripts/bench/run-80b-bench.sh:13) 第 13 行 `MODEL`；建议改为 `SLIM_ARC_MODEL_80B` 环境变量优先 + 主机名回退。RK3588 板用 `/home/orangepi/ssd/models/`，本板用 `/home/yituodabian/...`。
3. **本板硬件确认**：见 §2.2，首步采集；若为 WSL2/x86 32GB，MADV 最优策略可能与 RK3588（ARM 8GB）不同，须消融验证（TC-07）。
