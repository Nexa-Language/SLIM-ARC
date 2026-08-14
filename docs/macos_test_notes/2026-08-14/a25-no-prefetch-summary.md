# A25 完全关闭预取 runtime：跨设备淘汰结果

## 结论

`SLIM_ARC_NO_PREFETCH=1` 在 Mac 和 Raspberry Pi 5 上都显著慢于 A24，立即淘汰。
A24 只关闭错误率高的专家 `WILLNEED`，仍保留 model-owned runtime、Router 观察、稳定页常驻和
阶段策略；A25 则把整个 runtime 都关闭。结果证明不能把“减少无效 I/O”简化为“关闭所有系统机制”。

| Device/workload | Metric | A24 | A25 | A25 delta |
|---|---|---:|---:|---:|
| Mac 2GiB pp64/tg64 | Prefill (t/s) | 3.931758 | 3.521749 | -10.43% |
| Mac 2GiB pp64/tg64 | Decode (t/s) | 0.903851 | 0.750988 | -16.91% |
| Mac 2GiB pp64/tg64 | Wall (s) | 108.18 | 127.75 | +18.09% |
| Mac 2GiB pp64/tg64 | FS inputs | 401,655,792 | 510,967,872 | +27.22% |
| Pi5 4GiB pp16/tg16 | Prefill (t/s) | 0.201104 | 0.151455 | -24.69% |
| Pi5 4GiB pp16/tg16 | Decode (t/s) | 0.0556140 | 0.0423577 | -23.84% |
| Pi5 4GiB pp16/tg16 | Wall (s) | 547 | 662 | +21.02% |

Mac A25 的 `runtime_metrics_status=disabled`，Pi A25 没有任何 SLIM-ARC runtime 行，确认开关确实
关闭了 runtime。两端均 no-swap、cold cache、exit code 0；树莓派运行后 `/dev/zram0` 已恢复。

## 下一步

保留 A24 的精确边界：只禁止专家推测读盘。下一候选 A26 使用 resident-only hot expert cache：
只对已经 demand-fault 进入内存、并在连续 token 重复的专家页执行 `mlock`，不主动读取非驻留页，
目标是减少后续 token 的重复慢盘缺页。
