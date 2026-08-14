# A23 在线跨层专家转移预测：树莓派筛选

## 结论

A23 Top4 保留为科研原型和 opt-in 开关，不设为树莓派默认配置。它显著减少了专家预取字节，但在短、长 decode 两个工作负载上都没有改善 wall time，长 decode 的 TPS 还略有下降。

| Workload | Metric | Control | A23 Top4 | Delta |
|---|---|---:|---:|---:|
| pp16/tg4 | Prefill (t/s) | 0.202419 | 0.200163 | -1.11% |
| pp16/tg4 | Decode (t/s) | 0.0550797 | 0.0551424 | +0.11% |
| pp16/tg4 | Wall (s) | 331 | 332 | +0.30% |
| pp16/tg4 | Expert advice bytes | 2,812,297,216 | 843,726,848 | -70.00% |
| pp16/tg16 | Prefill (t/s) | 0.201807 | 0.200179 | -0.81% |
| pp16/tg16 | Decode (t/s) | 0.0551405 | 0.0550520 | -0.16% |
| pp16/tg16 | Wall (s) | 549 | 550 | +0.18% |
| pp16/tg16 | Expert advice bytes | 14,063,108,096 | 5,462,360,064 | -61.16% |

## 解释

`tg4` 只得到 404 个预测专家、62 个匹配；`tg16` 学习窗口更长，得到 2,644 个预测、1,071 个匹配，但仍不足以把减少的后台 I/O 转化成可测吞吐。该结果否定“只要减少 WILLNEED 字节就会提速”的假设：慢盘场景更需要避免错误预测，而不是扩大预测覆盖。

## 实验边界

- Raspberry Pi 5，4 GiB，4 threads
- Qwen3-Next-80B-A3B-Instruct Q4_K_M，USB 模型盘
- `llama.cpp` pinned `360e134`
- cold cache；每对实验期间 zram 停用；结束后确认 `/dev/zram0` 已恢复
- 所有 case exit code 为 0，无 OOM

下一候选是 A24：保留系统 demand paging 和 Router 观测，完全关闭低命中专家 `WILLNEED`。
