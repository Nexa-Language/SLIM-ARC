# A19: 1 GiB inline expert-cache boundary

Qwen3-Next-80B-A3B Q4_K_M 在 1 GiB cgroup v2、swap=0、8 CPU 下完成了 cold pp64/tg64：control 为 5.3015 prefill tok/s、1.0427 decode tok/s、90.66 s，内存峰值正好达到 1 GiB，且没有 OOM。

动态稳定命中 expert cache 在该内存档位不应启用：

- 64 MiB：decode -0.17%，prefill -0.44%，wall +0.13%；
- 128 MiB：decode -1.16%，prefill +1.40%，wall +0.64%。

两档都减少了 major faults 和 I/O，但锁页挤压了已经顶满的动态工作集，最终没有改善端到端性能。因此分档配置为：

- 1 GiB：关闭 `SLIM_ARC_INLINE_ROUTER`、`SLIM_ARC_EXPERT_HOT_MB` 和固定 resident sets；
- 2 GiB：启用 `SLIM_ARC_INLINE_ROUTER=1`、`SLIM_ARC_EXPERT_HOT_MB=512`。

本轮只保留结构化摘要及小型 cgroup/run manifest；模型、镜像和可再生 stdout/stderr 不进入 Git。
