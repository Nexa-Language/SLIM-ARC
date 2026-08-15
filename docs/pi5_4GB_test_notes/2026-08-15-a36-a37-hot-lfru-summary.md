# A36–A37：hot-expert LRU 与 LFRU

## 结论

A37 在 A36 的 512 MiB 跨 token LRU 上增加 `frequency / age` 受害者评分。两组配置都关闭
speculative expert/weight prefetch，使用相同 Pi 5、USB 3 Samsung 870 EVO SSD、NTFS-3G/FUSE、4 线程、cold cache、
no-swap、pp16/tg16 合同，并按 LRU → LFRU → LFRU → LRU 反向交错运行。

LFRU 的缓存计数优于 LRU：中位 admissions 下降 `10.08%`，hits 增加 `5.51%`，evictions
下降 `20.43%`。但这没有转化为端到端收益：wall 增加 `1.50%`，prefill TPS 下降
`1.60%`，decode TPS 下降 `1.99%`，且中位 nonresident 扫描字节增加 `56.33%`。

因此树莓派慢盘候选继续使用纯 LRU，不设置 `SLIM_ARC_EXPERT_HOT_LFRU=1`。LFRU 保持严格
opt-in，供后续在 NVMe、Mac 和不同 token 长度上单独评估；本轮不把缓存命中数替代为性能结论。

## 对照

| 配置 | 样本 | Prefill t/s | Decode t/s | Wall | Entries | Admissions | Hits | Evictions | Nonresident |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A36 LRU 512 | 2 | 0.20415 | 0.06615835 | 500.0 s | 323 | 947 | 1734 | 624 | 161.93 MiB |
| A37 LFRU 512 | 2 | 0.2008835 | 0.06484465 | 507.5 s | 355 | 851.5 | 1829.5 | 496.5 | 253.14 MiB |
| LFRU 相对 LRU | - | -1.60% | -1.99% | +1.50% | +9.91% | -10.08% | +5.51% | -20.43% | +56.33% |

## 下一步

LFRU 说明“保留得更久”本身不够：Pi 的关键是避免为了低价值条目做 resident-page 扫描和 `mlock`
管理。下一轮优先测试 admission，而非继续堆替换策略：只有候选的历史频率足以胜过当前受害者时才
准入，减少 churn 与扫描成本；仍保持不主动 fault-in 冷页。

四次运行均 `exit=0`，运行期间 `/proc/swaps` 为空，结束后 zram 已恢复。所有数值都可由四个
raw 目录的 `stdout.jsonl`、`stderr.log`、`wall-seconds.txt`、`policy.env` 和系统快照复算。
