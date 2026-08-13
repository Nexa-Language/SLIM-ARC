# 工程任务 Prompt：修复 SLIM-ARC 补丁并完成 4GB Pi5 全部可行测试

> 用途：本文件是可直接粘贴给 Agent（如 zoocode 或任意支持工具调用的编程智能体）的**完整任务指令**。
> 执行环境：树莓派 5（4GB RAM，4 核 ARM Cortex-A76，aarch64，microSD，Debian 13 / trixie）。
> 项目规则：见 `AGENT.md`、`ROADMAP.md`、`README.md`、`docs/design/`。

---

## 0. 角色与身份

你是 **SLIM-ARC 项目的 Agent Programmer**，受项目负责人委派，在树莓派 5（4GB）上执行一项"**修复 + 测试**"工程任务。你必须以工程级标准作业：可复现、可追溯、最小改动、全程留痕。

---

## 1. 当前状态（务必先核实，不要假设）

- 仓库已克隆；`src/llama-upstream` 是 upstream llama.cpp（**commit 1c3c967**），vanilla 版已成功编译过（`llama-cli`、`llama-bench` 产物存在）。
- 模型已下载：`data/models/Qwen3-4B-Q4_K_M.gguf`（2,497,280,256 字节 ≈ 2.33GB）。
- **已知问题**：执行 `python3 scripts/apply-slim-arc.py` 后编译 SLIM-ARC 版失败，报错如下：

  ```
  slim_arc::compute_phase has not been declared
  max_layer was not declared in this scope
  slim_arc::prefetch_scheduler has no member named 'effective_window'
  slim_arc::prefetch_scheduler has no member named 'get_cached_experts'
  slim_arc::prefetch_scheduler has no member named 'prefetch_experts'
  slim_arc::prefetch_scheduler has no member named 'cache_router_experts'
  ```

- **根因初判**：`scripts/apply-slim-arc.py` 插入到 `llama-context.cpp` 的代码，调用了 `patches/llama-upstream/` 中 `slim-arc-prefetch.*` 等源文件**尚未实现**的方法/枚举（`compute_phase`、`effective_window`、`get_cached_experts`、`prefetch_experts`、`cache_router_experts` 等）——即"脚本"与"补丁源码"版本不同步。此判断需在 T1 用实际编译日志复核。

---

## 2. 目标（按优先级）

1. **修复补丁**：让 `apply-slim-arc.py` 打补丁后的 llama.cpp 在本机（4GB aarch64）**成功编译**出 `llama-cli` / `llama-bench`。
2. **完成测试**：用 Qwen3-4B 完成当前 4GB 环境下**一切可行**的测试（见 T4 矩阵）。
3. **全程留痕**：所有构建日志、原始测试输出、根因分析、最终总结，一律写入 `docs/test_notes/`。

---

## 3. 硬性约束（违反任一即任务失败）

- **绝不做任何 git 提交 / 推送**：禁止 `git add`、`git commit`、`git push`；禁止改动 `.git` 目录；禁止 `git pull` / `git push` / `git fetch` 等远程交互。全程**只使用工作区（working tree）改动**。
- **不污染远程**：`git remote -v` 保持原样；结束时 `git status` 只允许出现预期的、未暂存的工作区改动。
- **只修复，不重构**：**严禁大刀阔斧修改 SLIM-ARC 的逻辑/机制/架构/接口设计**。只做"最小、外科手术式"修复：补齐缺失声明/方法、对齐脚本与实现、修正明显笔误/作用域问题，且严格保持原设计意图。
- **环境固定不变**：4GB RAM、4 核、microSD、aarch64。编译必须 `-j2`（一旦 OOM 降 `-j1`）；编译前确认 swap ≥ 2GB（zram 已配置）。
- **模型固定**：只用 `Qwen3-4B-Q4_K_M.gguf`。**禁止尝试 80B / OLMoE**（内存不足）。
- **无交互**：所有命令必须非交互执行（`llama-cli` 一律加 `-n <tokens>` 与 `--no-cnv` 等，不得等待键盘输入）。遇到不确定时依据仓库文档自主决策，**不要停下来询问用户**。

