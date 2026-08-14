# A32–A33：关闭 weight prefetch 的同环境归因

## 结论

A32 新增 `SLIM_ARC_NO_WEIGHT_PREFETCH=1`，但保留 model-wide phase advice、shared/hot
expert 常驻、统一 runtime 和 A29 的 16 MiB 总预算。它与 A25 的“关闭整个 runtime”不是同一消融。

A32 两次 cold/no-swap pp16/tg16 均为 `505s`，decode 中位数为 `0.0652464 t/s`；运行时
`weight_requested_bytes`、`weight_issued_bytes`、`weight_advice_requests`、
`weight_inflight_peak_bytes` 全部为 0，expert speculative advice 也仍为 0。

由于 A30 后内核把 `nr_requests` 从 2 钳制为 4，不能直接把 A32 相对 A29 的全部提升归因于代码。
因此 A33 使用同一二进制、同样 `nr_requests=4`、`read_ahead_kb=2048`，只移除
`SLIM_ARC_NO_WEIGHT_PREFETCH`。A33 同样得到 `505s`、decode `0.0650063 t/s`，但恢复了
`60.59 MiB` weight issuance 和 `9.59 MiB` 峰值在途页。

## 同环境结果

| 配置 | 样本 | Prefill t/s | Decode t/s | Wall | Weight issued | Inflight peak |
|---|---:|---:|---:|---:|---:|---:|
| A32 no weight prefetch | 2 | 0.203642 | 0.0652464 | 505 s | 0 | 0 |
| A33 weight control | 1 | 0.203043 | 0.0650063 | 505 s | 60.59 MiB | 9.59 MiB |

A32 相对 A33 的 prefill `+0.30%`、decode `+0.37%`、wall `0.00%`，属于性能持平；确定性增量是
weight speculative I/O 和在途页均下降 100%。shared/hot lock failure 均为 0，说明 runtime 的有益
驻留路径仍然存在。

## 决策

在 Raspberry Pi 5 的 USB NTFS/FUSE 旋转盘上推广 A32 作为 zero-speculation 慢盘策略：它保持
当前最佳完成时间和吞吐，同时消除剩余投机 weight I/O。该开关不会直接在 Mac/SSD 上默认启用，
必须先做独立 Mac A/B，因为更快存储可能从 60.59 MiB 的异步提示中获益。
