# A18 inline router expert residency

## 结论

在 2 GiB cgroup v2、swap=0、8 CPU、pp64/tg64 的 Qwen3-Next-80B-A3B Q4_K_M 冷启动测试中，启用 inline router observation，并把稳定命中的 expert 完整页纳入 512 MiB `mlock` 热缓存，是本轮最优配置。

两次 512 MiB 候选的中位数相对 default-off control：

- decode：1.019083 → 1.124524 tok/s，提升 10.35%；
- prefill：5.261280 → 5.445879 tok/s，提升 3.51%；
- wall time：92.37 → 85.19 s，下降 7.77%；
- major faults：1,028,236 → 952,603.5，下降 7.36%；
- filesystem input blocks：453,055,720 → 433,311,724，下降 4.36%。

因此，2 GiB finalist profile 增加：

```text
SLIM_ARC_INLINE_ROUTER=1
SLIM_ARC_EXPERT_HOT_MB=512
```

## 为什么 A18 有效

A17 在 graph 完成后才扫描 router 输出，页面此时已经被本层 MoE 消费，导致绝大多数候选页不再 resident。A18 把 observation 移入 `ggml_backend_sched_eval_callback`：在 layer N+1 router 完成时结算 layer N，使刚被访问且连续命中的 expert 页能够被 `mincore` 确认并立即锁入热缓存。

512 MiB 两次运行分别形成 8,316 / 8,310 次 cache hit；实际锁定约 423 MiB，预算拒绝为 0。相较 64、128、256 MiB，512 MiB 同时给出最高 decode TPS 和最低墙钟、major faults、I/O 输入量。

## 证据边界

- 以上提升只适用于本文件记录的 2 GiB Mac/Colima CPU-only 合同，不外推到其他设备或内存档位。
- control 来自紧邻的 A17 default-off 镜像；A18 代码的两个新增开关默认关闭，因此运行路径等价，但二者 commit/image identity 不同。
- 512 MiB 仍观察到非 resident 候选和少量 `mlock` 失败；后续会在 1 GiB 和远端设备上重新选预算，不能直接照搬。
- 完整结构化数字、镜像/模型/source hash 和逐次运行目录见 `a18-inline-hot-cache-summary.json`。
