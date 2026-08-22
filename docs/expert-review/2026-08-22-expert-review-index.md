# SLIM-ARC 专家复核材料与实现索引

整理日期：2026-08-21  
适用范围：2026 操作系统设计赛 Proj 59 决赛材料

本记录将最终报告和答辩 PPT 中的主要结论，对应到原始数据、实验合同、复现记录和实现代码。性能数字只在设备、模型、量化、资源限制、缓存状态和 workload 相同的条件下比较；`cold` 与 `warm`、Q4_K_M 与 IQ4_XS、CPU 与 NPU、cgroup 内存与进程 RSS 不交叉换算。

## 1. 建议复核顺序

1. 先看[项目详细报告](../../reports/Competition_Report_Finals/main.pdf)和[最终答辩 PPT](../../reports/SLIM-ARC_FINAL.pptx)。
2. 对照[初赛至决赛实验数据总索引](../results/README.md)，确认每项结果的实验合同和证据等级。
3. 按本记录第 3 节进入各设备的结构化结果、原始 stdout/stderr、环境记录和构建记录。
4. 按第 5 节进入补丁应用脚本、运行时实现和单元测试，核对报告所述机制与源码的对应关系。

## 2. 最终提交材料

| 材料 | 用途 | 入口 |
|---|---|---|
| 项目详细报告 | 系统设计、实现边界、跨设备评测和复现说明 | [仓库 PDF](../../reports/Competition_Report_Finals/main.pdf) · [LaTeX 源码](../../reports/Competition_Report_Finals/main.tex) |
| 最终答辩 PPT | 39 页决赛陈述材料；第 22–31 页集中呈现实验结果 | [仓库 PPTX](../../reports/SLIM-ARC_FINAL.pptx) · [仓库 PDF](../../reports/SLIM-ARC_FINAL.pdf) |
| 项目全景总结 | 项目演进、机制边界和跨设备结论的补充说明 | [仓库 PDF](../../reports/SLIM-ARC-project-overview.pdf) |
| 决赛答辩视频 | 提交时的完整陈述记录 | [Bilibili](https://www.bilibili.com/video/BV1iHbB6CEPb/) · GitHub Release asset |
| 全部提交文件 | 长期归档的代码、报告、答辩材料与证据 | [项目仓库](https://github.com/Nexa-Language/SLIM-ARC) |
| 统一数据索引 | 初赛至决赛全部设备的数据等级、合同和目录说明 | [docs/results/README.md](../results/README.md) |

### 2.1 模型与版本身份

- 决赛主模型：Qwen3-Next-80B-A3B-Instruct，Q4_K_M。
- 模型文件大小：48,410,988,384 B。
- 模型 SHA-256：`d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`。
- Mac 终态验证的 llama.cpp 提交：`360e1349f0009c5ad99d21e3c4546b707addc68a`。
- `80B` 表示约 800 亿参数。线上答辩视频标题中的“80 亿”为标题文字误差，不是实验所用模型规模。

模型文件大小取自文件系统和 `controller-result.json`；`llama-bench` stdout 中的 `model_size=48,405,005,312` 是其加载后报告的模型数据大小，二者统计对象不同。模型身份以文件名、文件系统大小和 SHA-256 三项共同确认。

## 3. 主要结论与原始数据

### 3.1 Mac/Colima：80B 模型在 2 GiB 硬限制下完成推理

实验合同：Qwen3-Next-80B Q4_K_M，2 GiB cgroup v2 `memory.max`，4 CPU，`swap.max=0`，cold cache，`pp64/tg16`，CPU-only。

终态运行退出码为 0，无 OOM；Prefill 为 3.908455 token/s，Decode 为 0.709095 token/s，wall 为 58.06 s；`memory.peak` 为 2,147,483,648 B，最大 RSS 为 2,084,740 KiB，major faults 为 402,118。

- 复核摘要：[final-validation-summary.md](../macos_test_notes/2026-08-17/final-validation-summary.md)
- 运行目录：[ecospec-a24-final-2g-4c-pp64-tg16-cold](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/)
- 实验身份：[run-manifest.json](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/run-manifest.json)
- 控制器结果：[controller-result.json](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/controller-result.json)
- 程序输出：[rep-1.stdout.log](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/rep-1.stdout.log) · [rep-1.stderr.log](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/rep-1.stderr.log) · [rep-1.time.txt](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/rep-1.time.txt)
- 资源限制前后记录：[cgroup-before.txt](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/cgroup-before.txt) · [cgroup-after.txt](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/cgroup-after.txt)

这里的“2 GiB”是 Colima 虚拟机内由 cgroup v2 强制执行的容器内存上限，不是把 Mac 物理内存减少为 2 GiB。VM 宿主配置为 16 GiB，但被测进程所在 cgroup 的 `memory.max` 和 `memory.peak` 均可在记录中核验。该结果证明的是硬资源合同下的可运行性。

8 月 12 日正式矩阵共 20 次运行，每个配置按 cold/warm 各重复两次，全部成功且 `memory.peak` 均为 2 GiB：

- [finals-results.json](../macos_test_notes/2026-08-12/finals-results.json)
- [finals-evidence.csv](../macos_test_notes/2026-08-12/finals-evidence.csv)
- [finals-validated-summary.md](../macos_test_notes/2026-08-12/finals-validated-summary.md)
- [build-evidence.json](../macos_test_notes/2026-08-12/build/build-evidence.json)
- [报告数据导入与校验说明](../../reports/Competition_Report_Finals/RESULTS_IMPORT.md)

正式矩阵中启用回收的运行均记录到 `reclaim_calls=0`，因此不能把该批性能差异归因于 `MADV_DONTNEED` 已实际触发。报告保留这一负面事实。

### 3.2 WSL/x86：只采用同合同 A/B 数字

8 GiB、Qwen3-Next-80B、同一 `pp/tg` 合同下的原始记录为：

| workload | baseline | SLIM-ARC | 同合同结果 | 原始日志 |
|---|---:|---:|---|---|
| `pp4/tg1` | 0.22 / 0.08 | 0.25 / 0.43 | Decode +437.5%，即 5.4× | [baseline](../../logs/ablation/raw-80b/80b-8g-baseline-pp4-tg1.txt) · [SLIM-ARC](../../logs/ablation/raw-80b/80b-8g-slim-arc-pp4-tg1.txt) |
| `pp16/tg4` | 0.63 / 0.08 | 0.28 / 0.29 | Prefill -56%，Decode +262.5%，即 3.6× | [baseline](../../logs/ablation/raw-80b/80b-8g-baseline-pp16-tg4.txt) · [SLIM-ARC](../../logs/ablation/raw-80b/80b-8g-slim-arc-pp16-tg4.txt) |

完整分析见[phase4-ablation-summary.md](../../reports/raw_analysis/phase4-ablation-summary.md)。PPT 中的 `0.08 → 5.16 token/s` 和“64.5×”连接了不同内存档位、缓存状态、量化、FlashAttention 和 workload，只能作为历史实验端点序列，不能作为受控端到端加速结论。正式复核采用上表的同合同数字。

### 3.3 RK3588：3 GiB 主结果与动态 MADV 修复

F 组固定 80B Q4_K_M、4 threads、`pp128/tg64`、KV q4_0、`MemorySwapMax=0`。在 3 GiB 同合同下，F1 baseline 为 3.85 / 0.70 token/s，F2 SLIM-ARC 为 4.40 / 2.21 token/s，即 Prefill +14%，Decode +216%（3.16×）；两组均未 OOM。

- [F/G/H 汇总](../rk3588_test_notes/SLIM-ARC后续测试汇总-FGH-2026-08-13.md)
- [F1 原始日志](../rk3588_test_notes/adv-scenario-F1-2026-08-13.txt)
- [F2 原始日志](../rk3588_test_notes/adv-scenario-F2-2026-08-13.txt)
- [RK3588 全部数据汇总](../../reports/raw_analysis/rk3588-edge-test-summary.md)

动态 MADV 的修复链用于证明分阶段页建议的必要性：静态 RANDOM 为 0.44 / 0.26；禁用 SLIM-ARC 为 2.74 / 1.41；最终动态全 SEQUENTIAL 为 2.84 / 1.40。对应记录为：

- [Stage 2A 动态 MADV 汇总](../rk3588_improvement/stage2a-dynamic-madv-summary.txt)
- [Stage 2B Decode 策略汇总](../rk3588_improvement/stage2b-decode-optimization-summary.txt)
- [测试数据说明](../rk3588_improvement/测试数据.md)
- [NVMe 随机读瓶颈与动态 MADV 分析](../rk3588_test_notes/RK3588-NVMe随机4K读瓶颈与动态MADV机制分析-2026-08-14.md)

F 组中的若干点为单次样本，2.5 GiB baseline 还出现过 page cache 导致的反常高值。因此这些数据只在相同内存档位内比较，不作为跨设备统计结论。

### 3.4 Raspberry Pi 5：共享热专家与字节预算

固定合同为 4 GB Raspberry Pi 5、80B Q4_K_M、4 threads、USB NTFS/FUSE 机械盘、cold、运行期 no-swap、`pp16/tg16`，每个候选两次运行。

A28 共享热专家缓存相对 A24 的中位数结果为：Prefill 0.204023 token/s、Decode 0.063486 token/s、wall 511 s；Decode +14.16%，wall -6.58%，`expert_issued=0`，共享或 hot lock 失败均为 0。

- [A28 汇总](../pi5_4GB_test_notes/2026-08-14-a28-hot512-shared-summary.md) · [结构化 JSON](../pi5_4GB_test_notes/2026-08-14-a28-hot512-shared-summary.json)
- [A28 第一次原始运行](../pi5_4GB_test_notes/2026-08-14-a28-hot512-shared-noswap-screen-tg16-r1/) · [第二次原始运行](../pi5_4GB_test_notes/2026-08-14-a28-hot512-shared-noswap-screen-tg16-r2/)

A29 将 issued weight 从 3,891.14 MiB 降到 60.59 MiB、inflight peak 从 614.39 MiB 降到 9.59 MiB，均下降 98.44%；性能与 A28 基本相当。A29 相对 A24 的 +14.33% 包含 A28 的共享热专家收益，不能全部归因于预算本身。

- [A29 汇总](../pi5_4GB_test_notes/2026-08-14-a29-budget16-summary.md) · [结构化 JSON](../pi5_4GB_test_notes/2026-08-14-a29-budget16-summary.json)
- [A29 第一次原始运行](../pi5_4GB_test_notes/2026-08-14-a29-budget16-current-tg16-r1/) · [第二次原始运行](../pi5_4GB_test_notes/2026-08-14-a29-budget16-current-tg16-r2/)

### 3.5 华为 HiDevLab：CPU-only 兼容性与运行时 A/B

该环境使用 aarch64 CPU-only llama.cpp 和 2.56 GB OLMoE Q2_K，16 threads、warm cache、3 次重复。Ascend 910B4 可枚举，但本次实验没有进入 NPU 计算路径。

- [环境与结论说明](../ascend_test_notes/2026-08-17/README.md)
- [运行时 A/B JSON](../ascend_test_notes/2026-08-17/olmoe-q2-runtime-ab.json)
- [Ascend 枚举与 smoke JSON](../ascend_test_notes/2026-08-17/ascend-smoke.json)

patched-default Decode 为 45.254 token/s，A24 为 48.184 token/s，提升 6.47%；但 native baseline 为 51.340 token/s，因此 A24 仍低 6.15%。这项结果用于说明 aarch64 兼容性和运行时开关可测，不作为 NPU 加速结论。

## 4. PPT 重点页的复核说明

| PPT 页 | 复核问题 | 可核验结论与材料 |
|---:|---|---|
| 14 | Router 预取是否改变模型输出，能否保证“零缺页”？ | Native Router 仍是最终专家选择，预测只用于提前发出页建议，miss 时回退到 demand paging，因此不改变模型语义；“零缺页”不是强保证。代码见[`cache_router_experts`](../../patches/llama-upstream/slim-arc-prefetch.cpp)和[`issue_expert_willneed`](../../patches/llama-upstream/slim-arc-prefetch.cpp)。 |
| 16 | StreamingLLM 的 4 sink + 1024 window 是否对应 +9.6%？ | +9.6% 的历史记录实际来自 32 GiB、IQ4_XS、sink=4/window=32：3.01 → 3.30 token/s；4+1024 是机制示意，不是该数字的实验配置。[baseline](../../logs/ablation/raw-80b/80b-32g-baseline-pp64-tg48.txt) · [eviction](../../logs/ablation/raw-80b/80b-32g-eviction-pp64-tg48.txt)。 |
| 17、36 | Weight/KV/Expert 是否已形成同强度的三方硬预算？ | Weight 与 Expert 已有字节级准入和统计；KV 有模块和调度接口，但当前 `runtime_owner` 向统一调度器传入空 KV manager，尚未形成与 Weight/Expert 同强度的每 tick 字节硬预算。以“统一接口已建立、KV 连通成熟度较低”表述更准确。 |
| 19 | 是否真的“零侵入上游”，是否只改约 200 行？ | 仓库采用可重复、幂等的低侵入 source transform。脚本修改 5 个上游 C++ 文件和 `src/CMakeLists.txt`，并复制 SLIM-ARC 模块；不是零修改。未经生成树 diff 复算，不采用固定行数表述。[apply-slim-arc.py](../../scripts/apply-slim-arc.py)。 |
| 20 | 跨平台是否使用“同一 build”？ | 使用同一补丁系统和运行时开关，但 x86_64 与 aarch64 分别原生编译，不是同一个二进制文件。Mac/RK 终态合同固定到 `360e134`；Pi 的后续合并源码另有运行 manifest。 |
| 22、24 | 64.5× 是否真实、可重复？ | 原始端点真实存在，但合同不同，不能组成受控加速比。正式数字改用第 3.2 节同合同 WSL A/B。统一索引已将“64.5×”“850%”列为历史、禁止作为当前统一结论。 |
| 25 | 为什么图中 Full Decode 为 3.03，而 no KV q4 为 3.92，却写 +4%？ | 3.03 来自 core IQ4_XS 32 GiB 基线；+4% 实际按同一消融批次的 3.77 → 3.92 计算。该页混合了两个 baseline。原始记录：[core](../../logs/ablation/full-rerun/core-iq4xs-32g.txt) · [ablation full](../../logs/ablation/full-rerun/80b-32g-ablation-full.txt) · [no KV q4](../../logs/ablation/full-rerun/80b-32g-ablation-no-kvq4.txt) · [no MADV](../../logs/ablation/full-rerun/80b-32g-ablation-no-madv.txt) · [eviction](../../logs/ablation/full-rerun/80b-32g-ablation-evict.txt)。 |
| 26 | 2 GiB 是否只是软件记录，回收是否真正生效？ | `memory.max`、`memory.peak`、swap、退出码、RSS 和 faults 均有独立文件；限制由 cgroup 强制执行。该正式矩阵的 `reclaim_calls=0`，所以只证明 2 GiB 下完成和运行时边界，不把性能归因于实际回收。 |
| 27–30 | RK3588/Pi 的提升是否具有统计普遍性？ | 这些是固定设备合同下的工程样本：Pi 候选通常 n=2，RK 部分主结果为单次或两次；用于验证机制、边界和选型，不外推为所有硬件的统计保证。 |
| 31 | Ascend 是否使用了 NPU？ | 未使用。只验证 aarch64 CPU 路径、设备枚举和 runtime A/B。 |
| 38 | 所有图表能否回到原始记录？ | 本记录第 3 节给出结构化结果和逐次日志；第 22、24、25 页存在上述合同或 baseline 混用，按本节口径复核。 |

## 5. 重点优化代码入口

仓库可追溯实现由 `patches/llama-upstream/` 中的模块和 `scripts/apply-slim-arc.py` 共同组成。外部 llama.cpp clone 只是生成后的工作树，不作为唯一源码依据。

| 机制 | 实现入口与关键符号 | 作用 | 验证入口 |
|---|---|---|---|
| 补丁应用与上游接线 | [scripts/apply-slim-arc.py](../../scripts/apply-slim-arc.py)：`SLIM_ARC_FILES`、`patch_model_loader`、`patch_model`、`patch_qwen3next`、`patch_context`、`patch_kv_cache`、`patch_cmakelists` | 将运行时生命周期、tensor mapping、Qwen3-Next Router feedback、decode 结算和 KV clear 页回收接入固定 llama.cpp 源码 | [Python 接线测试](../../tests/test_apply_expert_reclaim.py) · [压力准入测试](../../tests/test_apply_pressure_admission.py) |
| Model-owned runtime 生命周期 | [slim-arc-runtime.h](../../patches/llama-upstream/slim-arc-runtime.h)：`runtime_owner`、`runtime_lease`、`acquire_runtime`；[slim-arc-runtime.cpp](../../patches/llama-upstream/slim-arc-runtime.cpp) | 由 model 持有运行时，以 lease 防止卸载与并发调用竞态 | [test-slim-arc-runtime.cpp](../../tests/cpp/test-slim-arc-runtime.cpp) |
| 分阶段权重预取 | [slim-arc-prefetch.h](../../patches/llama-upstream/slim-arc-prefetch.h)：`prefetch_scheduler`；[slim-arc-prefetch.cpp](../../patches/llama-upstream/slim-arc-prefetch.cpp)：`set_phase`、`register_mapping`、`notify_layer_compute`、`worker_loop` | Prefill/Decode 分阶段页建议、有限队列、映射注册、page-range 合并和异步 `WILLNEED` | [test-slim-arc-prefetch-budget.cpp](../../tests/cpp/test-slim-arc-prefetch-budget.cpp) |
| Router 反馈与专家代际结算 | [slim-arc-prefetch.cpp](../../patches/llama-upstream/slim-arc-prefetch.cpp)：`cache_router_experts`、`cancel_expert_prefetch`、`issue_expert_willneed`、`record_expert_transition_result` | Router 选择后下发专家页建议，以 generation 区分已发出、命中、浪费和取消，Native Router 保持权威 | [test-slim-arc-prefetch-budget.cpp](../../tests/cpp/test-slim-arc-prefetch-budget.cpp) |
| Expert reclaim | [slim-arc-expert-reclaim.h](../../patches/llama-upstream/slim-arc-expert-reclaim.h)：`build_expert_reclaim_plan`；[slim-arc-prefetch.cpp](../../patches/llama-upstream/slim-arc-prefetch.cpp)：`reclaim_wrong_expert_pages` | 基于专家 tensor 的页范围生成回收计划，并记录实际回收调用 | [test-slim-arc-expert-reclaim.cpp](../../tests/cpp/test-slim-arc-expert-reclaim.cpp) |
| Expert residency、pressure 与 waste 控制 | [slim-arc-expert-residency.h](../../patches/llama-upstream/slim-arc-expert-residency.h)：`select_resident_experts`、`expert_pressure_controller`、`expert_waste_controller`；[实现](../../patches/llama-upstream/slim-arc-expert-residency.cpp) | 按热度、压力和浪费率决定常驻专家及准入收缩 | [test-slim-arc-expert-residency.cpp](../../tests/cpp/test-slim-arc-expert-residency.cpp) |
| 跨层专家转移 | [slim-arc-expert-transition.h](../../patches/llama-upstream/slim-arc-expert-transition.h) · [实现](../../patches/llama-upstream/slim-arc-expert-transition.cpp) | 在线维护相邻层专家转移统计，为下一层候选提供可衰减先验 | [test-slim-arc-expert-transition.cpp](../../tests/cpp/test-slim-arc-expert-transition.cpp) |
| 页边界与合并 | [slim-arc-page-range.h](../../patches/llama-upstream/slim-arc-page-range.h)：`interior_page_range`、`covering_page_range`、`coalesce_page_ranges` | 将 tensor 地址规整为可安全执行 `madvise`/`fadvise` 的页范围，避免重复建议 | [test-slim-arc-page-range.cpp](../../tests/cpp/test-slim-arc-page-range.cpp) |
| cgroup 感知与压力预算 | [slim-arc-cgroup-memory.h](../../patches/llama-upstream/slim-arc-cgroup-memory.h) · [slim-arc-pressure-budget.h](../../patches/llama-upstream/slim-arc-pressure-budget.h) | 读取容器内存边界，将压力、质量、inflight 和字节预算用于 admission | [cgroup 测试](../../tests/cpp/test-slim-arc-cgroup-memory.cpp) · [pressure 测试](../../tests/cpp/test-slim-arc-pressure-budget.cpp) · [统一压力测试](../../tests/cpp/test-slim-arc-unified-pressure.cpp) |
| 统一 I/O 调度 | [slim-arc-unified-scheduler.h](../../patches/llama-upstream/slim-arc-unified-scheduler.h)：`unified_io_scheduler`；[slim-arc-unified-scheduler.cpp](../../patches/llama-upstream/slim-arc-unified-scheduler.cpp)：`tick`、`adapt_allocation` | 按阶段分配 Weight/KV/Expert 预算并汇总统计；当前 Weight/Expert 主路径成熟度高于 KV | [test-slim-arc-unified-pressure.cpp](../../tests/cpp/test-slim-arc-unified-pressure.cpp) |
| KV eviction 研究模块 | [slim-arc-kv-eviction.h](../../patches/llama-upstream/slim-arc-kv-eviction.h) · [slim-arc-kv-eviction.cpp](../../patches/llama-upstream/slim-arc-kv-eviction.cpp) | 提供 sink/window 和 KV 驱逐接口；当前不等同于已完整接入三方硬预算的生产主路径 | [test-slim-arc-kv-eviction.cpp](../../tests/cpp/test-slim-arc-kv-eviction.cpp) |
| Edge Agent 演示 | [scripts/agent/edge_agent.py](../../scripts/agent/edge_agent.py)：`ContextPolicy`、`RestrictedShell`、`AdaptiveTokenBudget`、`EdgeAgent` | 在资源受限模型服务上演示上下文压缩、受限工具调用和自适应输出预算 | [test_edge_agent.py](../../tests/agent/test_edge_agent.py) |

运行全部 C++ 单元测试的入口为 [tests/run-cpp-unit.sh](../../tests/run-cpp-unit.sh)。实现章节源码为[04_implementation.tex](../../reports/Competition_Report_Finals/sections/04_implementation.tex)，评测章节源码为[05_evaluation.tex](../../reports/Competition_Report_Finals/sections/05_evaluation.tex)。

现场快速定位可优先打开以下位置：

- `scripts/apply-slim-arc.py:10`：被安装的独立模块；`:355`：Qwen3-Next Router 接线；`:362`：graph compute、phase 和 Router feedback 接线；`:645`：KV clear 回收接线；`:710`：补丁入口。
- `patches/llama-upstream/slim-arc-runtime.cpp:47`：model-owned runtime 构造；`:91`：运行时 lease 获取。
- `patches/llama-upstream/slim-arc-prefetch.cpp:305`：Prefill/Decode phase；`:793`：Router 专家反馈；`:921`：generation 取消；`:1264`：错误专家页回收；`:1308`：专家 `WILLNEED` 下发。
- `patches/llama-upstream/slim-arc-unified-scheduler.cpp:198`：一次统一预算 tick；当前 KV manager 的接线边界见 `slim-arc-runtime.cpp:47`。
- `patches/llama-upstream/slim-arc-expert-residency.cpp:188`：常驻专家选择；`slim-arc-pressure-budget.h:18`：压力预算计算接口。

## 6. 真实性与可复现性核验

### 6.1 每次正式实验保存的内容

正式记录尽量同时保留以下四层证据：

1. **实验身份**：模型路径、文件大小和哈希、llama.cpp 提交、补丁状态、命令行、环境变量、设备和时间戳。
2. **资源合同**：CPU 数、`memory.max`、`memory.swap.max`、缓存状态、模型量化、`pp/tg` 和重复次数。
3. **原始执行记录**：stdout、stderr、exit status、wall time、RSS、major faults、cgroup 前后状态。
4. **派生结果**：结构化 JSON/CSV 和 Markdown 摘要；派生文件由脚本重建，并校验输入 schema 与哈希。

Mac 正式结果的重建命令、20-run schema、SHA-256 校验和报告导入流程见[RESULTS_IMPORT.md](../../reports/Competition_Report_Finals/RESULTS_IMPORT.md)。仓库补丁的最小复现入口见[README.md](../../README.md)，核心 C++ 测试可运行：

```bash
bash tests/run-cpp-unit.sh
```

完整硬件复现需要相同模型文件、等价存储和资源约束以及相应设备；在不具备硬件时，仍可独立核对 manifest、哈希、原始日志、结构化结果、派生脚本和源码测试。

### 6.2 已排除或降级的记录

- Mac 8 月 11 日早期镜像存在 baseline-first `LD_LIBRARY_PATH` 问题；其中被标记为 patched 的性能比较已降级，只保留可独立核验的生存边界和资源记录。
- WSL “64.5×”和“850%”涉及不同实验合同，保留为历史记录，不进入当前统一性能结论。
- RK3588 H1 首轮输入含 `echo -e` artifact；相关结果只作探索性记录。
- Pi 的错误控制变量或运行失败样本不进入正式 A/B；最终结论只引用合同明确、原始目录完整的候选。
- IQ4_XS 精度小样本曾出现明显风险，因此决赛 2 GiB 主结果固定为 Q4_K_M。

## 7. 结论边界

- **可直接复核的主结论**：80B Q4_K_M 在 Mac/Colima 2 GiB hard cgroup、4 CPU、no-swap 合同下完成推理；模型哈希、构建提交、资源记录和完整输出均已保存。
- **同合同性能结论**：WSL、RK3588 和 Pi 只采用各自设备内、相同合同下的 A/B；不同设备之间不计算统一倍数。
- **机制性结论**：分阶段页建议、Router feedback、字节预算、generation settlement、pressure/waste admission 和 model-owned runtime 均有仓库源码与单元测试。
- **尚未作强结论的部分**：KV eviction 与三方统一硬预算的接线成熟度低于 Weight/Expert；HiDevLab 未使用 NPU；Pi 和部分 RK3588 样本量有限。
- **精度边界**：系统不替换 Native Router 的最终选择，但现有质量评测样本较小，只能证明已检查明显回归风险，不能替代大规模模型质量评测。

以上边界用于保证报告、PPT、原始数据和当前实现之间的对应关系可复查，也避免把历史探索数字、跨合同端点或尚未完整接线的模块表述为终态能力。
