# SLIM-ARC 决赛阶段做了什么

这份说明是写给队内看的，不是比赛报告的摘要。我尽量把“做了什么、数据怎么样、哪些话能对裁判说、哪些不能说”分开写清楚。

## 先说结论

初赛版本已经证明 80B MoE 可以靠 mmap、量化和运行时页管理在远小于模型文件大小的内存里运行。决赛没有推翻这条主线，而是把它补成了一个更完整的系统：预取可以撤回，错误页可以安全回收，内存压力会改变专家驻留策略，后台任务和模型映射有明确的生命周期，实验也能绑定到模型、源码、二进制和资源限制。

设备侧的结论不是“同一组参数到处都快”。RK3588、树莓派、Mac 和 HiDevLab 给出的最佳策略并不相同。我们现在有足够的反例说明，静态 `MADV_RANDOM`、盲目专家预取和提前文件读都可能拖慢推理。决赛版本真正站得住的地方，是能根据阶段、压力和设备特征减少无效 I/O，而不是宣传某个固定开关。

## 初赛已有的基础

初赛已经完成了这些工作：

- 以 llama.cpp 为执行底座，使用 mmap 和按需缺页避免一次性把全部权重常驻内存。
- 关闭 CPU repack，避免 45GB 级模型在加载阶段膨胀到约 90GB。
- 支持 Q4/IQ4 等量化模型，并对 KV cache、FlashAttention、StreamingLLM 等路径做过实验。
- 接入 MoE Router hook，尝试跨层预测和专家预取。
- 在 RK3588 等设备上跑通 Qwen3-Next-80B-A3B。

初赛材料里有一些跨设备、跨缓存状态的高倍数结果。决赛审计后没有继续沿用这些数字。现在报告只保留环境和证据链能对齐的结果。

## 决赛新增的运行时改动

### 1. 预取状态不再靠裸指针共享

旧实现里，Router hook 和预取线程会并发读写同一批 `vector`，而且图执行拿到的是内部 `data()` 指针。只要另一个线程扩容或覆盖 vector，就可能出现悬空指针。

决赛版改为在锁内做值快照，在锁外执行 `madvise`。同一层的多次预测使用不复用的 generation token 对账。成功、空结果、缺少 Router 节点和计算失败都会结算或取消 token，不会把上一轮的预取错误记到下一轮，也不会把待结算队列永久占满。

### 2. runtime 跟随模型生命周期

旧版调度器和 mmap 区域由进程全局指针保存。模型卸载后，后台线程仍可能访问已经失效的地址。

现在 runtime 由模型对象持有。图执行先取得 lease；模型销毁时停止接受新 lease，等待在途任务结束，再 join worker，最后释放映射。这个改动主要解决长期运行和重复加载模型时的竞态，不直接贡献 TPS，但它让后续预取、回收和驻留策略可以安全地放在同一个运行时里。

### 3. 错误专家页可以安全回收

新增页边界计算和 expert reclaim planner。系统只对完整落在专家切片内部的页调用 `DONTNEED`，不会误丢仍被选中专家的页，也不会把相邻 tensor 的半页算进去。回收过程先在锁内生成计划，系统调用在锁外执行；只有成功的调用才进入 reclaimed bytes。

这项功能保留为 opt-in。Mac 正式矩阵里，回收配置虽然跑通，但八次启用运行的 `reclaim_calls` 和 `reclaimed_bytes` 都是 0，所以报告只写机制正确性，不写性能提升。

### 4. 专家驻留改成压力状态机

驻留控制器把 cgroup 内存压力分成 normal、high 和 critical，并加入恢复滞回，避免在阈值附近反复切换。normal 可以考虑 stable、temporal 和 hot experts；high 只保留稳定集合；critical 直接拒绝新的专家驻留。浪费率用整数 EWMA 计算，popularities 每 64 个有效 Router sample 衰减一次。

Mac 2GiB 正式矩阵中，驻留配置每次都进入 critical，记录 768 个 critical samples、13,929,971,712 skipped bytes、0 admitted bytes。它按设计 fail closed，但没有带来性能收益，所以同样保持 opt-in。

### 5. 权重预取加入统一预算和节流

权重页建议不再无限发出。调度器会合并区间、限制每轮 issued bytes，并记录 requested、covered、issued、skipped、coalesced ranges 和 throttled rounds。树莓派 A29 的 16MiB 预算把投机 weight I/O 降低 98.44%，吞吐基本不变；这说明大量提前读原本并没有转化成计算收益。

### 6. 按阶段和设备选择页建议

