# A43：FUSE 上的 32 MiB 专家预取筛选

## 更正后的结论

在树莓派 5 的当前 SSD 路径（USB 3.0 Bulk-Only + NTFS-3G/FUSE）上，重新启用受 32 MiB
预算约束的 expert `WILLNEED` 预取后，pp16 prefill 只有 `0.0929747 t/s`。相对 A36 的
FUSE + 512 MiB hot-expert LRU 两次 cold-run 中位数 `0.20415 t/s`，下降
`54.46%`。但这轮后来发现没有严格保持 A36 控制变量，因此标记为失效，不能把全部回归
归因于 32 MiB expert prefetch。

启动命令误用了不存在的 `SLIM_ARC_EXPERT_HOT_SHARED_MLOCK` 和
`SLIM_ARC_EXPERT_TOTAL_BUDGET_MS`，而实际代码读取的是 `SLIM_ARC_SHARED_MLOCK` 和
`SLIM_ARC_TOTAL_BUDGET_MB`。因此 A43 意外关闭了 shared-expert mlock，并回退到默认总预算。
观测到的组合配置可以判定很慢，但若要评价 32 MiB 预取本身，必须使用正确 A36 环境重跑。

## 固定条件

- 模型：Qwen3-Next-80B-A3B-Instruct Q4_K_M，llama-bench 报告大小
  `48,405,005,312` bytes。
- llama.cpp：`360e1349f0009c5ad99d21e3c4546b707addc68a`。
- SLIM-ARC：`d41cda703642c15a3268684a88b4ce677253ad48`。
- `pp=16`、`tg=16`、4 threads、cold cache、swap off。
- expert prefetch budget：32 MiB；weight prefetch：off。
- hot-expert cache：512 MiB，LRU，首次命中准入；shared mlock 因变量名错误实际未启用。

## 结果边界

A43 是早停筛选：prefill 行写入后，在 decode 阶段主动终止，故 `exit=143`、wall=633 秒。
这里只使用完整写出的 prefill TPS；不把该 wall time 或尚未完成的 decode 当作性能结果。
运行前后 swap 都为 0，结束后 zram 保持恢复但未使用，模型挂载保持原 NTFS-3G/FUSE。
该行 TPS 只作为失效实验的原始观测保留，不进入单变量优化结论。

结构化结果见 `2026-08-15-a43-fuse-prefetch32-summary.json`，原始控制器产物见
`2026-08-15-a43-fuse-prefetch32-tg16-r1/`。
