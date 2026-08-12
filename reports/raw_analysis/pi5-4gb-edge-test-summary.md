# SLIM-ARC 树莓派 5（4GB）测试数据整理

> **透明声明**: 本报告整理自 [`docs/pi5_4GB_test_notes/`](../docs/pi5_4GB_test_notes/)（2026-08-04 ~ 08-05）。所有数据均可溯源到该目录的原始 `raw-*.txt` / `smoke-*.txt` 记录与汇总报告。测量存在波动，报告呈现全部数据而非挑选；编译失败、负面结果、数值偏高的原因均如实记录。

## 实验概述

- **目标**: 在树莓派 5（4GB RAM，ARM aarch64，microSD）上**修复 SLIM-ARC 补丁编译问题**，并完成 Qwen3-4B 在当前 4GB 环境**一切可行**的测试。
- **时间线**: 08-04 先做 vanilla 基线（补丁编译失败阶段）→ 08-05 修复补丁后编译成功，跑完整测试矩阵。
- **关键前提**: Qwen3-4B（2.33GB）**小于 6GB 阈值** → SLIM-ARC 核心机制（MADV_RANDOM / MoE 预取 / 统一调度器）**不触发**，实际等价 vanilla llama.cpp + KV q4_0 + FlashAttention 等基础项。

## 环境快照

| 项 | 值 |
|:---|:---|
| 设备 | 树莓派 5（Pi5），4GB RAM，4 核 Cortex-A76，aarch64 |
| CPU 特性 | crc32 / crypto / dotprod（asimddp）；无 AVX2 / i8mm / SVE |
| 系统 | Debian 13 (trixie)，内核；gcc 14.2.0 / cmake 3.31.6 |
| 内存 | 4.0GiB 总，swap 2.0GiB（zram） |
| 存储 | microSD（29G，可用 14-16G），裸读 ~8MB/s（**严重瓶颈**） |
| 内存限制 | cgroup memory 控制器**不可用**（内核无 CONFIG_MEMCG） |
| 模型 | Qwen3-4B-Q4_K_M.gguf（2,497,280,256 字节 ≈ 2.33GB，ModelScope 下载） |
| 推理框架 | upstream llama.cpp（commit 1c3c967）+ SLIM-ARC 补丁 |

---

## 一、08-04 基线测试（vanilla llama.cpp，microSD 冷启动）

> 此阶段 SLIM-ARC 补丁编译失败（见第二节），故先用 vanilla 确认硬件基线。

### 1.1 基础推理（llama-cli，冷启动）

| 指标 | 值 |
|:---|:---|
| Prompt eval | **0.3 t/s**（microSD 冷启动极慢） |
| Generation | **0.4 t/s**（Pi5 4 核 ARM） |
| RSS 内存 | 2.36 GB（56.9%） |
| Swap 使用 | 1.6 GB（严重依赖 swap） |
| 模型加载 | mmap 从 microSD 加载，约 2-3 分钟 |

### 1.2 llama-bench（热缓存）

| 测试 | 速度 |
|:---|:---:|
| pp64（prefill 64 tokens，热缓存） | **3.96 ± 0.56 t/s** |
| tg32（decode 32 tokens） | 待完成 |

> **关键发现**: 热缓存 prefill（3.96）比冷启动（0.3）快约 **13×**——microSD 是冷启动的最大瓶颈，一旦权重进入 page cache 速度显著提升。

### 1.3 与开发机对比

| 指标 | 开发机（i9-13900H, 32GB, NVMe） | Pi5（4GB, microSD） | 比值 |
|:---|:---|:---|:---|
| Prefill | ~13 t/s | 0.3 t/s | ~43× 慢 |
| Decode | ~13 t/s | 0.4 t/s | ~33× 慢 |
| 存储带宽 | ~3.5 GB/s | ~8 MB/s | ~440× 慢 |
| 内存 | 32 GB | 4 GB | 8× 少 |
| CPU | x86 AVX2（14核20线程） | ARM A76（4核） | ~5× 少核 |

### 1.4 SLIM-ARC 优化在 Pi5 上的适用性（预判）

| 优化 | 适用性 | 原因 |
|:---|:---|:---|
| MADV_RANDOM | ❌ 不触发 | 模型 2.4GB < 6GB 阈值 |
| MoE 预取 | ❌ 不适用 | Qwen3-4B 为 Dense |
| KV q4_0 | ⚠️ 可用收益小 | 省内存但 KV 非主要瓶颈 |
| FlashAttention | ✅ 可用 | 纯算法优化 |
| KV Eviction | ⚠️ 可用收益小 | 短上下文不触发 |
| 统一 I/O 调度器 | ❌ 不适用 | 依赖 MoE 稀疏性 |

---

## 二、08-05 补丁修复（关键里程碑）

### 2.1 根因（3 类）

