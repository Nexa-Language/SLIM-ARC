# A24 关闭专家预取：树莓派慢盘筛选

## 结论

在 Raspberry Pi 5 的 USB NTFS/FUSE 模型盘上，完全关闭专家 `WILLNEED` 后，专家推测读取从
2.81GB/14.06GB 降为 0；`tg4` 和 `tg16` 的 wall time 都没有可测回归。`tg16` 从 549s
降至 547s，但目前每组只有一次冷缓存运行，不能把约 0.36% 的差异解释为稳定加速。

| Workload | Metric | A23 control | A24 no expert prefetch | Delta |
|---|---|---:|---:|---:|
| pp16/tg4 | Prefill (t/s) | 0.202419 | 0.197338 | -2.51% |
| pp16/tg4 | Decode (t/s) | 0.0550797 | 0.0562080 | +2.05% |
| pp16/tg4 | Wall (s) | 331 | 332 | +0.30% |
| pp16/tg4 | Expert advice bytes | 2,812,297,216 | 0 | -100.00% |
| pp16/tg16 | Prefill (t/s) | 0.201807 | 0.201104 | -0.35% |
| pp16/tg16 | Decode (t/s) | 0.0551405 | 0.0556140 | +0.86% |
| pp16/tg16 | Wall (s) | 549 | 547 | -0.36% |
| pp16/tg16 | Expert advice bytes | 14,063,108,096 | 0 | -100.00% |

## 解释

该结果和 2026-08-13 的 Pi5 A0–A4 矩阵一致：该设备被同步缺页和 FUSE 往返延迟支配，
增加大量推测性读盘不能减少 major faults 或 wall time。A24 至少避免了专家预取与真实 demand
fault 竞争同一块慢盘，也不再用错误预测挤占 4GiB 内存中的有效页缓存。

Mac 2GiB cgroup 的三次冷缓存筛选已经观察到 A24 wall 中位数从 128.36s 降至 108.18s
（-15.72%）。Pi 上的价值目前主要是消除无收益 I/O；是否作为 slow-storage 默认策略，仍需
做 A/B 交错重复，避免把缓存和盘速波动当成收益。

## 实验边界

- Raspberry Pi 5，4GiB RAM，4 threads；每次运行停用 zram，运行后恢复。
- Qwen3-Next-80B-A3B-Instruct Q4_K_M，模型位于 USB NTFS/FUSE 机械盘。
- `llama.cpp` pinned `360e134`；SLIM-ARC source commit `b693106b`。
- cold cache；`pp16/tg4` 和 `pp16/tg16` 各一次；所有 case exit code 为 0。
- `SLIM-ARC-RUNTIME schema=3` 记录 `expert_issued_bytes=0`、`expert_advice_requests=0`，
  证明专家 `WILLNEED` 路径未下发 I/O；权重级预取保持启用。
