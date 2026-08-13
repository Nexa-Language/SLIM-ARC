# Qwen3-4B SLIM-ARC 补丁修复与测试报告

> 日期：2026-08-05（UTC+8）
> 执行环境：树莓派 5（4GB RAM / 4 核 Cortex-A76 / microSD / Debian 13 trixie / aarch64）
> 依据任务文档：`docs/pi5_4GB_test_notes/2026-08-05-修复与测试归档/任务Prompt-修复SLIMARC补丁.md`（T0~T6）
> 归档说明：2026-08-13 目录整理，本报告及配套文件已从 `docs/pi5_4GB_test_notes/` 根目录移入本归档目录。

---

## 1. 环境快照（T0）

- **架构**：`aarch64`；`CPU part: 0xd0b`（Cortex-A76）
- **系统**：Debian GNU/Linux 13 (trixie)，gcc 14.2.0，cmake 3.31.6
- **内存**：4.0 GiB 总 / 2.0 GiB swap（zram）
- **存储**：`/dev/mmcblk0p2` 29G（14G 已用 / 14G 可用），microSD
- **仓库**：主仓库 `git log -1` = `12aaa969`；upstream `src/llama-upstream` HEAD = **`1c3c9674de4d455f1e571bed808252af54932767`**
- **模型**：`data/models/Qwen3-4B-Q4_K_M.gguf`（2,497,280,256 字节 ≈ 2.33 GB）
- **CPU 特性**（`/proc/cpuinfo` + 编译 flags）：`crc32`、`crypto`（aes/pmull/sha1/sha2）、`dotprod`（asimddp）——对应 `-mcpu=cortex-a76+crc+crypto+dotprod`
- **证据**：T0 中间产物（`t0-environment-snapshot.txt`、`pre-fix.diff`、`backups/`）已按清理要求移除，关键信息保留于本报告与 [`root-cause.md`](root-cause.md)

---

## 2. 根因分析（T1）

首次运行 `python3 scripts/apply-slim-arc.py` 后编译失败，错误全部集中在 `llama-context.cpp` 的 `graph_compute`。完整编译日志当时保存为 `build-slimarc-attempt-N.log`（现按清理要求移除，属中间过程），关键错误分类见下。分类：

### A 类：脚本与补丁源码接口版本不同步（主因）
`apply-slim-arc.py` 插入的代码调用了 `patches/llama-upstream/slim-arc-prefetch.{h,cpp}` **尚未实现**的接口：

| 缺失项 | 类型 | 调用位置 | 修复语义 |
|---|---|---|---|
| `slim_arc::compute_phase` 枚举（PREFILL/DECODE） | 枚举 | llama-context.cpp:2513 | 阶段标识 |
| `prefetch_scheduler::set_phase(compute_phase)` | 方法 | llama-context.cpp:2513 | 记录阶段 |
| `prefetch_scheduler::effective_window()` | 方法 | llama-context.cpp:2501/2518 | 返回窗口 `window_` |
| `prefetch_scheduler::get_cached_experts(layer,&n)` | 方法 | llama-context.cpp:2507/2524 | 返回某层缓存路由专家 |
| `prefetch_scheduler::prefetch_experts(layer,exps,n)` | 方法 | llama-context.cpp:2508/2525 | 对指定专家发 WILLNEED |
| `prefetch_scheduler::cache_router_experts(layer,exps,n)` | 方法 | llama-context.cpp:2560 | 缓存路由专家 ID |
| `prefetch_scheduler::register_expert_tensor(...)` | 方法 | llama-model-loader.cpp | 注册 3D 专家张量 |
| `prefetch_scheduler::set_memory_budget(size_t)` | 方法 | unified-scheduler.cpp:80 | 记录权重带宽预算 |
| `slim_arc::register_mmap_region(void*,size_t)` | 全局函数 | llama-model-loader.cpp | mmap 区域注册（补丁中完全缺失） |