| 类别 | 问题 | 说明 |
|:---|:---|:---|
| A | 脚本与补丁源码接口版本不同步（**主因**） | `apply-slim-arc.py` 调用 `slim-arc-prefetch.*` 中未实现的 `compute_phase`/`set_phase`/`effective_window`/`get_cached_experts`/`prefetch_experts`/`cache_router_experts`/`register_expert_tensor`/`register_mmap_region` 等 |
| B | upstream API/头文件漂移（次要） | 缺 `<climits>` 致 `INT_MAX` 解析失败，级联引发 `max_layer was not declared` |
| C | 脚本生成代码缺陷 | `prefetch_block` 末尾多余 `}` 与 `init_mappings` 原有 `}` 重复 |

### 2.2 修复清单（均为最小修复，`// SLIM-ARC FIX 2026-08-05`）

| 文件 | 改动 |
|:---|:---|
| `patches/llama-upstream/slim-arc-prefetch.h` | 补 `compute_phase` 枚举、全部缺失方法声明、`register_mmap_region`、相关私有成员 |
| `patches/llama-upstream/slim-arc-prefetch.cpp` | 实现上述接口（专家按 `addr+eid*per_expert` 发 WILLNEED） |
| `scripts/apply-slim-arc.py` | `patch_context` 加 `<climits>`；`prefetch_block` 移除多余 `}` |
| 镜像同步 | 重跑脚本自动同步到 `src/llama-upstream/src/`（已验证两处一致） |

### 2.3 编译过程（5 次尝试）

| 尝试 | 结果 |
|:---|:---|
| 1 | 失败：prefetch_scheduler 接口缺失 + INT_MAX |
| 2 | 失败：`init_mappings` 重复 `}` |
| 3 | 失败：UI assets 外网下载卡死（`LLAMA_BUILD_UI=ON`） |
| 4 | 失败：UI embed 校验资产不完整 |
| 5 | **成功（EXIT=0）** |

> 构建规避 UI 下载：`cmake -B build -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF`，产物 `llama-cli` 1,057,936 字节、`llama-bench` 72,608 字节；`libllama.so` 确认 `prefetch_scheduler::*` 与 `kv_eviction_manager::*` 符号注入。

---

## 三、08-05 完整测试矩阵（Qwen3-4B / 4GB，补丁版）

> 命令统一 `--single-turn < /dev/null` + `script` 捕获（该版本 llama-cli 无 `--no-cnv`，UI 走 `/dev/tty`）。

| 用例 | 原始文件 | 参数 | Prompt (t/s) | Generation (t/s) | 关键结论 |
|:---|:---|:---|:---:|:---:|:---|
| 冒烟（默认） | `smoke-slimarc.txt` | `-c 128 -p "Hi" -n 8` | 11.6 | 3.8~4.9 | 正常，无异常 |
| 冒烟（禁用） | `smoke-slimarc-disabled.txt` | `SLIM_ARC_DISABLE=1` | 11.1 | 4.5 | 基线路径正常 |
| 4.1 冷 | `raw-41-basic-cold.txt` | `-c 256 -p "The capital of China is" -n 32` | 9.6 | 4.1 | mmap 正常 |
| 4.1 热 | `raw-41-basic-hot.txt` | 同上（重复） | 11.8 | 4.3 | 热缓存略快 |
| 4.2a | `raw-42-bench-p64n32.txt` | `llama-bench -p 64 -n 32 -pg 64,32` | pp64: **10.16±0.23** | tg32: **3.48±0.13** | 组合 5.33±0.11 |
| 4.2b | `raw-42-bench-p128n64.txt` | `llama-bench -p 128 -n 64` | pp128: **6.88** | tg64: **2.93** | — |
| 4.3 KV 量化 | `raw-43-kv-q4_0.txt` | `-ctk q4_0 -ctv q4_0` | 7.8 | 3.3 | 正常，略降速（省内存） |
| 4.4a FA auto | `raw-44-fa-auto.txt` | `-fa auto` | 6.7 | 3.1 | 短上下文差异小 |
| 4.4b FA off | `raw-44-fa-off.txt` | `-fa off` | 6.3 | 3.1 | 对照 |
| 4.5a ctx512 | `raw-45-ctx512.txt` | `-c 512` | 7.6 | 3.0 | 正常 |
| 4.5b ctx1024 | `raw-45-ctx1024.txt` | `-c 1024` | 7.8 | 2.6 | 正常，未 OOM |
| 4.6 内存 | `raw-46-memory.txt` | 监控脚本 | — | — | **PEAK_RSS = 2,537,888 KB ≈ 2.42 GiB**，未 OOM |
| 4.7a KV_EVICT | `raw-47-kv-evict.txt` | `SLIM_ARC_KV_EVICT=1` | 8.1 | 3.4 | ENABLED，短上下文不触发，不崩溃 |
| 4.7b NO_MADV | `raw-47-no-madv.txt` | `SLIM_ARC_NO_MADV_RANDOM=1` | 6.7 | 3.2 | 无 MADV（<6GB），不崩溃 |

