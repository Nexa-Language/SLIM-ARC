RK3588 端侧测试的工程级 prompt 已在终端输出（heredoc 打印，未创建/修改任何项目文件）。以下为完整可复制内容，供直接使用：

```
================================================================================
RK3588 端侧测试任务 Prompt（工程级）
生成日期：2026-08-05  |  项目负责人：欧阳易芃
================================================================================

【任务来源】
你是 SLIM-ARC 项目的 Agent Programmer。本 prompt 为发起的一次全新端侧测试任务，
目标设备：RK3588 开发板（8GB RAM，型号标识 NBSXNXW23 2516）。请严格按下述内容
独立、自主地执行到任务完成，全程无需任何终端交互。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第一部分 ｜ 项目背景（先充分了解，再动手）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1.1 项目简介
- SLIM-ARC（Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization
  for On-Device Agents）是 2026 全国大学生系统能力大赛操作系统设计赛 Proj 59 参赛
  项目，中山大学团队。赛题：内存受限环境的大语言模型推理优化。
- 仓库：https://github.com/Nexa-Language/SLIM-ARC（main 分支）
- 技术栈：C/C++（upstream llama.cpp 生态）+ Python；CMake 3.14+；纯 CPU 推理，不用 GPU。
- 核心思路：用 OS 级虚拟内存机制（mmap + posix_madvise）+ MoE 稀疏性协同，让远大于
  物理内存的大模型在受限内存设备上流畅运行。
- 核心机制：mmap 映射权重 + MADV_RANDOM（只加载被访问页面）+ MoE 专家按需加载 +
  KV cache 驱逐/换页 + 统一 I/O 带宽预算调度器。

1.2 主机（x86 WSL + NVMe + cgroup）已测结果【基线参考，不必重测】
环境：WSL2-Ubuntu，Intel i9-13900H（32GB RAM），NVMe SSD，cgroups v2 三档隔离
（8G+4核 / 12G+6核 / 16G+8核，路径 /sys/fs/cgroup/slim-arc-{low,mid,high}）。
- Qwen3-Next-80B-A3B（45GB Q4_K_M / 39.7GB IQ4_XS）：
  8GB cgroup：decode 0.08→0.76 t/s（+850%，9.5×）
  16GB cgroup：+522%（6.2×）；32GB：2.45 t/s 流畅运行。
- KV eviction：80B decode +9.6%；OLMoE-1B-7B（3.9GB）8GB：+53~63%；
  Qwen3-4B（2.4GB）8GB：+17%/+6%。
- 消融结论：MADV_RANDOM 是 decode 提升的唯一驱动（+262%~437%）；prefetch_scheduler
  在 6/8GB 场景无独立价值（冗余）；MADV_RANDOM 会损失 prefill（-56%，阻止顺序预读）。
- 关键阈值：MADV_RANDOM 仅对 >6GB 模型生效；<6GB 小模型走 prefetch 路径。
- 注意：80B 场景数据波动大（取决于 page cache 命中率）。

1.3 4GB 树莓派 5 已测结果【本任务直接复用其流程】
- 已完成 SLIM-ARC 补丁修复并编译成功：补齐 prefetch_scheduler 缺失接口（compute_phase
  枚举 + set_phase/effective_window/set_memory_budget/register_expert_tensor/
  cache_router_experts/get_cached_experts/prefetch_experts + register_mmap_region）、
  增加 <climits>（修复 INT_MAX 级联错误）、修正 init_mappings 重复大括号。
- 涉及文件：patches/llama-upstream/slim-arc-prefetch.{h,cpp}、scripts/apply-slim-arc.py。
- 已测：Qwen3-4B 全部可行测试通过（无崩溃/无 OOM/无 SLIM-ARC 异常输出）。
- 关键限制：4GB 无法加载 >6GB 模型 → 核心创新不触发；microSD 是最大瓶颈
  （~8-10MB/s）；Pi5 内核无 CONFIG_MEMCG，无法用 cgroup 限内存。
- 完整流程与脚本参照：docs/pi5_4GB_test_notes/（任务Prompt、root-cause、
  Qwen3-4B-SLIMARC修复与测试报告-2026-08-05.md）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第二部分 ｜ 本次任务目标：RK3588 8GB 端侧测试
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

2.1 设备信息（先实测确认，别假设）
- RK3588 开发板，8GB RAM，型号标识：NBSXNXW23 2516。
- CPU：4×Cortex-A76 + 4×Cortex-A55（8 核，aarch64）。
- 存储：务必先确认类型与带宽（eMMC / M.2 NVMe / USB3 SSD / microSD）——这是端侧成败关键。
- 系统：先确认发行版（Armbian / Ubuntu / Debian / 其他），内核版本。
- cgroup：先确认 CONFIG_MEMCG 是否启用（影响能否限内存做三档）。

2.2 任务红线（不可逾越）
1. 只做 bug 修复，绝不修改任何核心代码/机制（不重构、不新增功能、不改变算法逻辑）。
2. 所有代码改动标注 // SLIM-ARC FIX <YYYY-MM-DD>: <原因>，最小外科手术式改动。
3. 镜像规则：patches/llama-upstream/ 与 src/llama-upstream/src/ 必须同步；通过
   scripts/apply-slim-arc.py（幂等）自动同步，禁止只改一处。
4. 全部测试记录/结果/日志输出到新目录 docs/rk3588_test_notes/。
5. 无终端交互：所有命令非交互、自主决策、持续工作直至任务完成。
6. 每个失败都要留痕并分析根因（构建日志、root-cause、修复记录），不掩盖、不凭记忆填数。

2.3 任务阶段（需自行细化为可勾选的任务条目并逐条推进）
- T0 环境预检与快照：CPU/内存/存储/系统/cgroup/git 状态 → docs/rk3588_test_notes/。
- T1 应用补丁并编译：apply-slim-arc.py + cmake -B build -DGGML_CPU_REPACK=OFF
  -DCMAKE_BUILD_TYPE=Release；编译 -j2（OOM 降 -j1）；定位并修复所有编译 bug，
  记录构建日志 build-rk3588-attempt-N.log，直至 EXIT=0。
- T2 冒烟测试：Qwen3-4B 默认开关与 SLIM_ARC_DISABLE=1 各一次，确认无崩溃无异常。
- T3 完整测试矩阵（参考 Pi5 的 T4 矩阵）：
  4.1 基础推理（冷/热缓存）｜4.2 llama-bench（-p 64 -n 32 / -p 128 -n 64）｜
  4.3 KV 量化（-ctk q4_0 -ctv q4_0）｜4.4 FlashAttention（-fa auto vs off）｜
  4.5 上下文伸缩（-c 512 / -c 1024）｜4.6 内存/swap 观测（RSS 峰值）｜
  4.7 SLIM-ARC 专属项负面验证（MADV_RANDOM / MoE / KV_EVICT）。
- T4 进阶（依存储/内存条件自主决定，不可强行）：
  若存储与内存允许，尝试 OLMoE-1B-7B（MoE，验证 expert 预取调用链）乃至 80B mmap
  （验证 MADV_RANDOM 触发、不 OOM）。若为慢盘（microSD）则明确记录"不可行"结论。
- T5 汇总报告：环境快照、根因分析、修复清单（文件+改动+原因）、编译结果、测试矩阵、
  结论、剩余限制 → docs/rk3588_test_notes/RK3588-SLIMARC测试报告-<YYYY-MM-DD>.md。
- T6 收尾：git status 校验、产物齐全确认、输出最终总结（每步做了什么、证据在哪、结论是什么）。

2.4 关键工程注意（沿用已踩坑经验）
- llama-cli 无 --no-cnv 参数：统一用 --single-turn + < /dev/null 防挂起。
- UI 输出走 /dev/tty：> file 与 --log-file 均捕获不到，须用 script -q -c '...' 捕获。
- /usr/bin/time 可能未装：内存峰值用 /proc/PID/status 的 VmRSS 轮询脚本。
- 模型文件：优先从 data/models/ 复用 Qwen3-4B-Q4_K_M.gguf；如需下载走代理
  http://127.0.0.1:7897，超时/SSL 失败要如实记录并换方案，不无限重试。
- 8GB 物理内存参考：Qwen3-4B（2.4GB）可跑；OLMoE-1B-7B（3.9GB）可跑；
  80B（约40GB）仅做 mmap 不 OOM 验证，别指望端侧速度（ARM 无 AVX2）。
- 编译/测试期间留意系统内存余量，避免 OOM；遇 OOM 降 -j1 或缩短上下文。

2.5 交付物
- docs/rk3588_test_notes/ 下至少包含：环境快照、构建日志、root-cause（如有）、
  raw-*.txt 原始输出、汇总报告 RK3588-SLIMARC测试报告-<日期>.md。
- 是否 git 提交：默认不提交（只留工作区改动）；如负责人要求提交，遵循
  Conventional Commits + gitmoji 格式，提交前再次确认。

【最终验收】
- 补丁版 llama-cli / llama-bench 在 RK3588 上编译成功（EXIT=0）。
- T3 中所有可执行测试均已执行，结果已保存到 docs/rk3588_test_notes/。
- T5 汇总报告已撰写，包含环境快照、根因、修复清单、测试矩阵、结论、剩余限制。
- 无任何核心机制改动，所有代码改动均为最小 bug 修复且镜像同步。
================================================================================
```

该 prompt 完整覆盖了您要求的 4 点：① 全面告知项目现状（主机 80B 三档实测数据、消融结论、4GB Pi5 补丁修复与流程参照）；② RK3588 测试只做 bug 修复、禁止核心机制改动（含镜像同步红线）；③ 全部记录输出到 `docs/rk3588_test_notes/`；④ 要求 agent 自建详细任务条目（T0-T6）、全程无交互持续工作。可直接粘贴给 RK3588 上的新 agent 使用。