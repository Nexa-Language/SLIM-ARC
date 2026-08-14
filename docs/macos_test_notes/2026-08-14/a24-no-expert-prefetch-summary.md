# A24 禁用低命中专家预取：Mac 筛选

## 结论

现有 `SLIM_ARC_NO_EXPERT_PREFETCH=1` 开关在 2 GiB、无 swap、cold-cache 的 Qwen3-Next-80B 测试中连续三轮优于 control。三轮中位数为：

- Prefill: `3.553070 -> 3.931758 t/s`，`+10.66%`
- Decode: `0.738163 -> 0.903851 t/s`，`+22.45%`
- Wall: `128.36 -> 108.18s`，`-15.72%`
- File-system inputs: `437,573,248 -> 401,655,792`，`-8.21%`

该结果只提升 A24 为树莓派候选。Mac Colima 的 cold-I/O 波动较大，不能单独作为最终性能结论。

## 动机

同一镜像的 control 专家预取命中率只有约 41%；树莓派 `tg4` control 的命中率更低，只有 11.68%。错误的 `POSIX_MADV_WILLNEED` 会与真实按需缺页争用慢盘带宽。A24 保留 Router 观测、hot-expert 统计和系统按需缺页，仅禁止预测专家页 advice；模型计算与精度路径不变。

这对应调研中“错误预取应回退到 demand paging / CPU fallback，而不是强制提交错误 I/O”的边界。当前实现复用已有严格开关，没有新增代码或内存结构。

## 原始结果

| Run | Prefill (t/s) | Decode (t/s) | Wall (s) | Major faults | FS inputs |
|---:|---:|---:|---:|---:|---:|
| 1 | 3.879570 | 0.941653 | 105.56 | 1,276,187 | 401,655,792 |
| 2 | 4.085922 | 0.858675 | 111.29 | 1,297,627 | 409,085,224 |
| 3 | 3.931758 | 0.903851 | 108.18 | 1,272,128 | 400,668,320 |

三轮 runtime metrics 均确认 `expert_advice_requests=0`、`expert_issued_bytes=0`，不是开关未生效或日志误归因。

## 下一门槛

在树莓派同一 USB 模型文件、4 核、禁 swap、cold cache 下先跑 `pp16/tg4`。若短 decode 有收益，再用 `tg16` 验证稳态；若板卡不赢，则保持 A24 为 Mac/虚拟化环境的可选配置，不设为默认。