RK3588 的 80B 实验是这项改动的直接原因。静态 `MADV_RANDOM` 在该设备上把 `p32/n16/t4` 降到 0.44/0.26 t/s；禁用后为 2.74/1.41 t/s。改为阶段感知策略后达到 2.84/1.40 t/s。Prefill 适合顺序预读，Decode 是否保留预读要看设备，不能把一个平台的静态参数复制到另一个平台。

树莓派的 USB + NTFS-3G/FUSE 更极端。`POSIX_FADV_WILLNEED` 没有改善队列深度，也没有减少读取量，A45 相对 control 为 -0.251714%。最后保留的方向是常驻 shared/hot 路径、限制或关闭投机 I/O，以及 512MiB 的跨 token LRU。

## 各设备目前能说的数据

### Mac：80B 在 2GiB、no-swap 下可以完成

8 月 17 日用当前 A24 终态做了一次 cold 复核：

- 模型：Qwen3-Next-80B-A3B-Instruct Q4_K_M，48,410,988,384 B。
- 资源：2GiB、4 CPU、swap 0。
- Prefill：3.908455 t/s。
- Decode：0.709095 t/s。
- Wall：58.06s。
- memory.peak：2,147,483,648 B，进程没有 OOM。
- Expert advice 为 0，说明 `SLIM_ARC_NO_EXPERT_PREFETCH=1` 确实生效；模型靠 demand paging 完成。

这是一条“当前版本还能稳定跑完”的证据，不是新的提升率。原始记录在 `docs/macos_test_notes/2026-08-17/`。

8 月 12 日还有两轮、五配置、cold/warm 共 20 次的身份绑定矩阵。20/20 成功，峰值都碰到 2GiB。combined cold 的中位 wall 比 patched-control 慢 19.947%，因此 combined 被拒绝；这组负面结果已经写进报告，没有包装成收益。

### RK3588：动态阶段策略修复了静态 RANDOM 的严重负优化

这个设备最能说明为什么要做阶段感知策略。静态 RANDOM 会把大块顺序读拆成同步小缺页，弱核、DMA/SMMU 和中断路径的固定开销被放大。动态策略恢复 Prefill，并让 Decode 接近禁用路径。相关原始记录在 `docs/rk3588_test_notes/`。

队友随后补齐的 F/G/H/R 系列把结论扩展到了严格内存限制、长 Prompt、多轮对话和 RSS：

- F1/F2 在 3GiB、4 threads、`pp128/tg64`、swap 0 下对比：baseline 为 3.85/0.70 t/s，SLIM-ARC 为 4.40/2.21 t/s，Decode 提高 216%（3.16 倍），Prefill 提高约 14%。
- F3 加入 KV eviction 后为 4.19/2.12 t/s。短工作负载下它没有超过 SLIM-ARC，说明主要收益来自权重页策略，而不是 KV 驱逐。
- F4/F5 在 2.5GiB 下分别为 3.97/1.91 和 4.26/2.21 t/s。baseline 单次值高于 3GiB baseline，说明缓存初态会放大波动，所以只能在 2.5GiB 档内比较，不能宣传“内存越小越快”。
- G1--G4 的 4096/8192 Prompt 在 4GiB 下都在 600s Prefill 超时，但没有 OOM。这证明长 Prompt 的主要问题是权重换页和扫描时间，不是模型无法装入虚拟地址空间。
- H1/H2 的 4B 五轮对话中，Generation 均值从 4.52 提高到 5.20 t/s（约 15%），Prompt 基本持平；H1 有 `echo -e` 输入 artifact，因此只作为探索性结果。
- R3/R4/R5 使用 8 threads 做 RSS 补测，baseline、SLIM-ARC、SLIM-ARC+KV 的 VmHWM 分别为 4324、3986、3951MB。三者的 user scope `memory.current` 都触及 3072MB；由于进程 RSS 与 cgroup 文件页计费边界不同，这两类内存数不能直接相减。

这批数据已经整理到决赛报告正文、完整附录和 `docs/results/README.md`，不会再只剩 PPT 截图里的“0.70 到 2.21”。

### 树莓派 5：慢盘上“少读”比“早读”重要

树莓派阶段做了 resident cache、shared expert mlock、统一预算、替换策略、文件系统预读和 top-k 质量实验。当前比较有价值的结果是：

- A28 相对 A24：Decode +14.16%，wall -6.58%。
- A29 相对 A28：吞吐约在正负 0.2% 内，但 issued/in-flight weight bytes 都降低 98.44%。
- A32/A33：完全关闭 weight/expert speculative advice 后，两次 wall 都是 505s，Decode 反而 +0.37%。
- 512MiB LRU 相比旧 cache：evictions -36.31%，hits +6.53%，Decode +0.93%。
- 更复杂的 LFRU、两次命中准入和提前文件读都没有保留。