---

## 4. 执行规范

- **快照先行**：每次改动文件前，用 `git diff` 或 `cp` 将原文件备份到 `docs/test_notes/backups/`。
- **镜像修复（关键）**：`apply-slim-arc.py` 每次执行都会把 `patches/llama-upstream/` 复制到 `src/llama-upstream/src/`。因此所有对补丁源码的修复**必须同时落在两处**：
  1. `src/llama-upstream/src/slim-arc-*.{h,cpp}` —— 用于本次编译验证；
  2. `patches/llama-upstream/` 同名文件 —— 用于持久化、可复现（仓库已跟踪该目录）。
  - 若需修改 `scripts/apply-slim-arc.py` 本身，同样记录改动。
- **改动标注**：在每个修改点加注释：`// SLIM-ARC FIX <YYYY-MM-DD>: <原因>`。
- **迭代式编译**：改一次 → 编译一次 → 捕获新错误 → 记录 → 继续，直至通过。不要一次堆大量改动。
- **全程日志**：每次编译完整输出保存为 `docs/test_notes/build-slimarc-attempt-N.log`（N 递增）。
- **结果即证据**：每个测试保存原始输出（`raw-*.txt`），总结报告引用这些证据，不要凭记忆填数字。

---

## 5. 任务清单（按顺序一一执行，未完成不允许停止）

### T0 预检与状态快照
- [ ] 记录环境：`uname -m; cat /etc/os-release; free -h; nproc; df -h /; gcc --version; cmake --version`
- [ ] 记录仓库状态：`git status`、`git log -1 --oneline`、`git -C src/llama-upstream rev-parse HEAD`
- [ ] 确认模型存在：`ls -l data/models/Qwen3-4B-Q4_K_M.gguf`
- [ ] 确保 `docs/test_notes/` 与 `docs/test_notes/backups/` 存在
- [ ] 保存修复前基线：`git diff > docs/test_notes/pre-fix.diff`（应接近空）

### T1 精确定位编译失败根因
- [ ] 运行 `python3 scripts/apply-slim-arc.py`
- [ ] 首次构建并保存完整日志：
  ```bash
  cd src/llama-upstream && cmake -B build -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release && \
  cmake --build build --target llama-cli llama-bench -j2 2>&1 | tee ../../docs/test_notes/build-slimarc-attempt-1.log
  ```
- [ ] 逐条解析所有编译错误，分类为：A) SLIM-ARC 内部接口缺失；B) upstream llama.cpp API 漂移（需与 1c3c967 对账）
- [ ] 阅读并核对以下文件，确认脚本调用与实现的差异：
  - `scripts/apply-slim-arc.py`
  - `patches/llama-upstream/slim-arc-prefetch.{h,cpp}`
  - `patches/llama-upstream/slim-arc-unified-scheduler.{h,cpp}`
  - `patches/llama-upstream/slim-arc-kv-eviction.{h,cpp}`
  - `patches/llama-upstream/slim-arc-on-demand.{h,cpp}`
- [ ] 将根因分析写入 `docs/test_notes/root-cause.md`

### T2 最小修复（核心任务）
- [ ] 修复 SLIM-ARC 内部接口不一致：为 `prefetch_scheduler` 补齐 `set_phase` / `effective_window` / `get_cached_experts` / `prefetch_experts` / `cache_router_experts` 及 `compute_phase` 枚举，**实现语义与 `apply-slim-arc.py` 的调用意图一致**（严格按脚本意图，不做超出需要的增强）。
- [ ] 修复 `unified_io_scheduler` 的 `set_phase` / `tick` 与 `max_layer` 作用域问题（若根因涉及）。
- [ ] **同步更新 `patches/llama-upstream/` 对应文件**（镜像规则）。
- [ ] 迭代编译直至通过（记录 `build-slimarc-attempt-N.log`，N ≥ 2），通过后记录产物大小与 CPU 特性检测结果（ARM A76 / crc / crypto / dotprod 等）。
- [ ] 若发现修复必然牵涉大规模重构，**立即回退该方向**，改走最小路径：调整 `apply-slim-arc.py` 插入的调用以匹配现有实现（而非为脚本大规模新增功能），并记录该决策。

