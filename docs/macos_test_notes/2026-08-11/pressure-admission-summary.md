# 2 GiB Qwen3-Next-80B Pressure Admission A/B

## 结论

决策为 `kept_opt_in`：保留 pressure-aware prefetch 的实现、测试和运行时指标，但不在最终 demo 或默认配置中启用。

所有有效实验都使用同一 Qwen3-Next-80B-A3B Q4_K_M 模型、4 vCPU、2 GiB cgroup、no-swap、`pp64 + tg16`，并在修复 variant 动态库串用后重新运行。模型 SHA-256 为 `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`，llama.cpp 为 `360e1349f0009c5ad99d21e3c4546b707addc68a`。

| 配置 | Cold wall | Warm wall | Warm median | `memory.peak` | Pressure 行为 |
|---|---:|---:|---:|---:|---|
| pressure off | 63.32s | 52.12s, 58.39s | 55.255s | 2 GiB | expert issued 3759.6 MiB，waste 2407.4 MiB |
| reserve 512 MiB | 62.41s | 58.41s, 63.13s | 60.77s | 2 GiB | 17/17 throttled，effective/issued=0 |
| reserve 1024 MiB | 65.37s | 51.84s, 63.10s | 57.47s | 2 GiB | 17/17 throttled，effective/issued=0 |

512 MiB 相对 off 的 cold 快 1.44%，warm median 慢 9.98%；1024 MiB 的 cold 慢 3.24%，warm median 慢 4.01%。三组 `memory.peak` 都精确触及 2 GiB，内存峰值下降为 0%，所以即使墙钟回退没有超过 15%，也没有满足“内存至少下降 10%”的 promotion threshold。控制器安全下限为 2 GiB，本轮没有可测试的更低档，不能声称改善了 OOM boundary。

## 系统行为解释

pressure-off 的 corrected patched run 每次 expert prefetch 约 3.76 GiB，命中率 42.67%，约 2.41 GiB 被统计为 waste。pressure admission 确实把 weight/expert advice 全部挡住：有效 row 的 fallback 和 madvise failure 都为 0，说明限流来自真实 cgroup headroom，而不是读取失败。

但在 2 GiB 下，模型 mmap 页与运行时工作集已占满可用 headroom。默认 512 MiB、1024 MiB，甚至 exploratory `reserve=0`（仍保留 10% reserve）都得到 `effective=0`。因此这些 reserve 在本机上属于同一策略，512/1024 的时间差只能视为 page cache 与 I/O 噪声，不能用来挑选默认参数。

## 有效性修复

原镜像设置了 baseline-first `LD_LIBRARY_PATH`，导致 patched executable 实际加载 baseline `libllama.so`。旧的 patched survival、CPU、ablation 以及第一轮 pressure runs 已全部列入 `pressure-admission-results.json` 的 `invalidated_run_ids`；原始文件保留作审计，但不再用于任何性能结论。

修复后，`tests/macos/test-variant-linkage.sh` 使用真实镜像 `ldd` 强制验证 baseline/patched 各自链接到自身目录；corrected patched run 还必须出现 `[SLIM-ARC-PRESSURE]` 或 `[SLIM-ARC-METRICS]` 才可进入有效数据集。

## 最终展示建议

- 继续展示 2 GiB、4 vCPU、no-swap 下 80B-A3B 模型能够完成 `pp64 + tg16`，但只引用 corrected run IDs。
- 最终 demo 不设置 `SLIM_ARC_PRESSURE_ADMISSION`；pressure admission 作为可观测、可复用的 opt-in 机制保留。
- 后续若在 3–8 GiB 档或更长 context 下出现非零 headroom，再评估该 admission 是否能在不完全关闭预取的情况下减少回收与 major faults。

结构化证据见 `pressure-admission-results.json`，有效 raw runs 为：

- `pressure-valid-off-cold` / `pressure-valid-off-warm`
- `pressure-valid-512-cold` / `pressure-valid-512-warm`
- `pressure-valid-1024-cold` / `pressure-valid-1024-warm`