### B 类：upstream API/头文件漂移（次要）
- 脚本只加了 `<vector>`，但插入代码使用 `INT_MAX`，需 `<climits>`。**该缺失导致 `int min_layer=INT_MAX, max_layer=-1;` 声明解析失败，进而引发全部 `max_layer was not declared` 级联错误**（本报告核对真实日志后确认）。

### C 类：脚本生成的代码缺陷
- `prefetch_block` 以函数结尾 `}` 收尾，但 `replace` 只插入不删除原有 `}`，导致 `init_mappings` 出现**重复 `}`**（`expected declaration before '}'`，attempt-2）。

详细分析见 [`root-cause.md`](root-cause.md)。

---

## 3. 逐项修复清单（T2）

所有改动均标注 `// SLIM-ARC FIX 2026-08-05: <原因>`，严格最小修复，无逻辑/机制重构。

| # | 文件 | 改动 | 原因 |
|---|---|---|---|
| 1 | [`patches/llama-upstream/slim-arc-prefetch.h`](patches/llama-upstream/slim-arc-prefetch.h) | 新增 `compute_phase` 枚举；声明 `set_phase`/`effective_window`/`set_memory_budget`/`register_expert_tensor`/`cache_router_experts`/`get_cached_experts`/`prefetch_experts`；声明全局 `register_mmap_region`；新增私有成员（`phase_`/`memory_budget_`/`expert_tensors_by_layer_`/`cached_experts_by_layer_`） | 对齐脚本调用意图 |
| 2 | [`patches/llama-upstream/slim-arc-prefetch.cpp`](patches/llama-upstream/slim-arc-prefetch.cpp) | 实现 `register_mmap_region`、`register_expert_tensor`、`cache_router_experts`、`get_cached_experts`、`prefetch_experts`（对选中专家地址段发 `posix_madvise(WILLNEED)`） | 补齐脚本所需实现 |
| 3 | [`scripts/apply-slim-arc.py`](scripts/apply-slim-arc.py) | `patch_context` 增加 `<climits>`（独立幂等判断）；`prefetch_block` 移除末尾多余 `}` | 修复 INT_MAX 级联错误 + init_mappings 重复 `}` |
| 4 | [`src/llama-upstream/src/llama-model-loader.cpp`](src/llama-upstream/src/llama-model-loader.cpp) | 删除多余 `}`（由修复后的脚本重跑可复现） | 工作区修复 |

**镜像规则**：对 `patches/` 的修复通过重新运行 `apply-slim-arc.py` 自动同步到 `src/llama-upstream/src/`（已验证 `grep` 确认 `climits`、`compute_phase`、各新方法均出现在两处）。

---

## 4. 编译结果（T2）

| 尝试 | 结果 |
|---|---|
| 1 | 失败：prefetch_scheduler 接口缺失 + INT_MAX |
| 2 | 失败：llama-model-loader.cpp 重复 `}` |
| 3 | 失败：UI assets 下载卡死（LLAMA_BUILD_UI=ON，外网 SSL 失败） |
| 4 | 失败：UI embed 校验占位资产不完整 |
| 5 | **成功**（`BUILD_EXIT_CODE=0`） |

> 注：5 份完整编译日志 `build-slimarc-attempt-{1..5}.log` 当时已保存，现按清理要求移除（属中间过程）；各尝试结果摘要见上表与 [`root-cause.md`](root-cause.md)。

**构建命令**（规避 UI 下载，仅需 CLI/Bench 无需 Web UI）：
```bash
cmake -B build -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build build --target llama-cli llama-bench -j2
```

**产物**：
- `build/bin/llama-cli`：1,057,936 字节
- `build/bin/llama-bench`：72,608 字节
- `libllama.so` 符号确认：`prefetch_scheduler::prefetch_experts / cache_router_experts / register_expert_tensor / notify_layer_compute`、`kv_eviction_manager::*` 全部注入

