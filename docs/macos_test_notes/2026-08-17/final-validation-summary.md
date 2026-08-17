# 2026-08-17 Mac A24 最终运行复核

这是一条赛前终态复核，不是新的 A/B 结论。它回答的是：当前镜像能否继续在固定的 2 GiB、4 CPU、no-swap 条件下完成 80B MoE 推理，以及 A24 的“关闭专家投机预取”开关是否确实生效。

## 固定条件

- 模型：`Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`
- 模型大小：48,410,988,384 B
- 模型 SHA-256：`d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`
- llama.cpp：`360e134`
- 资源：2 GiB、4 CPU、swap 0
- 工作负载：`pp64/tg16`、cold cache、seed 1、no warmup、mmap、offline
- 环境：`SLIM_ARC_DECODE_MADV=SEQUENTIAL`、`SLIM_ARC_DYNAMIC_MADV=1`、`SLIM_ARC_NO_EXPERT_PREFETCH=1`

## 结果

| 项目 | 数值 |
|---|---:|
| 运行状态 | success，exit 0，无 OOM |
| Prefill | 3.908455 t/s |
| Decode | 0.709095 t/s |
| Wall time | 58.06 s |
| memory.peak | 2,147,483,648 B |
| Maximum RSS | 2,084,740 KiB |
| Major page faults | 402,118 |
| File-system inputs | 199,548,696 blocks |
| Expert samples | 816 |
| Expert advice requests / issued / waste | 0 / 0 B / 0 B |
| Weight advice requests | 34,594 |
| Weight issued / skipped | 151,824,785,408 B / 1,899,768,147,968 B |

`expert_advice_requests=0` 与 `expert_issued_bytes=0` 直接说明 A24 精确关闭了专家 `WILLNEED`；模型仍通过 demand paging 完成推理。由于只有一次运行，而且镜像与 8 月 12 日矩阵不同，这些数字不能与旧结果相除后写成提升率。

原始证据位于 `ecospec-a24-final-2g-4c-pp64-tg16-cold/`，包括 controller result、run manifest、llama-bench JSON、GNU time、cgroup 前后快照和运行时指标。
