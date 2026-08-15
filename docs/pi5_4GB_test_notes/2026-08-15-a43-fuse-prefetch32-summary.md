# A43：FUSE 上的 32 MiB 专家预取筛选

## 结论

在树莓派 5 的当前 SSD 路径（USB 3.0 Bulk-Only + NTFS-3G/FUSE）上，重新启用受 32 MiB
预算约束的 expert `WILLNEED` 预取后，pp16 prefill 只有 `0.0929747 t/s`。相对 A36 的
FUSE + 512 MiB hot-expert LRU 两次 cold-run 中位数 `0.20415 t/s`，下降
`54.46%`。因此拒绝该配置，后续继续保持 weight prefetch 和 expert prefetch 都关闭。

该结果说明“限制预取量”不足以解决当前存储路径的问题：即使只有 32 MiB，推测性专家读取
仍会和同步缺页竞争同一条 Bulk-Only/FUSE I/O 通道。当前更值得验证的是增加已经证明有效的
hot-expert resident set，而不是增加另一条预取流。

## 固定条件

- 模型：Qwen3-Next-80B-A3B-Instruct Q4_K_M，llama-bench 报告大小
  `48,405,005,312` bytes。
- llama.cpp：`360e1349f0009c5ad99d21e3c4546b707addc68a`。
- SLIM-ARC：`d41cda703642c15a3268684a88b4ce677253ad48`。
- `pp=16`、`tg=16`、4 threads、cold cache、swap off。
- expert prefetch budget：32 MiB；weight prefetch：off。
- hot-expert cache：512 MiB，LRU，首次命中准入，共享 mlock。

## 结果边界

A43 是早停筛选：prefill 行写入后，在 decode 阶段主动终止，故 `exit=143`、wall=633 秒。
这里只使用完整写出的 prefill TPS；不把该 wall time 或尚未完成的 decode 当作性能结果。
运行前后 swap 都为 0，结束后 zram 保持恢复但未使用，模型挂载保持原 NTFS-3G/FUSE。

结构化结果见 `2026-08-15-a43-fuse-prefetch32-summary.json`，原始控制器产物见
`2026-08-15-a43-fuse-prefetch32-tg16-r1/`。