### T3 冒烟测试（补丁版）
- [ ] 运行：`llama-cli -m data/models/Qwen3-4B-Q4_K_M.gguf -t 4 -c 128 -p "Hi" -n 8 --no-cnv`，输出存 `docs/test_notes/smoke-slimarc.txt`
- [ ] 确认无崩溃、无 SLIM-ARC 异常输出；验证默认开关与 `SLIM_ARC_DISABLE=1` 下都能正常启动

### T4 完整测试矩阵（Qwen3-4B，4GB）
> 每个用例保存原始输出 `docs/test_notes/raw-<name>.txt` 并记录关键数值；若某项 OOM/超时，如实记录失败原因，最多重试 2 次，不强行循环。
- [ ] 4.1 基础推理（冷/热缓存）：`-t 4 -c 256 -p "The capital of China is" -n 32 --no-cnv`
- [ ] 4.2 性能基准：`llama-bench -m data/models/Qwen3-4B-Q4_K_M.gguf -t 4 -p 64 -n 32 -pg 64,32` 与 `-p 128 -n 64`
- [ ] 4.3 KV 量化：`-ctk q4_0 -ctv q4_0`
- [ ] 4.4 FlashAttention：`-fa auto` 对比 `-fa off`
- [ ] 4.5 上下文伸缩：`-c 512`、`-c 1024`（记录 swap 使用）
- [ ] 4.6 内存/swap 观测：`/usr/bin/time -v` 或轻量监控脚本，记录 RSS 峰值与 swap 使用
- [ ] 4.7 SLIM-ARC 专属项（**预期负面结果，验证不崩溃且不生效**）：
  - MADV_RANDOM：>6GB 才触发，Qwen3-4B 不生效（`SLIM_ARC_NO_MADV_RANDOM` 对照）
  - MoE 预取：Qwen3-4B 为 Dense，不适用
  - `SLIM_ARC_KV_EVICT=1`：短上下文下不触发且不崩溃
  - 记录为"符合预期"，不做强行适配

### T5 汇总报告
- [ ] 撰写 `docs/test_notes/Qwen3-4B-SLIMARC修复与测试报告-<YYYY-MM-DD>.md`，必须包含：环境快照、根因分析、逐项修复清单（文件+改动+原因）、编译结果、完整测试矩阵表（含与既有基线 0.3/0.4 t/s 的对比）、结论、剩余限制（4GB / microSD / CONFIG_MEMCG 缺失）。

### T6 收尾与校验
- [ ] `git status`：确认**无任何暂存/提交/推送**；`git remote -v` 未变
- [ ] 确认 `docs/test_notes/` 下所有产物齐全（日志、raw、报告、root-cause、backups）
- [ ] 输出最终总结：每步做了什么、证据在哪、结论是什么

---

## 6. 完成标准（Definition of Done）

- [ ] 补丁版 `llama-cli` / `llama-bench` 在本机成功编译
- [ ] T4 中所有可执行测试均已执行，结果已保存到 `docs/test_notes/`
- [ ] T5 汇总报告已撰写完成
- [ ] 无任何 git 提交、无远程污染
- [ ] 无逻辑/机制重构，全部为最小修复且已用注释标注

---

## 7. 自律要求

- **不要停下来询问用户**。信息不足时，依据 `AGENT.md`、`README.md`、`ROADMAP.md`、`docs/design/`、`docs/guide/environment.md` 自主决策。
- 你有**充足的时间与预算**，任务未完成不得提前终止。每一步必须输出"做了什么 + 证据 + 下一步"。
- 若某个修复方向会涉及大规模重构，**立即停止该方向**，改走最小修复路径（见 T2 最后一条）。
- 全程遵守第 3 节硬性约束；任何违反 git 约束的行为视为任务失败。
