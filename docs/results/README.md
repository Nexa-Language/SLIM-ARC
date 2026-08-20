# SLIM-ARC 初赛至决赛实验数据总索引

更新时间：2026-08-17

覆盖范围：初赛 WSL/x86、RK3588、Raspberry Pi 5、Mac/Colima、华为 HiDevLab

整理所基于的源码快照：`d61423696f2d3ef5d7d447d4de79ef0435b9dc7e`

这份文档是 SLIM-ARC 的统一数据入口。它不替代原始日志和结构化 JSON，而是解决三个
问题：数据放在哪里、哪些结果能互相比较、哪些结论仍可用于决赛答辩。

快速跳转：[一页总览](#2-一页总览) · [初赛](#4-初赛数据) ·
[RK3588](#5-rk3588-数据) · [Mac](#6-maccolima-数据) ·
[Raspberry Pi 5](#7-raspberry-pi-5-数据) · [华为 HiDevLab](#8-华为-hidevlab--ascend-数据) ·
[优化决策账本](#9-跨设备优化决策账本) · [证据目录](#10-证据目录)

## 1. 阅读规则

### 1.1 证据等级

| 标记 | 含义 | 可以怎么使用 |
|---|---|---|
| **A：当前可引用** | 合同明确，有重复或终态复核，证据链完整 | 可进入决赛报告和答辩，但仍需带设备与 workload |
| **B：探索性有效** | 真实运行，但样本较少、镜像不同或只验证单一机制 | 可说明趋势、机制和选型，不宜宣传为稳定提升 |
| **C：历史/已失效** | 链接错误、控制变量错误、跨缓存拼接或已被后续实验推翻 | 仅用于说明研发过程，不能作为当前性能结论 |
| **D：兼容性** | 证明编译、运行或硬件枚举，不代表目标加速路径 | 可说明可移植性，不可宣传为 NPU/端到端加速 |

### 1.2 统一口径

- `pp`/Prefill 和 `tg`/Decode 的单位均为 token/s；wall 为整次 benchmark 秒数。
- 只有同设备、同模型、同缓存状态、同资源限制、同 `pp/tg` 和相邻构建的行才计算提升率。
- cold 与 warm 不相除；Q4_K_M 与 IQ4_XS 不相除；CPU-only 与 NPU 不相除。
- `memory.max`/`memory.peak` 是 cgroup 口径；RSS 是进程口径，二者不能混写。
- 早期“64.5x”“850%”保留在历史区，但不再视为当前版本的统一结论。

## 2. 一页总览

| 阶段/设备 | 核心模型与合同 | 最重要结果 | 等级 | 详细入口 |
|---|---|---|---|---|
| 初赛 WSL/x86 | Qwen3-Next-80B，8–32 GiB cgroup | 证明 mmap、关闭 repack、量化和页建议路径可运行；高倍数数据受缓存/合同混合影响 | C/B | [初赛报告](../../reports/Competition_Report/main.pdf)、[初赛消融](../../reports/raw_analysis/phase4-ablation-summary.md) |
| RK3588 8GB | 80B Q4_K_M，SSD，ARM CPU；3GiB user cgroup | 3GiB 下 `tg 0.70 → 2.21`（3.16×）；动态阶段策略恢复到 `pp 2.84 / tg 1.40` | A/B | [RK3588 汇总](../../reports/raw_analysis/rk3588-edge-test-summary.md)、[F/G/H](../rk3588_test_notes/优势场景测试-2026-08-13/SLIM-ARC后续测试汇总-FGH-2026-08-13.md) |
| Pi 5 4GB | 80B Q4_K_M，USB NTFS/FUSE，no-swap | A28 相对 A24：Decode +14.16%，wall -6.58%；A34 LRU 再小幅改善 | A/B | [Pi 目录](../pi5_4GB_test_notes/) |
| Mac/Colima | 80B Q4_K_M，2 GiB、4/8 CPU、no-swap | 48.41GB 模型在 2GiB 下完成；末次 `pp 3.908 / tg 0.709` | A | [Mac 末次复核](../macos_test_notes/2026-08-17/final-validation-summary.md) |
| 华为 HiDevLab | OLMoE Q2_K，aarch64 CPU-only | 跑通系统开/关 A/B；A24 比 patched-default Decode +6.47%，但仍慢于 baseline | D/B | [Ascend 环境实验](../ascend_test_notes/2026-08-17/README.md) |

仓库当前保存 171 份 Mac `run-manifest.json`、26 份 Mac summary、14 份 Pi summary、
653 个 Pi 数据文件、364 个 RK3588 数据文件和 3 个 Ascend 数据文件。正文只列有解释价值
的汇总；原始逐次记录通过链接进入。

## 3. 模型与设备合同

### 3.1 模型

| 模型 | 类型 | 量化/大小 | 专家 | 主要用途 |
|---|---|---:|---:|---|
| Qwen3-4B | Dense | Q4_K_M，约 2.4GB | — | 小模型基线、Pi/RK 编译与 KV/FA 验证 |
| OLMoE-1B-7B | MoE | Q4_K_M 约 3.9–4.2GB；Q2_K 2.56GB | 64，激活 8 | 小 MoE Router 链路、HiDevLab A/B |
| Qwen3-Next-80B-A3B | MoE | Q4_K_M，48,410,988,384B | 512，激活约 10 | 主模型；2–16GiB 物理内存受限实验 |
| Qwen3-Next-80B-A3B | MoE | IQ4_XS，约 40GB | 512，激活约 10 | 初赛量化与性能探索；精度风险较高 |

80B Q4_K_M 的决赛固定 SHA-256 为
`d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`。

### 3.2 设备

| 设备 | CPU/内存 | 存储与隔离 | 主要瓶颈 | 可否与其他设备直接比较 |
|---|---|---|---|---|
| 初赛 WSL/x86 | i9-13900H，8–32GiB cgroup | NVMe，缓存状态多样 | 冷启动 I/O、page cache 波动 | 否 |
| Orange Pi 5 Plus / RK3588 | 4×A76+4×A55，8GB | SSD 约 2.1GB/s；部分 cgroup/压力实验 | 弱核、内存带宽、fault 固定开销 | 否 |
| Raspberry Pi 5 | 4×A76，4GB | USB 机械盘 + NTFS-3G/FUSE；决赛多为 no-swap cold | FUSE 往返和同步缺页 | 否 |
| Mac/Colima ARM64 VM | 8 vCPU/16GiB VM，容器限 1–4GiB | cgroup v2，`swap.max=0`，CPU-only | page fault、虚拟磁盘、CPU 饱和 | 否 |
| 华为 HiDevLab | aarch64，Ascend 910B4 可枚举 | 独立目录；实际 llama.cpp CPU-only | 小模型已接近全驻留 | 否 |

## 4. 初赛数据

### 4.1 80B WSL 历史核心结果

| 合同 | 配置 | Prefill | Decode | 当时记录的变化 | 当前判定 |
|---|---|---:|---:|---:|---|
| 8GiB，`pp4/tg1` | baseline | 0.22 | 0.08 | reference | B：原始日志存在 |
| 8GiB，`pp4/tg1` | SLIM-ARC | 0.25 | 0.43 | Decode +437.5% | B：仅限此合同 |
| 8GiB，`pp16/tg4` | baseline | 0.63 | 0.08 | reference | B：原始日志存在 |
| 8GiB，`pp16/tg4` | SLIM-ARC | 0.28 | 0.29 | Prefill -56%，Decode +262.5% | B：明确有权衡 |
| 16GiB，`pp4/tg1` | SLIM-ARC | 0.17 | 0.38 | baseline 未同合同测量 | B：不可算提升 |

证据：[初赛消融报告](../../reports/raw_analysis/phase4-ablation-summary.md)。初赛材料曾把
不同内存档位、缓存状态、量化和 FlashAttention 行连接成 `0.08 -> 5.16 t/s`，得到
`64.5x`；决赛审计后该数字降为 **C**，不再作为当前端到端加速结论。

### 4.2 初赛三档与量化探索

| 环境 | 模型/配置 | Prefill | Decode | 说明 | 等级 |
|---|---|---:|---:|---|---|
| 8GiB/4核 | IQ4_XS Full | — | — | 冷启动超时 | B：边界结果 |
| 16GiB/8核 | IQ4_XS Full | — | 2.27±0.38 | `tg64` | B |
| 32GiB/8核 | IQ4_XS Full | 4.44±1.53 | 3.03±0.29 | `tg48` | B |
| 8GiB/4核 | Q4_K_M Full | — | — | 冷启动超时 | B |
| 16GiB/8核 | Q4_K_M Full | 1.96±0.82 | — | `pp128`，tg 超时 | B |
| 32GiB/8核 | Q4_K_M Full | — | 2.68±0.23 | `tg48` | B |
| 32GiB/8核 | IQ4_XS + FA auto | 12.99 | 5.16 | 热缓存，不能接到冷 baseline | C/B |

完整表在[初赛评测源码](../../reports/Competition_Report/sections/05_evaluation.tex)。

### 4.3 小模型、精度和负面结果

| 项目 | 结果 | 当前解释 |
|---|---|---|
| Qwen3-4B，2GiB+1核 | Decode `2.58±0.17 t/s` | 小模型可运行 |
| OLMoE，2GiB+1核 | Decode `8.92±0.94 t/s` | MoE 小模型可运行 |
| GSM8K Qwen3-4B Q4_K_M | 15/20 = 75% | 小样本精度检查 |
| GSM8K 80B Q4_K_M + KV q4_0 | 5/10 = 50% | 样本过小，只作风险检查 |
| GSM8K 80B IQ4_XS + KV q4_0 | 0/10 | IQ4_XS 推理精度风险，不推广 |
| WikiText-2 Qwen3-4B Q4_K_M | PPL 约 12.7 | F16 11.9 为外部参考、非同机实测 |
| Self-draft speculative decoding | 3.01 → 1.41 t/s，-53.2% | 拒绝；MoE Router 高熵且无小 draft model |

### 4.4 Qwen3-4B Phase 2c

| 环境 | Baseline pp64/tg32 | Phase 2c pp64/tg32 | 结果 |
|---|---:|---:|---|
| 8GiB/4核 | 39.80 / 9.74 | 39.86 / 7.64 | Prefill +0.2%，Decode -21.6% |
| 16GiB/8核 | 54.28 / 11.90 | 56.98 / 10.09 | Prefill +5.0%，Decode -15.2% |

证据：[Phase 2c 原始分析](../../reports/raw_analysis/phase2c-prefill-decode-results.md)。该轮直接
促成后续“Prefill 与 Decode 必须分阶段”的设计。

## 5. RK3588 数据

### 5.1 小模型与首次 80B 上机

| 模型/合同 | 配置 | Prefill | Decode | RSS/备注 |
|---|---|---:|---:|---|
| Qwen3-4B `p64/n32/t4` | F16 KV, FA auto | 8.57±0.01 | 6.90±0.13 | 约 2.65GB |
| Qwen3-4B `p64/n32/t4` | KV q4_0 | 8.31±0.10 | 5.05±0.29 | 省内存但此场景变慢 |
| Qwen3-4B `p64/n32/t4` | FA off | 7.63±0.04 | 3.49±0.69 | FA 有明显价值 |
| OLMoE | 默认 | 4.3 | 10.7 | RSS 约 4.2GB；Router 链路跑通 |
| 80B `p32/n16/t4` | 早期静态 RANDOM 全开 | 0.39 | 0.23 | RSS 约 6.29GiB |
| 80B `p32/n16/t4` | SLIM_ARC_DISABLE | 2.02 | 0.89 | 早期全开明显负优化 |
| 80B `p32/n16/t4` | NO_MADV_RANDOM | 1.41 | 0.65 | 定位 RANDOM 为主因 |

### 5.2 动态 MADV 修复链

| 阶段 | Prefill | Decode | 结论 |
|---|---:|---:|---|
| 静态 RANDOM | 0.44 | 0.26 | 严重负优化 |
| 禁用 SLIM-ARC | 2.74 | 1.41 | 参考路径 |
| Prefill SEQUENTIAL / Decode RANDOM | 2.82 | 0.25 | Prefill 修复，Decode 仍坏 |
| Decode SEQUENTIAL | 2.81 | 1.35 | 关键修复 |
| Decode NORMAL | 2.57 | 1.41 | Decode 最快但 Prefill 较低 |
| 动态全 SEQUENTIAL | **2.84** | **1.40** | 追平禁用并保留运行时能力 |
| 长上下文 `p512/n128` 全开 | 6.09 | 2.08 | 接近禁用 6.33/2.15 |

### 5.3 Router、预算与受限场景

| 实验 | 对照 | 候选 | 结论 |
|---|---:|---:|---|
| Temporal predictor 精度 | 随机约 2% | 34.9% | 约 17.5× 随机；spatial 仅 4.5% |
| Confidence gating | 27,836.7MB / 31.05% hit | 12,123.6MB / 55.35% hit | 下发约 -56%，速度 1.9 t/s 持平 |
| Confidence + budget | baseline tg 1.9 | tg 2.1，hit 54.00% | 探索性正结果 |
| Popular expert 16 | 27,836.7MB / 31.05% | 72,634.4MB / 19.31% | I/O 增、命中降，拒绝 |
| 4GiB cgroup | baseline | SLIM-ARC | Prefill +18.0%，Decode +13.3% |
| 4GiB、长生成 | baseline | SLIM-ARC | Prefill +3.6%，Decode +11.2% |
| 5GiB cgroup | baseline | SLIM-ARC | Prefill -0.7%，Decode +15.7% |
| 并发压力 2GB | baseline | SLIM-ARC | Prefill +7.8%，Decode +5.8% |

### 5.4 3GiB 主实验、长 Prompt、多轮对话与 RSS

队友随后通过 `systemd-run --user --scope` 创建了用户级 cgroup。固定 80B Q4_K_M、
4 threads、`pp128/tg64`、KV q4_0、`MemorySwapMax=0` 的 F 组结果如下：

| 编号 | 配置 | MemMax | Prefill | Decode | 同档比较 |
|---|---|---:|---:|---:|---|
| F1 | baseline | 3GiB | 3.85 | 0.70 | reference |
| F2 | SLIM-ARC | 3GiB | 4.40 | 2.21 | Prefill +14%，Decode +216%（3.16×） |
| F3 | SLIM-ARC + KV eviction | 3GiB | 4.19 | 2.12 | Prefill +9%，Decode +203%（3.03×） |
| F4 | baseline | 2.5GiB | 3.97 | 1.91 | reference；单次波动明显 |
| F5 | SLIM-ARC + KV eviction | 2.5GiB | 4.26 | 2.21 | Prefill +7%，Decode +16% |

五组均未 OOM。2.5GiB baseline 单次结果高于 3GiB baseline，说明 page-cache 初始状态
会显著影响单次采样；只在各自内存档位内比较。

| 组别 | 合同 | 结果 | 解释 |
|---|---|---|---|
| G1/G2 | 80B，4GiB，4096 Prompt，baseline/SA+KV | 均 600s Prefill timeout，无 OOM | 超长 Prompt 的权重换页耗时超过测试预算 |
| G3/G4 | 80B，4GiB，8192 Prompt，baseline/SA+KV | 均 600s Prefill timeout，无 OOM | KV eviction 不缩短首次 Prefill |
| H1 | 4B，3GiB，五轮 baseline | Prompt 7.88、Generation 4.52 平均 | 首轮输入含 `echo -e` artifact |
| H2 | 4B，3GiB，五轮 SA+KV | Prompt 7.86、Generation 5.20 平均 | Generation +15%，探索性 |

RSS 补测使用 8 threads，与 F 组不能直接比较。三个 3GiB scope 的
`memory.current` 均触及 3072MiB；baseline/SLIM-ARC/SLIM-ARC+KV 的 VmHWM 分别为
4324/3986/3951MiB。内核 5.10 缺少 `memory.peak`，因此 cgroup 峰值通过 0.5s 轮询获得。
进程 RSS 可能包含计费到外部 session cgroup 的文件页，不能与 scope current 直接相减。

证据：[F/G/H 汇总](../rk3588_test_notes/优势场景测试-2026-08-13/SLIM-ARC后续测试汇总-FGH-2026-08-13.md)、
[RSS 补测](../rk3588_test_notes/优势场景测试-2026-08-13/RK3588-SLIMARC-RSS内存峰值补测-2026-08-13.md)、
[F1 原始日志](../rk3588_test_notes/优势场景测试-2026-08-13/adv-scenario-F1-2026-08-13.txt)、
[F2 原始日志](../rk3588_test_notes/优势场景测试-2026-08-13/adv-scenario-F2-2026-08-13.txt)。

完整汇总：[RK3588 数据整理](../../reports/raw_analysis/rk3588-edge-test-summary.md)、
[优势场景报告](../rk3588_test_notes/优势场景测试-2026-08-13/RK3588-SLIMARC-优势场景测试报告-2026-08-13.md)、
[原始目录](../rk3588_test_notes/)。这些实验说明“固定 RANDOM”不能跨设备推广。

## 6. Mac/Colima 数据

### 6.1 8 月 11 日生存边界与 CPU 曲线

这一批原镜像存在 baseline-first `LD_LIBRARY_PATH`，所以标为 patched 的性能行实际加载
baseline `libllama.so`。**可保留**的是内存档位、cgroup/no-swap、真实 baseline 和 CPU 曲线；
patched 消融比较全部降为 C。

| 项目 | 结果 | 判定 |
|---|---|---|
| 80B 最低观察到的生存档位 | 2GiB | A：两次成功 |
| 80B 最低稳定档位 | 2GiB | A：cold + warm 成功 |
| 2 CPU | wall 75.06s | B |
| 4 CPU | wall 68.56s | B |
| 6 CPU | wall 66.28s | B：该轮最佳 |
| 8 CPU | wall 66.72s | B：收益饱和 |

原表与失效说明：[2026-08-11 summary](../macos_test_notes/2026-08-11/summary.md)。

修复动态库串用后还完成了独立 pressure-admission A/B，合同为同一 80B 模型、2GiB、
4 vCPU、no-swap、`pp64/tg16`：

| 配置 | Cold wall | Warm wall 中位 | `memory.peak` | 运行时行为 | 决策 |
|---|---:|---:|---:|---|---|
| pressure off | 63.32s | 55.255s | 2GiB | expert issued 3,759.6MiB，waste 2,407.4MiB | reference |
| reserve 512MiB | 62.41s | 60.77s | 2GiB | 17/17 throttled，effective/issued=0 | opt-in |
| reserve 1024MiB | 65.37s | 57.47s | 2GiB | 17/17 throttled，effective/issued=0 | opt-in |

该策略确实按 cgroup headroom 拦截 advice，但没有降低峰值，warm 反而回退，因此不进入默认
配置。证据：[pressure-admission summary](../macos_test_notes/2026-08-11/pressure-admission-summary.md)、
[结构化结果](../macos_test_notes/2026-08-11/pressure-admission-results.json)。

### 6.2 8 月 12 日身份绑定正式矩阵

固定合同：80B Q4_K_M、2GiB、4 CPU、no-swap、`pp64/tg16`，每配置 cold/warm 各两轮；
20/20 成功，所有 `memory.peak` 均为 2GiB。

| 配置 | Cache | Wall 中位(s) | Decode 中位(t/s) | Major faults | 相对 patched-control | 决策 |
|---|---|---:|---:|---:|---|---|
| baseline | cold | 69.530 | 0.600242 | 250,177.5 | wall +4.87%，decode -12.83% | reference |
| patched-control | cold | 66.300 | 0.688606 | 406,601.5 | reference | reference |
| patched-reclaim | cold | 63.390 | 0.732030 | 403,548 | wall -4.39%，decode +6.31% | opt-in；本轮回收计数为 0 |
| patched-residency | cold | 66.160 | 0.692031 | 403,203 | wall -0.21%，decode +0.50% | opt-in |
| patched-combined | cold | 79.525 | 0.667540 | 399,309 | wall +19.95%，decode -3.06% | **rejected** |
| baseline | warm | 53.535 | 1.231783 | 143,727.5 | 比 patched-control 更快 | reference |
| patched-control | warm | 60.300 | 0.820575 | 331,466.5 | reference | reference |
| patched-reclaim | warm | 58.080 | 0.844204 | 347,946 | wall -3.68%，decode +2.88% | opt-in；回收计数为 0 |
| patched-residency | warm | 63.190 | 0.712126 | 350,215.5 | wall +4.79%，decode -13.22% | opt-in |
| patched-combined | warm | 63.265 | 0.759589 | 344,376.5 | wall +4.92%，decode -7.43% | opt-in/总体拒绝 |

结构化证据：[finals-results.json](../macos_test_notes/2026-08-12/finals-results.json)、
[CSV](../macos_test_notes/2026-08-12/finals-evidence.csv)、
[结论](../macos_test_notes/2026-08-12/finals-validated-summary.md)。

### 6.3 8 月 13–14 日优化筛选账本

除特别注明外，以下为 Mac/Colima、80B、2GiB、no-swap、CPU-only cold 实验。每行只在
本轮固定合同内比较。

| 编号 | 优化/对照 | 关键数据 | 决策 | 证据 |
|---|---|---|---|---|
| A1 | latest-wins + pressure | 2GiB cold `pp 3.951 / tg 0.800 / wall 57.16s`；1GiB 仍成功 | 保留研究路径 | [summary](../macos_test_notes/2026-08-13/a1-slow-storage-summary.md) |
| A4 | Prefill 8 / Decode 6 threads | Decode +20.23%，wall -5.91%，major faults -5.33% | 设备参数候选 | [summary](../macos_test_notes/2026-08-13/a4-phase-thread-summary.md) |
| A5 | Expert RANDOM | Decode `0.801 → 0.262`，wall `55.90 → 96.42s` | 拒绝 | [summary](../macos_test_notes/2026-08-13/a5-expert-madv-summary.md) |
| A6 | Expert NORMAL | Decode `0.801 → 0.657`，wall `55.90 → 61.08s` | 拒绝 | [summary](../macos_test_notes/2026-08-13/a6-expert-madv-normal-summary.md) |
| A7/A12 | Worker poll | 50 优于 25/75/100 | 保留 50 | [A7](../macos_test_notes/2026-08-13/a7-poll-summary.md)、[A12](../macos_test_notes/2026-08-13/a12-poll-boundary-summary.md) |
| A8 | Shared expert residency | Decode +3.07%，wall -5.40% | 保留 opt-in | [summary](../macos_test_notes/2026-08-13/a8-shared-residency-summary.md) |
| A9 | MLOCK_ONFAULT | Decode -3.39%，wall +0.60% vs eager | 拒绝替换 eager | [summary](../macos_test_notes/2026-08-13/a9-onfault-locking-summary.md) |
| A10 | Decode thread 5/6/7 | 6 线程 `tg 0.834 / wall 55.31s`；7 虽 tg 0.848 但 wall 55.89 | 保留 6 | [summary](../macos_test_notes/2026-08-13/a10-decode-thread-summary.md) |
| A11 | Readahead 128/192/256KB | 256KB Prefill 4.732、wall 51.77s；Decode 低于 128KB | Pareto 参数，不硬编码 | [summary](../macos_test_notes/2026-08-13/a11-readahead-shared-summary.md) |
| A13/A14 | Small always-used tensors | 短 `tg +0.11%`；长 `tg -0.72%` | 不推广 | [A13](../macos_test_notes/2026-08-13/a13-small-residency-summary.md)、[A14](../macos_test_notes/2026-08-13/a14-sustained-decode-summary.md) |
| A15 | Shared expert sustained | Decode `0.937 → 1.025`，wall `101.87 → 96.36s` | 保留 | [summary](../macos_test_notes/2026-08-13/a15-shared-sustained-summary.md) |
| A16 | 256KB sustained readahead | Prefill +13.39%，Decode +2.10%，wall -6.39% | Mac 候选 | [summary](../macos_test_notes/2026-08-13/a16-sustained-readahead-summary.md) |
| A17 | Graph 后 hot cache | Decode -2.07%，wall +0.54% | 拒绝时机 | [summary](../macos_test_notes/2026-08-13/a17-hot-cache-summary.md) |
| A18 | Inline Router + hot512 | Decode +10.35%，Prefill +3.51%，wall -7.77% | 保留 | [summary](../macos_test_notes/2026-08-13/a18-inline-hot-cache-summary.md) |
| A20 | Layer-local 32MiB pipeline | Decode +1.03%，fault -4.09%，I/O -5.10%，Prefill -2.10% | opt-in | [summary](../macos_test_notes/2026-08-14/a20-layer-local-expert-pipeline-summary.md) |
| A22 | Cross-layer Router Top2 | Decode +9.96%，wall -7.77%，hit 88.56%；仍慢于 A20 | 科研原型 | [summary](../macos_test_notes/2026-08-14/a22-cross-layer-prefetch-summary.md) |
| A23 | Online transition Top4 | 三轮波动大，未形成稳定优势 | opt-in，不推广 | [summary](../macos_test_notes/2026-08-14/a23-online-transition-summary.md) |
| A24 | 禁用 expert speculative prefetch | 三轮中位 Prefill +10.66%，Decode +22.45%，wall -15.72% | Mac/Pi 慢盘候选 | [summary](../macos_test_notes/2026-08-14/a24-no-expert-prefetch-summary.md) |
| A25 | 关闭整个 prefetch runtime | Mac Decode -16.91%，wall +18.09% | 拒绝；不能连有益路径一起关 | [summary](../macos_test_notes/2026-08-14/a25-no-prefetch-summary.md) |
| A32/A33 | Weight prefetch on/off | Mac on `tg 1.083 / wall 92.19s`，off `tg 1.022 / wall 96.14s` | Mac 保留 on；Pi 相反 | [summary](../macos_test_notes/2026-08-14/a32-a33-weight-prefetch-cross-device-summary.md) |

### 6.4 8 月 17 日终态复核

| 项目 | 数值 |
|---|---:|
| 合同 | 2GiB、4 CPU、swap 0、cold、`pp64/tg16` |
| 状态 | success，exit 0，无 OOM |
| Prefill | 3.908455 t/s |
| Decode | 0.709095 t/s |
| Wall | 58.06s |
| `memory.peak` | 2,147,483,648B |
| Maximum RSS | 2,084,740KiB |
| Major faults | 402,118 |
| Expert samples | 816 |
| Expert advice/issued/waste | 0 / 0B / 0B |
| Weight issued/skipped | 151,824,785,408B / 1,899,768,147,968B |

这是可运行性终态复核，不是新的 A/B 提升率。证据：[summary](../macos_test_notes/2026-08-17/final-validation-summary.md)、
[run manifest](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/run-manifest.json)、
[controller result](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/controller-result.json)。

## 7. Raspberry Pi 5 数据

### 7.1 早期 Qwen3-4B 基线

| 场景 | Prefill | Decode | 内存/备注 |
|---|---:|---:|---|
| microSD 冷启动 llama-cli | 0.3 | 0.4 | RSS 2.36GB，swap 1.6GB |
| 热缓存 `pp64` | 3.96±0.56 | — | 冷热差异约 13× |
| 修复后 `pp64/tg32` | 10.16±0.23 | 3.48±0.13 | upstream `1c3c967` + patch |
| 修复后 `pp128/tg64` | 6.88 | 2.93 | 较长 workload |
| RSS 测量 | — | — | Peak RSS 2.42GiB，未 OOM |

证据：[Pi 4GB 早期整理](../../reports/raw_analysis/pi5-4gb-edge-test-summary.md)。Dense 4B 不触发
MoE expert path，因此这些数据主要验证构建、mmap、KV 和 FlashAttention 基线。

### 7.2 80B 慢盘优化序列

固定主合同：Pi 5 4GB、4 threads、80B Q4_K_M、USB NTFS/FUSE、cold、运行期 no-swap；
主要 workload 为 `pp16/tg16`。

| 编号 | 改动 | Prefill | Decode | Wall | 机制指标/结论 | 决策 |
|---|---|---:|---:|---:|---|---|
| [A23](../pi5_4GB_test_notes/2026-08-14-a23-noswap-screen/summary.md) | Online transition Top4 | 0.200179 | 0.055052 | 550s | expert advice -61.16%，TPS 无改善 | 原型，不默认 |
| [A24](../pi5_4GB_test_notes/2026-08-14-a24-noswap-screen/summary.md) | 禁用 expert prefetch | 0.201104 | 0.055614 | 547s | expert advice 归零 | 慢盘基线 |
| [A26](../pi5_4GB_test_notes/2026-08-14-a26-hot512-summary.md) | Resident-only hot512 | 0.200578 | 0.060726 | 522.5s | vs A24 Decode +9.19%，wall -4.48% | 保留 |
| [A28](../pi5_4GB_test_notes/2026-08-14-a28-hot512-shared-summary.md) | Shared + resident hot512 | 0.204023 | 0.063486 | 511s | vs A24 Decode +14.16%，wall -6.58% | 当前强基线 |
| [A29](../pi5_4GB_test_notes/2026-08-14-a29-budget16-summary.md) | 总预算 16MiB | 0.204283 | 0.063585 | 510.5s | weight issued/inflight -98.44%，TPS 持平 | 保留 |
| [A32](../pi5_4GB_test_notes/2026-08-14-a32-a33-weight-prefetch-summary.md) | 关闭 weight prefetch | 0.203642 | 0.065246 | 505s | weight speculative I/O=0 | Pi 默认候选 |
| [A33](../pi5_4GB_test_notes/2026-08-14-a32-a33-weight-prefetch-summary.md) | 同环境 weight control | 0.203043 | 0.065006 | 505s | 恢复 60.59MiB issued，无收益 | Pi 关闭 / Mac 保留 |
| [A34](../pi5_4GB_test_notes/2026-08-14-a34-a35-hot-lru-summary.md) | 512MiB cross-token LRU | 0.203585 | 0.065856 | 503s | hits +6.53%，evictions -36.31% | 保留 opt-in |
| [A35](../pi5_4GB_test_notes/2026-08-14-a34-a35-hot-lru-summary.md) | 384MiB LRU | 0.202685 | 0.064198 | 510s | evictions +121.10% vs A34 | 拒绝 |
| [A36](../pi5_4GB_test_notes/2026-08-15-a36-a37-hot-lfru-summary.md) | 512MiB LRU 复测 | 0.204150 | 0.066158 | 500s | 两次中位 | 参考 |
| [A37](../pi5_4GB_test_notes/2026-08-15-a36-a37-hot-lfru-summary.md) | LFRU | 0.200884 | 0.064845 | 507.5s | hits +5.51% 但 Decode -1.99% | 拒绝复杂策略 |
| [A38–A40](../pi5_4GB_test_notes/2026-08-15-a38-a40-hot-admission-summary.md) | 二次命中准入变体 | 约 0.094 prefill | — | 早停 | Prefill 约 -54%；组合路径退化 | 拒绝 |
| [A41](../pi5_4GB_test_notes/2026-08-15-a41-a42-ntfs3-summary.md) | NTFS-3G/FUSE | 0.204150 | — | — | 1MiB direct 69.24MiB/s | 保留 mmap 路径 |
| [A42](../pi5_4GB_test_notes/2026-08-15-a41-a42-ntfs3-summary.md) | NTFS3 read-only | 0.070032 | — | — | direct 108.90MiB/s，但 mmap 路径更慢 | 拒绝 |
| [A43](../pi5_4GB_test_notes/2026-08-15-a43-fuse-prefetch32-summary.md) | 32MiB expert prefetch | 0.092975 | — | 早停 | 控制变量名写错 | **失效 C** |
| [A44](../pi5_4GB_test_notes/2026-08-15-a44-hot768-summary.md) | hot768 | 0.092539 | — | 早停 | 控制变量名写错 | **失效 C** |
| [A45](../pi5_4GB_test_notes/2026-08-15-a45-a47-file-advice-repro-summary.md) | 精确文件预读 on | 0.093601 | — | 早停 | vs A46 -0.2517% | 无收益，拒绝 |
| [A46](../pi5_4GB_test_notes/2026-08-15-a45-a47-file-advice-repro-summary.md) | 精确文件预读 off | 0.093837 | — | 早停 | 同源码 control | reference |
| [A47](../pi5_4GB_test_notes/2026-08-15-a45-a47-file-advice-repro-summary.md) | 旧源码复现 | 0.094405 | — | 早停 | 与 A45/A46 同一慢簇 | reference |
| [A49](../pi5_4GB_test_notes/2026-08-15-a48-a52-routed-topk-summary.md) | Routed Top-8 | 0.054285 | 0.029354 | 528s | 修复 view 后成功 | Top-8 仅研究 |
| [A50](../pi5_4GB_test_notes/2026-08-15-a48-a52-routed-topk-summary.md) | Routed Top-10 | 0.046178 | 0.026556 | 546s | Top-8 更快；质量题均答 50% | Top-8 仅研究 |

对应证据按编号位于 [Pi 数据目录](../pi5_4GB_test_notes/)，其中每个 `*-summary.md` 均有
同名 JSON 和原始运行目录。A48 的 exit 134 是旧图形状触发 `ggml_view_2d` 断言，不计入性能样本；
A51/A52 只做质量题，不能据此推广 Top-8。

### 7.3 Pi 的最终策略边界

| 路径 | Pi 慢盘结论 | Mac/快存储结论 |
|---|---|---|
| Expert speculative prefetch | 关闭；高命中率也未转化为 TPS | A24 在本地筛选有收益，但需固定合同 |
| Weight speculative prefetch | 关闭，A32 与 on 持平且少 I/O | A33 on 比 off 更快 |
| Shared expert residency | 保留 | 也可作为 opt-in |
| Hot expert cache | 512MiB resident-only LRU | Inline hot cache 有收益 |
| 文件预读 | FUSE 上无收益 | 需按存储重新测量 |
| 更复杂准入/LFRU | 指标变好不等于端到端变快，拒绝 | 不直接外推 |

## 8. 华为 HiDevLab / Ascend 数据

### 8.1 兼容性探测

| 项目 | 结果 | 等级 |
|---|---|---|
| 架构/设备 | aarch64 Linux，Ascend 910B4，HBM 32GiB | D |
| `npu-smi` | 25.2.0，Health OK | D |
| 系统 Python | 3.11.6 | D |
| CANN/torch_npu | 系统缺少匹配 toolkit；复用环境缺 `libhccl.so` | D：未执行 NPU 算子 |
| 隔离性 | 仅在独立目录运行，发现其他比赛 NPU 进程后停止探测 | D |

### 8.2 OLMoE CPU-only A/B

固定合同：OLMoE-1B-7B Q2_K 2,562,763,232B、16 threads、`pp64/tg16`、3 repetitions、
warm page cache、mmap、offline。为了让小模型进入 runtime，仅在隔离构建把 admission guard 从
6GiB 降至 2GiB，仓库默认未修改。

| 配置 | Prefill | Decode | Wall | Max RSS KiB | 结论 |
|---|---:|---:|---:|---:|---|
| baseline | 100.724597 | 51.340323 | 3.254600 | 2,575,956 | native reference |
| patched-default | 101.175889 | 45.254024 | 3.415535 | 2,577,888 | Decode -11.85% vs baseline |
| patched-A24 | 100.602680 | 48.184150 | 3.373611 | 2,577,380 | vs default Decode +6.47%；vs baseline -6.15% |
| patched-no-prefetch | 99.618235 | 45.803109 | 3.457525 | 2,577,572 | 未胜 A24 |
| patched-dynamic-normal | 100.326690 | 47.396683 | 3.443797 | 2,577,576 | 未胜 A24 |
| patched-dynamic-random | 100.237988 | 44.155583 | 3.535042 | 2,577,052 | 最慢 Decode |
| patched-sequential-prefetch | 99.443328 | 47.358331 | 3.484104 | 2,578,344 | 未胜 A24 |

这组结果证明 POSIX/llama.cpp 路径在华为 aarch64 环境可移植，并说明小模型、内存充足、
热页缓存不是 SLIM-ARC 的优势区间。它不是 CANN/NPU 加速数据。证据：
[说明](../ascend_test_notes/2026-08-17/README.md)、
[完整 JSON](../ascend_test_notes/2026-08-17/olmoe-q2-runtime-ab.json)、
[硬件探测 JSON](../ascend_test_notes/2026-08-17/ascend-smoke.json)。

## 9. 跨设备优化决策账本

| 优化 | WSL/x86 | RK3588 | Mac | Pi 5 | HiDevLab CPU | 总体决策 |
|---|---|---|---|---|---|---|
| 关闭 CPU repack | 必需 | 必需 | 构建基线 | 必需 | 构建基线 | **保留** |
| mmap/demand paging | 核心 | 80B 可运行基础 | 2GiB 生存基础 | 80B/4GB 基础 | 可移植 | **保留** |
| 静态 MADV_RANDOM | 早期曾正向 | 4–6× 负优化 | cold 下可能灾难性 | 不适合慢 FUSE | 最慢候选 | **拒绝默认** |
| 动态阶段建议 | 方向正确 | 恢复到 2.84/1.40 | 保留 SEQUENTIAL | 按慢盘收缩 | A24 最好 patched | **设备化保留** |
| 盲目 expert prefetch | 命中不稳定 | confidence 可减 I/O | A24 关闭后更快 | 关闭且不损性能 | issued=0 | **不默认** |
| Router/transition predictor | 科研路径 | temporal 34.9% | A22 hit 88.56% 但非总体最佳 | 高命中仍未加速 | 未形成收益 | **opt-in 研究** |
| Shared/hot expert residency | 未系统测 | 可选 | A18 有收益 | A28/A34 有收益 | 小模型无明显价值 | **按设备保留** |
| Reclaim wrong pages | 未测 | 机制路径 | 正式矩阵调用为 0 | 曾真实回收但 wall 持平 | 未触发 | **opt-in 正确性功能** |
| Pressure residency | 未测 | 受限场景相关 | 2GiB critical fail-closed | 需压力源 | 小模型不适用 | **opt-in** |
| Weight prefetch | 混合 | 设备相关 | on 优于 off | off 持平且少 I/O | advice 发生但无收益归因 | **设备化** |
| KV q4_0 | 8GiB 有价值 | 小模型变慢/长上下文省内存 | 本轮非主瓶颈 | 可运行、短上下文收益小 | 未测 | **按内存压力启用** |
| KV eviction | 长上下文能力 | 8192/16384 正常 | 非终态主项 | 短上下文不触发 | 未测 | **长上下文 opt-in** |
| FlashAttention | 热缓存计算路径收益 | Qwen3-4B 明显 | 由 upstream/backend 决定 | 小模型短上下文差异小 | CPU-only未专测 | **兼容时保留** |
| IQ4_XS | 速度/体积收益 | 未作为最终端侧主线 | 未用于决赛固定模型 | 未用 | 未用 | **精度风险，不作为默认** |
| Speculative decoding | -53.2% | 未继续 | 未继续 | 未继续 | 未测 | **拒绝当前实现** |

## 10. 证据目录

| 内容 | 人类可读入口 | 机器可读/原始入口 |
|---|---|---|
| 初赛总报告 | [Competition_Report](../../reports/Competition_Report/main.pdf) | [LaTeX 评测章节](../../reports/Competition_Report/sections/05_evaluation.tex) |
| 决赛增量报告 | [Competition_Report_Finals](../../reports/Competition_Report_Finals/main.pdf) | [LaTeX 评测章节](../../reports/Competition_Report_Finals/sections/05_evaluation.tex) |
| 初赛原始分析 | [raw_analysis](../../reports/raw_analysis/) | `reports/logs/` 与各分析文档链接 |
| Mac 8/11 | [summary](../macos_test_notes/2026-08-11/summary.md) | [runs](../macos_test_notes/2026-08-11/runs/) |
| Mac 8/12 | [validated summary](../macos_test_notes/2026-08-12/finals-validated-summary.md) | [finals-results.json](../macos_test_notes/2026-08-12/finals-results.json) |
| Mac 8/13–14 | 各 `a*-summary.md` | 同目录 summary JSON + run manifests |
| Mac 8/17 | [final validation](../macos_test_notes/2026-08-17/final-validation-summary.md) | [final run](../macos_test_notes/2026-08-17/ecospec-a24-final-2g-4c-pp64-tg16-cold/) |
| Pi 5 | [全部 Pi 数据](../pi5_4GB_test_notes/) | 每轮 raw 目录 + summary JSON |
| RK3588 | [总整理](../../reports/raw_analysis/rk3588-edge-test-summary.md) | [全部 RK 数据](../rk3588_test_notes/) |
| Ascend/HiDevLab | [README](../ascend_test_notes/2026-08-17/README.md) | [A/B JSON](../ascend_test_notes/2026-08-17/olmoe-q2-runtime-ab.json) |
| 队内决赛说明 | [final-stage-summary](../finals/2026-final-stage-summary.md) | 本索引列出的设备证据 |

## 11. 对外引用建议

最稳妥的三条主结论是：

1. **可运行性**：48.41GB 的 Qwen3-Next-80B-A3B Q4_K_M 在 Mac/Colima 的
   2GiB cgroup、4 CPU、no-swap 合同下成功完成 `pp64/tg16`，末次 Prefill 3.908455、
   Decode 0.709095 t/s。
2. **设备自适应**：RK3588 证明静态 RANDOM 会严重负优化，而动态阶段策略把
   `0.44/0.26` 恢复到 `2.84/1.40 t/s`；固定页建议不能跨设备复制。
3. **慢盘治理**：Pi 5 上 A28 相对 A24 的 Decode +14.16%、wall -6.58%；进一步的
   预算和 LRU 主要减少无效 I/O、命中和淘汰，不应夸大为跨平台加速。

华为结果应表述为“Ascend 开发环境里的 aarch64 CPU-only 可移植性和系统 A/B”，不能写成
“910B NPU 加速”。初赛高倍数结果可作为研发历史展示，但当前答辩应优先引用上面三条和
本文件中的固定合同。
