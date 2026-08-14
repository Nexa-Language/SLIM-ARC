# A34–A35：跨 token hot-expert LRU

## 结论

A34 在现有“连续 token 稳定专家才准入”的门槛上，把立即同层替换改成 512 MiB 预算内的
跨 token LRU：未满预算时保留已 resident 并成功 `mlock` 的专家页，满额后只淘汰最久未使用且
不属于当前稳定集合的条目。

Pi 5 的两次 cold/no-swap pp16/tg16 中，A34 wall 为 `499 s` 和 `507 s`，中位数 `503 s`；
decode 中位数 `0.06585635 t/s`。相对同环境 A32 legacy hot cache，decode `+0.93%`、wall
`-0.40%`。该吞吐增量不大，但 cache 机制改善明确：evictions 中位数下降 `36.31%`，hits 增加
`6.53%`，且没有 expert/weight speculative advice 或 lock failure。

## 对照

| 配置 | 样本 | Prefill t/s | Decode t/s | Wall | Locked | Entries | Admissions | Hits | Evictions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A32 legacy hot 512 | 2 | 0.203642 | 0.0652464 | 505 s | 302.20 MiB | - | 990 | 1691 | 811 |
| A34 LRU hot 512 | 2 | 0.2035845 | 0.06585635 | 503 s | 511.73 MiB | 363 | 879.5 | 1801.5 | 516.5 |
| A35 LRU hot 384 | 1 | 0.202685 | 0.0641983 | 510 s | 382.23 MiB | 228 | 1370 | 1311 | 1142 |

A35 把预算降到 384 MiB 后，evictions 相对 A34 增加 `121.10%`、hits 下降 `27.23%`、decode
下降 `2.52%`，wall 增加 `1.39%`。因此不复跑 384 MiB，保留 512 MiB。

## 边界

- 这是 Raspberry Pi USB NTFS/FUSE 旋转盘上的设备策略，不直接替换 Mac 默认。
- `SLIM_ARC_EXPERT_HOT_LRU=1` 保持 opt-in；没有该变量时仍执行旧策略。
- LRU 只锁定已经 resident 的页，不主动 fault-in 冷专家，因此没有重演预测错误造成的额外磁盘读。
- zram 在每次实验结束后均恢复，三次运行期间 swap 为 0。

所有数值均可从三个 raw 目录的 `stdout.jsonl`、`stderr.log`、`wall-seconds.txt` 和内存快照复算。