**关于数值的诚实说明**: 任务文档提到的既有基线 0.3/0.4 t/s 对应**冷缓存/更长上下文**；本次短上下文 + 热缓存 + `--single-turn` 下 Generation 为 2.6~4.9 t/s、llama-bench 稳态 tg32/tg64 为 3.48/2.93 t/s——**不代表 SLIM-ARC 带来数量级加速**（Qwen3-4B 在 4GB 下 `model_fits` 判定为真，SLIM-ARC 未激活，本就运行 baseline 路径）。修复验证的核心目标是"编译通过 + 不崩溃 + 无异常"，均已达成。

---

## 四、SLIM-ARC 专属项负面验证（T4.7，全符合预期）

| 项 | 预期 | 实测 | 结论 |
|:---|:---|:---|:---|
| MADV_RANDOM | >6GB 才触发，2.33GB 不生效 | 无 MADV 输出；NO_MADV 无差异 | ✅ |
| MoE 预取 | Dense 不适用 | 无 `_exps` 3D 张量，专家接口不触发 | ✅ |
| KV eviction | 短上下文不触发且不崩溃 | `ENABLED` 输出，无 evicted（seq_len≈34），EXIT 0 | ✅ |

---

## 五、汇总统计（关键指标）

| 指标 | 数值 | 来源 |
|:---|:---|:---|
| 补丁编译 | 5 次尝试后成功（EXIT=0） | §2.3 |
| 短上下文稳态吞吐（热缓存） | pp64 10.16 / tg32 3.48 t/s | §3 |
| 较长上下文吞吐 | pp128 6.88 / tg64 2.93 t/s | §3 |
| RSS 峰值 | 2.42 GiB（<4GB，未 OOM） | §3 |
| KV q4_0 / FA / 上下文伸缩 | 全部正常，短上下文差异小 | §3 |
| SLIM-ARC 专属项 | 全部符合预期（不触发且不崩溃） | §4 |
| 冷启动基线（microSD） | pp 0.3 / tg 0.4 t/s（热缓存 pp 3.96，13×） | §1 |

### 与 RK3588 端侧（8GB）对比

| 维度 | Pi5 4GB（本报告） | RK3588 8GB |
|:---|:---|:---|
| 主模型 | 仅 Qwen3-4B（2.33GB） | Qwen3-4B + OLMoE + **80B** |
| 补丁编译 | 首次修复成功（08-05） | 同批修复，验证可编译 |
| Qwen3-4B decode | tg32 3.48 t/s（--single-turn 热缓存短上下文） | tg16 6.90 t/s（08-05 microSD） |
| SLIM-ARC 核心创新 | 不触发（<6GB） | 80B 触发并确认（RSS ~6.3GB） |
| 存储 | microSD ~8MB/s | microSD 68MB/s → SSD 2.1GB/s |

> 两处数据不可直接横向比较（不同 llama.cpp 版本、不同生成参数、不同缓存状态）；Pi5 4GB 的价值定位为**补丁修复里程碑 + 4GB 极限小模型可行性验证**。

---

## 六、剩余限制

1. **4GB RAM**：无法测 80B / OLMoE，仅覆盖 Qwen3-4B
2. **microSD**：存储带宽 ~8MB/s 是最大瓶颈，冷启动 prefill 0.3 t/s
3. **CONFIG_MEMCG 缺失**：cgroup 内存限制不可用，`model_fits` 逻辑未在真实 cgroup 验证（Qwen3-4B 判为 fits，SLIM-ARC 未激活）
4. **llama-cli 版本差异**：无 `--no-cnv`、UI 走 `/dev/tty`，用 `--single-turn` + `script` 捕获
5. **UI 资产**：外网 SSL 下载失败，编译以 `-DLLAMA_BUILD_UI=OFF` 规避（不影响 CLI/Bench）

## 数据文件索引（docs/pi5_4GB_test_notes/）

- 汇总报告: [`Qwen3-4B-SLIMARC修复与测试报告-2026-08-05.md`](../docs/pi5_4GB_test_notes/Qwen3-4B-SLIMARC修复与测试报告-2026-08-05.md)
- 结果汇总: [`pi5_qwen3_4b_results.md`](../docs/pi5_4GB_test_notes/pi5_qwen3_4b_results.md)
- 根因分析: [`root-cause.md`](../docs/pi5_4GB_test_notes/root-cause.md)
- 原始输出: `smoke-slimarc*.txt`、`raw-41~47-*.txt`（共 16 个）
- 安装/说明: `init_pi5.md`、`pi5.md`、`任务Prompt-修复SLIMARC补丁.md`
