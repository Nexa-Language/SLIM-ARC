# A28 分层专家驻留：Pi5 慢盘当前最优

## 结论

A28 在 A26 的 resident-only hot expert cache 上，增加约 94.8MB always-on shared expert 常驻。
两次 Raspberry Pi 5 cold/no-swap 运行分别为 513s 和 509s，中位 511s。相对只关闭专家预取的
A24：

- Prefill: `0.201104 -> 0.204023 t/s`，`+1.45%`。
- Decode: `0.055614 -> 0.063486 t/s`，`+14.16%`。
- Wall: `547 -> 511s`，`-6.58%`。

相对已重复确认的 A26，A28 仍把 decode 提高 `4.54%`、wall 再降低 `2.20%`。因此 shared
expert 常驻与 hot routed expert cache 的收益能够叠加。

| Run | Prefill (t/s) | Decode (t/s) | Wall (s) | Shared locked | Hot locked | Hot hits | Lock failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| r1 | 0.203135 | 0.0630510 | 513 | 94,765,056 | 254,066,688 | 1,691 | 0 |
| r2 | 0.204910 | 0.0639218 | 509 | 94,765,056 | 234,815,488 | 1,691 | 0 |

两次运行的 `expert_issued_bytes` 都是 0；shared/hot mlock 都是 0 failure；zram 在每次运行后恢复。
这证明收益来自保留已经确定有用的页，不是增加推测性磁盘读取。

## 当前 Pi slow-storage 配置

```bash
SLIM_ARC_NO_EXPERT_PREFETCH=1 \
SLIM_ARC_EXPERT_HOT_MB=512 \
SLIM_ARC_SHARED_MLOCK=1
```

该组合对应三层策略：

1. routed expert miss 交给 demand paging，避免低命中 `WILLNEED` 争用机械盘。
2. 连续 token 重用且已经驻留的 routed expert 进入 512MiB resident-only hot cache。
3. 每 token 必经的 shared expert 固定常驻约 94.8MB。

这与调研建议的“always-on path 常驻 + per-layer expert cache + miss fallback”一致，但当前结论完全
来自本机两轮原始数据。下一阶段需把双方 merge 后的最新源码增量构建到 Pi，再测试总权重预算和
块设备队列参数；旧 A23 二进制不支持 `SLIM_ARC_TOTAL_BUDGET_MB`。