**测试方法备注**：该 llama.cpp 版本（1c3c967）的 `llama-cli` 对话 UI 直接写 `/dev/tty`（`> file` 重定向与 `--log-file` 均无法捕获，仅 `script` 能记录完整原始输出）；且参数为 `--single-turn`（`--no-cnv` 不存在）。所有推理测试统一使用 `--single-turn < /dev/null` + `script` 捕获。

---

## 5. 完整测试矩阵（T3 + T4，Qwen3-4B / 4GB）

> 所有原始输出保存在 `docs/pi5_4GB_test_notes/2026-08-05-修复与测试归档/原始数据/`（`raw-*.txt` 与 `smoke-*.txt`）。`EXIT=0` 均指 `COMMAND_EXIT_CODE="0"`。

| 项 | 用例 | 参数 | Prompt t/s | Generation t/s | 关键结论 |
|---|---|---|---|---|---|
| T3 冒烟（默认） | `smoke-slimarc.txt` | `-c 128 -p "Hi" -n 8 --single-turn` | 11.6 | 3.8~4.9 | 正常启动/生成/退出，无 SLIM-ARC 异常 |
| T3 冒烟（禁用） | `smoke-slimarc-disabled.txt` | `SLIM_ARC_DISABLE=1` | 11.1 | 4.5 | 同基线路径，正常 |
| 4.1 冷 | `raw-41-basic-cold.txt` | `-c 256 -p "The capital of China is" -n 32` | 9.6 | 4.1 | 冷启动 mmap 正常 |
| 4.1 热 | `raw-41-basic-hot.txt` | 同上（重复运行） | 11.8 | 4.3 | 热缓存略快 |
| 4.2a | `raw-42-bench-p64n32.txt` | `llama-bench -p 64 -n 32 -pg 64,32` | pp64: **10.16** | tg32: **3.48** | pp64+tg32: 5.33 |
| 4.2b | `raw-42-bench-p128n64.txt` | `llama-bench -p 128 -n 64` | pp128: **6.88** | tg64: **2.93** | — |
| 4.3 KV 量化 | `raw-43-kv-q4_0.txt` | `-ctk q4_0 -ctv q4_0` | 7.8 | 3.3 | 量化 KV 正常，略降速（省内存） |
| 4.4a FA auto | `raw-44-fa-auto.txt` | `-fa auto` | 6.7 | 3.1 | 短上下文差异小 |
| 4.4b FA off | `raw-44-fa-off.txt` | `-fa off` | 6.3 | 3.1 | 对照 |
| 4.5a ctx512 | `raw-45-ctx512.txt` | `-c 512` | 7.6 | 3.0 | 正常 |
| 4.5b ctx1024 | `raw-45-ctx1024.txt` | `-c 1024` | 7.8 | 2.6 | 正常，未 OOM（2.6G available） |
| 4.6 内存 | `raw-46-memory.txt` | 监控脚本 | — | — | **PEAK_RSS = 2,537,888 KB ≈ 2.42 GiB**，未 OOM |
| 4.7a KV_EVICT | `raw-47-kv-evict.txt` | `SLIM_ARC_KV_EVICT=1` | 8.1 | 3.4 | hook ENABLED，短上下文**不触发**，不崩溃 |
| 4.7b NO_MADV | `raw-47-no-madv.txt` | `SLIM_ARC_NO_MADV_RANDOM=1` | 6.7 | 3.2 | 无 MADV 触发（<6GB），不崩溃 |

### 与既有基线对比
- 任务文档提及既有 Qwen3-4B 基线约 **0.3 / 0.4 t/s**（见同目录 [`pi5_qwen3_4b_results.md`](pi5_qwen3_4b_results.md)）。
- 本次短上下文 + 页面缓存热 + `--single-turn` 下，llama-cli 报告的 Generation 为 **2.6~4.9 t/s**；`llama-bench` 的稳态指标 tg32/tg64 为 **3.48 / 2.93 t/s**。
- 说明：0.3/0.4 t/s 基线对应冷缓存/更长上下文/更完整生成路径，本次数值偏高主要因短上下文与热缓存，**不代表 SLIM-ARC 带来数量级加速**（Qwen3-4B 在 4GB 下 `model_fits` 判定为真，SLIM-ARC 未激活，本就运行 baseline 路径）。修复验证的核心目标是"编译通过 + 不崩溃 + 无异常"，均已达成。

