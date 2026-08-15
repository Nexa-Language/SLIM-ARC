# A45–A47：精确 expert 文件预读与旧冷基线复现

## 结论

在树莓派 5 的 4 GiB 内存、NTFS-3G/FUSE 模型盘、USB Bulk-Only 传输、4 线程、no-swap、
pp16/tg16 条件下，A45 开启精确 expert 文件范围 `POSIX_FADV_WILLNEED`，prefill 为
`0.0936006 t/s`；匹配的 A46 关闭该开关，prefill 为 `0.0938368 t/s`。开启后下降
`0.251714%`，没有可推广的收益，因此树莓派慢盘默认继续关闭
`SLIM_ARC_EXPERT_FADVISE`。

A47 使用 A36 的精确源码提交、生成源码和运行策略重新构建，prefill 为
`0.0944048 t/s`，与当前 flag-off control 只差 `+0.605306%`，但比历史 A36 中位数
`0.20415 t/s` 低 `53.757139%`。因此后续代码变化不是这次速度下降的原因；更可能的原因是
过去的“cold”流程只清了 Linux page cache，无法证明 NTFS-3G/FUSE、USB bridge 和 SSD 内部缓存
都处于相同状态。

历史 A36/A37 在同一批次反向交错得到的相对 LRU/LFRU 结论继续保留，但不再把 A36 的
`0.20415 t/s` 当作后续跨批次实验的绝对 cold baseline。所有引用这一绝对值计算出的跨批次
提升或回归比例均不用于决赛性能结论。

## 对照

| 运行 | 源码 | 精确文件预读 | Prefill t/s | 相对 A46 | Wall 到停止 | 状态 |
|---|---|---:|---:|---:|---:|---|
| A45 | `1a5abcb5` | 开 | 0.0936006 | -0.251714% | 638 s | prefill 完成后在 decode 阶段停止 |
| A46 | `1a5abcb5` | 关 | 0.0938368 | control | 654 s | prefill 完成后在 decode 阶段停止 |
| A47 | `a1f57230` | 关 | 0.0944048 | +0.605306% | 634 s | 精确旧源码复现，decode 阶段停止 |

三轮都使用同一份 48 GB 模型，没有复制模型；运行时关闭 swap，结束后 zram 恢复且 Used 为 0。
远端没有残留 `llama-bench`。原始 JSONL、系统快照、退出状态、wall time 和精确策略都保存在
对应 A45、A46、A47 目录中。

## 下一步

`fadvise` 只把请求提前交给 FUSE/内核，没有减少实际读取量，也没有改变 Bulk-Only 队列深度，
因此不会继续扩大这个方向。下一轮应优先减少真正的 expert 文件读取字节，或把跨 token 的热点
驻留集合变成可复现的 warm-cache 工作负载；每个候选都与同一源码、相邻运行的 flag-off control
做 A/B，不再跨批次引用 A36 的绝对速度。
