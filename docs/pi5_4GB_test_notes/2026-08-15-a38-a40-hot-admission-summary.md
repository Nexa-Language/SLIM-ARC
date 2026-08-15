# A38-A40: hot-expert admission screen

## 结论

在 A36 的 512 MiB hot-expert LRU 上，把准入阈值从首次命中提高到两次命中，三个实现均出现
几乎相同的确定性负收益。A36 LRU 的两次 cold-run prefill 中位数为 `0.20415 t/s`；A38
全阶段准入为 `0.0943808 t/s`，A39 仅 decode 阶段准入为 `0.0942793 t/s`，A40 仅在
缓存接近满载时准入为 `0.0937173 t/s`，分别下降 `53.77%`、`53.82%` 和 `54.09%`。

因此在 Pi 5 + Qwen3-Next 80B 上拒绝 `SLIM_ARC_EXPERT_HOT_ADMIT_HITS=2`，继续使用默认
`SLIM_ARC_EXPERT_HOT_ADMIT_HITS=1`。阈值大于一的实现保留为严格 opt-in，不纳入树莓派的
性能配置。

## 为什么三个版本都退化

Qwen3-Next 的 recurrent 层在 prefill 期间仍会拆成 `n_tokens=1` 的 microbatch。因而用
“batch token 数”区分 prefill/decode 会误判；即使把过滤延后到缓存接近 512 MiB 上限，
第一次遇到的专家仍可能在后续 recurrent microbatch 立即复用。等待第二次命中才驻留，恰好
淘汰了这条跨 microbatch 的热路径。

| 筛选 | 准入范围 | Prefill t/s | 相对 A36 | 终止状态 |
|---|---|---:|---:|---|
| A38 | 所有阶段 | 0.0943808 | -53.77% | prefill 后主动停止 |
| A39 | 观测到的 decode 阶段 | 0.0942793 | -53.82% | prefill 后主动停止 |
| A40 | hot cache 接近满载后 | 0.0937173 | -54.09% | prefill 后主动停止 |

三次筛选都使用 Pi 5、4 GiB、4 线程、cold cache、运行期间 no-swap、pp16/tg16，以及
Samsung 870 EVO SSD over USB 3 + NTFS-3G/FUSE。它们在 decode 尚未完成时被有意停止，
所以 `exit=143`、wall 仅表示停止前时间，不能作为完整运行性能；结束后 zram 均已恢复且
Used 为 0。结论只使用已经写入 `stdout.jsonl` 的 prefill 行，不推断 decode TPS。

## 下一步

重复命中准入已经被真实硬件反馈否决。下一轮不再继续调 admission 阈值，而是优先验证底层
存储路径：同一 Samsung 870 EVO 当前走 `usb-storage` 与用户态 NTFS-3G/FUSE，先用只读
内核 NTFS3 A/B 分离文件系统开销，再决定是否继续做应用层 I/O 合并或异步读。