---

## 6. SLIM-ARC 专属项负面验证结论（T4.7）

| 项 | 预期 | 实测 | 结论 |
|---|---|---|---|
| MADV_RANDOM | >6GB 触发；Qwen3-4B（2.33GB）不生效 | 无 MADV 相关输出；`SLIM_ARC_NO_MADV_RANDOM=1` 无差异 | ✅ 符合预期 |
| MoE 预取 | Qwen3-4B 为 Dense，不适用 | 无 `_exps` 3D 张量，`register_expert_tensor`/`prefetch_experts` 不触发 | ✅ 符合预期 |
| KV eviction | 短上下文不触发且不崩溃 | `SLIM_ARC_KV_EVICT=1` 输出 `ENABLED`，无 `evicted`（seq_len≈34 < sink4+window1024），EXIT 0 | ✅ 符合预期 |

---

## 7. 结论

1. **补丁修复成功**：`apply-slim-arc.py` 打补丁后的 llama.cpp 在 4GB aarch64 上成功编译出 `llama-cli` 与 `llama-bench`（`EXIT=0`）。
2. **修复为最小改动**：仅补齐 prefetch_scheduler 缺失接口（严格按脚本调用意图）、增加 `<climits>`、修正 `init_mappings` 重复 `}`、补充 `register_mmap_region`；未改动 SLIM-ARC 任何机制/架构。
3. **镜像可复现**：`patches/llama-upstream/` 与 `scripts/apply-slim-arc.py` 已更新，重新运行脚本可完整复现；工作区 `src/` 同步生效。
4. **Qwen3-4B 在 4GB 环境下全部可行测试通过**：无崩溃、无 OOM、无 SLIM-ARC 异常输出；SLIM-ARC 专属项均为符合预期的负面结果。
5. **全程无 git 提交/推送**，仅工作区改动（见 T6 校验）。

---

## 8. 剩余限制（如实记录）

- **4GB RAM**：无法测试 80B / OLMoE（内存不足），本报告仅覆盖 Qwen3-4B。
- **microSD**：存储 29GB，swap 压力下 decode 较慢（0.3~0.4 t/s 量级基线）。
- **CONFIG_MEMCG 缺失**：cgroup 内存限制不可用，`model_fits`（<60% memory.max）逻辑无法在真实 cgroup 下验证，本次因 Qwen3-4B 判定为 fits 而未激活 SLIM-ARC。
- **`/usr/bin/time` 未安装**：T4.6 以轻量 `/proc/PID/status` 监控脚本记录 RSS 峰值替代。
- **llama-cli 参数差异**：该版本无 `--no-cnv`，且 UI 输出走 `/dev/tty`；统一改用 `--single-turn` + `script` 捕获。
- **UI 资产**：外网 SSL 下载失败，编译以 `-DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF` 规避（不影响 `llama-cli`/`llama-bench`）。

---

## 9. 产物清单（docs/pi5_4GB_test_notes/2026-08-05-修复与测试归档/，清理后）

- 测试说明：`任务Prompt-修复SLIMARC补丁.md`、`root-cause.md`、`环境准备与文档/init_pi5.md`、`环境准备与文档/pi5.md`
- 汇总报告：`Qwen3-4B-SLIMARC修复与测试报告-2026-08-05.md`
- 结果汇总：`pi5_qwen3_4b_results.md`
- 原始输出：`原始数据/smoke-slimarc.txt`、`原始数据/smoke-slimarc-disabled.txt`、`原始数据/raw-41~47-*.txt`
- 已清理（中间过程/debug）：`build-slimarc-attempt-{1..5}.log`、`t0-environment-snapshot.txt`、`t1-apply-slim-arc.txt`、`pre-fix.diff`、`backups/`
