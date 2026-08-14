# A32–A33：weight prefetch 的 Mac 跨设备边界

## 结论

使用当前 `23c6fbb0` 镜像，在 Mac/Colima aarch64、2 GiB cgroup、8 CPU、no-swap、
pp64/tg64 和 guest cold cache 下做了两轮反序交错 A/B。除
`SLIM_ARC_NO_WEIGHT_PREFETCH=1` 外，关闭组与开启组完全一致。

Mac 保持 weight-prefetch 默认开启；`SLIM_ARC_NO_WEIGHT_PREFETCH=1` 只作为树莓派 USB
NTFS/FUSE 旋转盘策略使用，不升级成通用默认值。

## 结果

| 配置 | 样本 | Prefill t/s | Decode t/s | Wall | Major faults | File inputs | Weight requests | Weight issued |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A33 weight prefetch on | 2 | 4.548372 | 1.0831545 | 92.190 s | 1,290,391.5 | 398,198,328 | 1,105 | 0 |
| A32 weight prefetch off | 2 | 4.492960 | 1.0223615 | 96.135 s | 1,311,420.5 | 404,167,388 | 0 | 0 |

关闭组相对开启组的 prefill 为 `-1.22%`、decode 为 `-5.61%`、wall 为 `+4.28%`；
major faults 和 file-input 计数分别增加 `1.63%` 和 `1.50%`。

## 解释边界

开启组每次生成 1,105 个 weight advice 请求，并覆盖约 64.76 GiB 的候选范围，但在 2 GiB
pressure admission 下全部被预算拒绝：`weight_issued_bytes=0`。关闭组把这些请求和 skipped
计数清零，也同样没有发出实际 weight advice。

因此不能把 Mac 的 `5.61%` decode 差异解释成异步磁盘预取收益；更可能是缺页时序、宿主
文件缓存或调度噪声的综合结果。比赛策略以设备实测为准：

- Mac/较快存储：保留默认路径，它在当前屏幕中更快。
- Raspberry Pi 5/慢盘：使用 `SLIM_ARC_NO_WEIGHT_PREFETCH=1`；Pi A32/A33 已在同环境下保持
  `505 s` wall，同时把实际 weight issuance 从 `60.59 MiB` 降为 0。

所有数字均可从同目录四个 `run-manifest.json`、`rep-1.stdout.log` 和
`rep-1.time.txt` 复算。
