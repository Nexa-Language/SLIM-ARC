# A20: layer-local expert page-in pipeline

## 机制

`SLIM_ARC_EXPERT_PIPELINE_MB=32` 将 expert page-in 从 graph-start 全层突发改为逐层 double-buffer：首层在 graph 开始前提示；layer N router 就绪后，按上一 token 的同层历史和 `SLIM_ARC_EXPERT_CONF=1` 稳定集合，只提示 layer N+1；每层独立限制为 32 MiB。

该设计对应 survey 的 I/O request queue、低 queue-depth、sequential layer pipeline 和“当前层计算时读取下一层”。

## 两次有效 cold 结果

固定 2 GiB、swap=0、8 CPU、pp64/tg64、512 MiB hot cache。相对 A18 finalist 中位数：

- decode：1.124524 → 1.1360745 tok/s，提升 1.03%；
- wall：85.19 → 85.12 s，基本持平（下降 0.08%）；
- major faults：952,603.5 → 913,594.5，下降 4.09%；
- filesystem input blocks：433,311,724 → 411,213,404，下降 5.10%；
- prefill：5.445879 → 5.331467 tok/s，下降 2.10%。

两次运行的 pipeline 记账完全一致：下发 23,379,554,304 bytes，命中 15,970,897,920 bytes，浪费 7,408,656,384 bytes，命中率 68.31%；advice failure、invalid range、OOM 和 swap 均为 0。

## 决策

保留为慢存储 opt-in candidate，不替换 A18 默认 finalist。它已经重复证明能降低换入字节和 major faults，但本机高速虚拟盘上的 wall 中位数仅持平，仍需在真实 Pi/RK3588 或带宽受限环境确认端到端收益。

推荐继续验证的组合：

```text
SLIM_ARC_INLINE_ROUTER=1
SLIM_ARC_EXPERT_HOT_MB=512
SLIM_ARC_EXPERT_CONF=1
SLIM_ARC_EXPERT_PIPELINE_MB=32
```

首次 diagnostic 的 benchmark 成功，但旧 `run_manifest.py` 因缺少变量 allowlist 返回 error；该运行不进入性能统计，修复提交为 `566c6c20`。
