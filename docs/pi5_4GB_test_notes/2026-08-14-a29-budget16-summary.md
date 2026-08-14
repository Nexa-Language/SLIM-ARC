# A29：慢盘统一预取预算收缩到 16 MiB

## 结论

A29 保留 A28 已验证的三项配置：关闭专家推测预取、512 MiB resident-only hot expert cache、
always-on shared expert 常驻；只新增 `SLIM_ARC_TOTAL_BUDGET_MB=16`，限制统一调度器每轮可用于
weight/KV/expert 的投机 I/O 总预算。

两次 Raspberry Pi 5 冷启动、无 swap、pp16/tg16 结果表明，它没有牺牲 A28 的吞吐或完成时间，
却把 weight `WILLNEED` 实际发出量从 `3891.14 MiB` 降至 `60.59 MiB`，把峰值在途量从
`614.39 MiB` 降至 `9.59 MiB`，两者均下降约 `98.44%`。这说明 A29 已经从“大范围投机换入”
收敛到“少量顺序提示 + 真实 demand fault”，更适合 USB NTFS/FUSE 旋转盘。

## 固定实验口径

- Raspberry Pi 5，4 GiB，4 线程，Qwen3-Next-80B-A3B Q4_K_M。
- 模型位于 USB NTFS/FUSE 旋转盘；每轮开始前 drop page cache。
- `pp=16`、`tg=16`、`--no-warmup`，运行期间 swap=0，退出后 zram 已恢复。
- 当前生成源码哈希：`05af794afe6df8fe84be5238131499bebb0f7ce0af5191ff822b9ba232437855`。

```text
SLIM_ARC_NO_EXPERT_PREFETCH=1
SLIM_ARC_EXPERT_HOT_MB=512
SLIM_ARC_SHARED_MLOCK=1
SLIM_ARC_TOTAL_BUDGET_MB=16
```

## 原始结果

| 运行 | Prefill t/s | Decode t/s | Wall | Weight issued | Inflight peak |
|---|---:|---:|---:|---:|---:|
| A29 r1 | 0.203950 | 0.0642558 | 508 s | 60.59 MiB | 9.59 MiB |
| A29 r2 | 0.204615 | 0.0629134 | 513 s | 60.59 MiB | 9.59 MiB |
| A29 中位数 | 0.2042825 | 0.0635846 | 510.5 s | 60.59 MiB | 9.59 MiB |
| A28 中位数 | 0.2040225 | 0.0634864 | 511.0 s | 3891.14 MiB | 614.39 MiB |

相对 A28，A29 中位数 prefill `+0.13%`、decode `+0.15%`、wall `-0.10%`；这些性能差异属于
噪声范围，因此不把它们描述为额外 TPS 加速。可复现且显著的增量是预取 I/O 和在途页量均下降
`98.44%`，同时所有 expert/shared/hot advice 的失败计数仍为 0。

相对最初 A24 demand-paging 配置，完整的 A29 驻留与预算组合达到 decode `+14.33%`、wall
`-6.67%`。下一步只改变块设备队列参数，判断内核层能否继续掩盖 FUSE/旋转盘的 fault latency。
