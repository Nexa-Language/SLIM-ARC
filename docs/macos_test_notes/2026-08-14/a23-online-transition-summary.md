# A23 在线跨层专家转移预测：Mac 筛选

## 结论

A23 Top4 进入树莓派无 swap 筛选，但尚未认定为稳定性能优化。三轮组内中位数显示 prefill `+12.34%`、decode `+12.64%`、wall `-9.41%`；考虑冷盘时序波动后，逐轮配对的 decode 中位提升只有 `+0.52%`，wall 中位仍为 `-9.41%`。

A23 不执行额外 Router 矩阵乘法。它用本 token 上一层真实激活在线学习 `(layer, source expert) -> next-layer experts`，并在下一次 decode 图中通过既有页预取路径发出请求。首个 decode 图只学习，不预测。

## 固定实验合同

- Model: Qwen3-Next-80B-A3B-Instruct Q4_K_M，SHA-256 `d103b273...3c061a`
- Image: `sha256:15c3bf31...bfaac3`
- Memory: 2 GiB cgroup v2，`memory.swap.max=0`
- CPU: 8 vCPU，CPU-only
- Workload: `pp64/tg64`，cold cache，单次 repetition
- Common path: inline Router、32 MiB expert pipeline、512 MiB hot budget、pressure admission

## 原始结果

| 配置 | Run | Prefill (t/s) | Decode (t/s) | Wall (s) | Major faults | FS inputs |
|---|---:|---:|---:|---:|---:|---:|
| Control | 1 | 3.790004 | 0.738163 | 128.36 | 1,264,169 | 493,426,048 |
| Control | 2 | 3.553070 | 0.720921 | 129.68 | 1,123,542 | 437,573,248 |
| Control | 3 | 3.527041 | 0.929391 | 127.43 | 1,136,379 | 434,148,240 |
| A23 Top2 | 1 | 3.669405 | 0.722105 | 130.63 | 1,193,824 | 408,869,000 |
| A23 Top4 | 1 | 3.893005 | 0.831489 | 116.28 | 1,287,767 | 445,450,368 |
| A23 Top4 | 2 | 3.991515 | 0.673784 | 133.33 | 1,166,088 | 412,176,488 |
| A23 Top4 | 3 | 4.481298 | 0.934223 | 101.52 | 1,352,124 | 454,691,312 |

Top2 预测 5,888 个专家、匹配 2,612 个；Top4 每轮预测 11,776 个、匹配 4,937 个。Top2 相对同轮 control 的文件系统读入减少约 17.1%，但 decode 下降 2.18%，因此不继续推广。

## 解释边界

Mac Colima 的 cold-cache 结果受宿主和虚拟机 I/O 调度影响很大。组内中位数适合筛选候选，不能代替慢盘板卡结论。因此，A23 只有在树莓派同一 eMMC/USB 模型文件、禁 swap、交错 cold-cache 复测中保持 wall 或 decode 收益后，才会成为默认推荐配置。