top-8 只保留为带质量门的实验方向，不能只看 TPS 就推广。

### 华为 HiDevLab：跑通真实 MoE 的系统开/关 A/B，但不是 NPU 加速

HiDevLab 的新独立环境可以编译 `aarch64` llama.cpp。SLIM-ARC 目前没有 CANN backend，所以这组 OLMoE 数据跑的是 CPU-only POSIX/mmap 路径。模型是 OLMoE-1B-7B Q2_K，2,562,763,232 B；为了让小模型真实进入 runtime，只在隔离实验构建中把 6GiB admission guard 降到 2GiB。

同模型、16 线程、`pp64/tg16`、三次重复的结果：

| 配置 | Prefill t/s | Decode t/s | Wall s | Max RSS KiB |
|---|---:|---:|---:|---:|
| baseline | 100.724597 | 51.340323 | 3.254600 | 2,575,956 |
| SLIM-ARC default | 101.175889 | 45.254024 | 3.415535 | 2,577,888 |
| SLIM-ARC A24 | 100.602680 | 48.184150 | 3.373611 | 2,577,380 |

A24 相对 default 的 Decode 高 6.47%，wall 低 1.23%；相对 baseline 仍是 Decode -6.15%、wall +3.66%。这是合理的负面结果：2.56GB 模型、内存充足、页缓存已热，本来就不是按需分页系统的目标负载。patched 运行各有一条 schema 3 runtime 指标，`expert_samples=785`，weight advice 真实发生；`expert_issued_bytes=0`，所以不能说专家预取在这组实验里带来加速。

完整数据在 `docs/ascend_test_notes/2026-08-17/olmoe-q2-runtime-ab.json`。损坏的 Q8 下载及分片已经清理，没有继续占用远端磁盘。

## Agent Harness 放在什么位置

Agent Harness 是低优先级扩展，不是决赛主贡献。报告把它放在评测之后，定位为“如何让运行时节省不被上层编排浪费”，而不是把项目包装成 Agent 框架。

实现很小：

- 连接常驻 OpenAI-compatible endpoint，避免每次工具调用重新加载模型。
- 保留稳定 system prefix，只发送最近对话，并截断过长工具输出。
- 模型只能返回 `shell` 工具调用或最终答案；shell 使用 argv allowlist，不使用 `shell=True`，拒绝绝对路径和 `..`。
- 每步有超时、输出上限和总步骤上限。
- 当输出 TPS 低于阈值时，下一轮 `max_tokens` 从 192 按 0.65 缩到 124，避免慢设备继续生成无用长答案。
- JSONL 记录模型耗时、工具耗时、估算 TPS、截断和预算变化。

当前确定性 smoke 已完成 `model -> uname -m -> observation -> final`，并有截图和 10 个单元测试。它只证明闭环、预算调整和受限 shell 正常，没有真实模型的 Harness 开/关 A/B，所以报告没有给它写性能提升。

## 代码和材料上的收尾

- 决赛报告独立放在 `reports/Competition_Report_Finals/`，初赛 `reports/Competition_Report/` 保留。
- 决赛报告已经按标准论文逻辑重组为引言、背景与相关工作、系统设计、系统实现、实验评估、总结和附录；Design 与 Implementation 分开，实验先主结果、再消融和设备专项。
- 队友更新的三张图已替换进决赛报告对应 figure；PPT 由队友继续维护，本轮不改 PPT。
- 评测图不再使用简单柱状图：Mac 使用两轮原始值、极差和中位数区间图，RK3588 使用策略响应温度图，Pi 使用多目标 Pareto 图，并补充跨设备同合同效应矩阵。
- Mac、RK3588、树莓派和 HiDevLab 的结论都绑定到各自证据目录，不能跨设备相除。
- GitLab 发布历史已经按官方仓库需求清理；GitHub 仍是完整开发历史的恢复源。任何 `AGENTS.md`、`.agents`、`.codex`、`.omo` 和内部计划都不应进入对外仓库。

## 给裁判讲时建议怎么说

主线可以概括成一句话：SLIM-ARC 把大模型权重和专家访问看成受预算约束的页工作集，通过阶段感知建议、Router 反馈、压力驻留和安全回收，在极小物理内存里维持可运行推理。

然后用三类证据支撑：Mac 证明 48GB 的 80B 模型能在 2GiB/no-swap 下完成；RK3588 和树莓派说明策略必须匹配真实存储链路；HiDevLab OLMoE A/B 说明代码可以移植到 `aarch64`，也如实暴露小模型热缓存场景的开销。

不要说“所有平台都加速”，也不要说“已经完成 Ascend NPU 优化”。现在能说的是，CPU/POSIX 路径已经在华为开发环境跑通，CANN backend 仍是后续工作。
