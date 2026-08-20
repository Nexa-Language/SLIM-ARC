# RK3588 代码审核专家提问预测与应答

- 编写日期：2026-08-21（答辩复核前准备）
- 用途：预测明天代码审核时专家最可能追问的问题，逐条给出应答要点与证据定位。
- 使用方式：审核前通读一遍，重点记住「高概率」标记的问题；被追问时先抛结论，再指证据。

---

## 一、代码实现类（审核打开代码时必问）

### Q1【高概率】动态 MADV 阶段切换是怎么实现的？代码在哪？

**应答**：`register_mmap_region()` 在模型 mmap 后记录所有映射区域；`set_phase()` 在 prefill/decode 切换时触发 `apply_dynamic_madv()`，对全部区域重设页建议——prefill 用 `SEQUENTIAL`（保顺序预读），decode 默认也 `SEQUENTIAL`（RK3588 场景），可用 `SLIM_ARC_DECODE_MADV=RANDOM/NORMAL` 覆盖。

**代码定位**：[`patches/llama-upstream/slim-arc-prefetch.cpp`](../../patches/llama-upstream/slim-arc-prefetch.cpp) 中 `apply_dynamic_madv()`（约 line 307 起，含 `SLIM_ARC_DECODE_MADV` 分支）。

**关键点**：强调「阶段切换是两级的」——阶段控制器给默认值，设备配置按存储链路覆盖 decode 行为。这不是写死一个最优值，而是机制与策略分离。

---

### Q2【高概率】decode 为什么默认 SEQUENTIAL 而不是 RANDOM？这是硬编码吗？

**应答**：不是硬编码，是**设备相关的默认值**。消融数据（[`80b专家预取消融-2026-08-08/`](../rk3588_test_notes/80b专家预取消融-2026-08-08/) 对应阶段的测试数据）显示：RK3588 45GB/8GB 极端比例下，decode 用 RANDOM 会 5.4× 拖慢（0.25 vs 1.40），因为随机小读把顺序读拆成同步缺页。所以 RK3588 默认 SEQUENTIAL，`SLIM_ARC_DECODE_MADV=RANDOM/NORMAL` 留给内存充足场景。

**证据**：decode 消融表 RANDOM 0.25 / SEQUENTIAL 1.35 / NORMAL 1.41，见 [`改进记录`](../rk3588_improvement/改进记录.md) 阶段 2b。

**引申**：WSL/x86 恰恰相反，decode 用 RANDOM 省 98% 无用预读是净收益——所以同一机制在两类硬件结论相反，这正是「设备化配置」的设计动机。

---

### Q3【高概率】generation token 是什么？为什么要用它对齐预测和事实？

**应答**：同一层在一个计算图里会重复出现，后台预取 worker 也可能晚于下一次 Router 观测完成。只按「层号」存「最近预测」会把两个轮次覆盖或错配。所以每次专家预取分配单调递增的 generation token，`cache_router_experts` 结算时只认**相同 token** 的记录；计算失败/无 Router 节点时显式 `cancel_expert_prefetch` 清理，避免 pending 队列被 64 个失败轮次耗尽。

**代码定位**：[`scripts/apply-slim-arc.py`](../../scripts/apply-slim-arc.py) 中 `patch_context` 的 `expert_generation_tokens`、`settle_pending()`、`cancel_expert_prefetch()`。

**关键点**：这是「预测可撤回、事实晚于预测」原则的工程落地——预测只是候选，原生 Router 结果才是权威。

---

### Q4【中概率】专家预取曾经是 0 次下发，你们发现了哪三个 bug？

**应答**（这是体现排查能力的亮点，主动讲）：
1. **层号解析失败**：`ffn_moe_topk-<N>`/`gate-<N>` 节点名无 `blk.` 前缀，`tensor_layer_from_name` 失败 → 用 `strrchr(t->name,'-')+atoi` 回退解析。
2. **层范围扫描失败**：decode 图节点导致 `min_layer=INT_MAX` → 预取块整体跳过 → 层扫描也加 `-<N>` 后缀回退。
3. **幂等性回归 bug**：patcher 用 `'ffn_moe_topk' not in content` 判断是否已插入，但注释里出现该字样导致误判跳过 → 插入标记改为 `'cache_router_experts'`。

**证据**：修复后 `issue_expert_willneed` 从 0 → 846 次（144 张量注册、912 次 router 提取、846 次 WILLNEED），见 [`改进记录`](../rk3588_improvement/改进记录.md) 阶段 5，原始调试日志在 [`80b专家预取消融-2026-08-08/dbg-*.txt`](../rk3588_test_notes/80b专家预取消融-2026-08-08/)。

---

### Q5【中概率】CONF（置信度门控）、BUDGET（预算）、POP（热门）三者实现和结论各是什么？

**应答**（改进记录阶段 11-14，文献驱动）：
- **CONF=1**：维护 2-token 路由历史，只对连续两 token 都激活的「稳定专家」发 WILLNEED → 命中率 31%→55%、下发 -56%，**速度无损，明确 WIN**。
- **BUDGET=1**：把专家预取纳入统一 I/O 预算（MOE_DECODE 专家占比 60%），按 step 累计截断 → 机制正确（能截突发），但 RK3588 解码非 I/O 受限，速度中性。
- **POP=16**：temporal ∪ top-K 热门专家并集 → issued +161%、命中率降至 19%，**诚实负结果**，默认关闭。

**代码定位**：[`slim-arc-prefetch.cpp`](../../patches/llama-upstream/slim-arc-prefetch.cpp) 的 `conf_gating_`、`pop_k_`、`parse_popularity_k()`；[`slim-arc-unified-scheduler.cpp`](../../patches/llama-upstream/slim-arc-unified-scheduler.cpp) 的 `SLIM_ARC_EXPERT_BUDGET` 分支（约 line 237）。

**关键点**：三者都是 env opt-in、默认关闭，体现了「机制提供、策略按设备选择、不吹不藏」的态度。

---

### Q6【中概率】补丁怎么保证幂等？上游变了会不会被静默忽略？

**应答**：`apply-slim-arc.py` 对指定 anchor 做幂等变换——重复应用后生成树 hash 不变；anchor 缺失时脚本直接失败，而不是跳过。另有 fixture 验证二次应用 byte-identical。

**代码定位**：[`scripts/apply-slim-arc.py`](../../scripts/apply-slim-arc.py) 的 `transform_model`/`transform_qwen3next`/`patch_context`。

---

## 二、数据可信度类（审核数据时必问）

### Q7【高概率】F 系列是 r=1 单次，为什么不做多次重复取均值？

**应答**：80B 冷启动一次约 2 分钟加载 + benchmark，且受「页缓存必须冲刷 + cgroup 限额必须真实触发」约束，当天串行跑完 F/G/H/R 全系列已到时间预算。诚实承认这是 **B 级证据**：3GiB 档内 F1→F2 的 3.16× 幅度远超单次波动，可信；2.5GiB 档的 +16% 在波动范围内，报告里已标注「单次波动」。

**补救口径**：R 系列（RSS 补测）用了 0.5s 轮询多采样（231 次），弥补了内存峰值的观测密度；若要补强吞吐结论，复现时把 `-r 1` 改为 `-r 3` 取中位数即可，命令已在复现文档里。

---

### Q8【高概率】为什么 2.5GiB baseline（tg 1.91）比 3GiB baseline（tg 0.70）还快？数据是不是有问题？

**应答**：不是规律，是 `r=1` 单次采样落在 page-cache 驻留窗口临界点附近的非单调波动。三个原因：① 匿名挤压法无法清零页缓存（残留 1.4GB，每轮集合不同）；② baseline 顺序 readahead 对驻留窗口非单调敏感（3G 预读更激进挤掉当前页，2.5G 恰好形成更好驻留组合）；③ F4 在 F3 后执行可能复用残留页。

**铁证**：F4 的 pp（3.97）也比 F1 的 pp（3.85）高——pp/tg 同时抬升，说明是「整轮初始状态好」，不是机制差异。**结论：只能档内比较，F1 vs F4 跨档不可比。** 详见复现文档 §6.1。

---

### Q9【中概率】冷启动公平性怎么保证的？页缓存怎么冲刷？

**应答**：无 sudo 无法 `drop_caches`，用 [`flush-pagecache.sh`](../rk3588_test_notes/优势场景测试-2026-08-13/flush-pagecache.sh) 的匿名内存挤压法（分配 7GB 匿名内存，把 buff/cache 从 6.2GB 压到 1.4GB）。局限如实记录：压不到零，所以单次采样有波动——这正是 Q8 的根因。

**关键点**：主动暴露「冲刷不彻底」这个局限，比假装干净更可信。RSS 补测里还记录了「R3 首测因页缓存残留导致限额未触发」的翻车案例，说明我们实测验证过冲刷的必要性。

---

### Q10【中概率】「同合同」怎么定义的？哪些能比哪些不能比？

**应答**：同合同 = 同设备 + 同模型 + 同缓存状态 + 同资源限制 + 同 workload（pp/tg）+ 相邻构建。只在这个范围内算提升率。不能比的例子：F 系列（4 线程）vs R 系列（8 线程）、cold vs warm、Q4_K_M vs IQ4_XS、cgroup peak vs 进程 RSS、不同内存档位之间（F1 vs F4）。

**证据**：规则见 [`docs/results/README.md`](../results/README.md) §1.2 统一口径。

---

## 三、机制正确性类（追问「为什么这样设计」）

### Q11【高概率】为什么 3GiB 受限时 SLIM-ARC 优势才显现？

**应答**：核心是「baseline 的 readahead 在高压下被打穿」。hit_rate 与内存压力无关（37.36% 恒定），变的是 baseline 处境：3GiB 下 baseline 顺序 readahead 预读的未来页挤掉当前页 → 缺页抖动 → tg 0.70；SLIM-ARC 精准预取「即将用」的专家页 → tg 2.21。详见复现文档 §1。

---

### Q12【中概率】MADV_RANDOM 为什么 WSL 正优化、RK3588 负优化？

**应答**：单趟固定开销 × 队列深度 × 工作集 churn 三者决定。x86+NVMe 固定开销低、可堆 QD，随机按需分页「付得起」，省 98% 无用预读是净赚；RK3588 是 45GB/8GB 极端 churn，SoC 内 DMA/SMMU 路径长、弱核处理 fault 慢，顺序大块读才能摊薄固定开销。**机制没有好坏，只有与硬件场景的匹配。**

**证据**：[`RK3588-NVMe随机4K读瓶颈与动态MADV机制分析-2026-08-14.md`](../rk3588_test_notes/RK3588-NVMe随机4K读瓶颈与动态MADV机制分析-2026-08-14.md) §7 答辩口径。

---

### Q13【中概率】解码瓶颈到底是什么？为什么预取没收益？

**应答**：解码**非 SSD I/O 受限**。vmstat 实测解码期 SSD 读仅 500-560MB/s（容量 1/4）、CPU 空闲 40-45%、wa 9-13%、t8 比 t4 更慢 → 是计算吞吐/并行度/内存带宽共同受限。I/O 预取类机制存在物理上限。

**证据**：[`80b专家预取消融-2026-08-08/vmstat-decode-on.txt`](../rk3588_test_notes/80b专家预取消融-2026-08-08/vmstat-decode-on.txt) + 改进记录阶段 8。

---

### Q14【中概率】expert prefetch 命中率 37% 是不是太低？

**应答**：单独看命中率没意义。① 37% 已经是随机基线 2% 的 17.5×（temporal 预测器）；② 置信度门控后升到 55%、下发 -56%；③ 关键不是「命中多少」，而是「是否比 baseline 的整层 readahead 少浪费 I/O」——在 3GiB 高压下，37% 命中的精准预取就足以把 tg 从 0.70 拉到 2.21。A22 的 88.56% 高命中率在 Mac 上反而没提速，证明「命中率 ≠ 端到端收益」。

---

## 四、工程与边界类（追问「有没有漏洞/局限」）

### Q15【中概率】baseline 和 patched 怎么保证加载各自的动态库，不串？

**应答**：决赛报告 §4.8 有明确的「baseline 必须不输出 `[SLIM-ARC-METRICS]` 行」的校验。RK3588 上 F1（baseline）无该行、F2/F3/F5（patched）有该行，从 raw 日志可直接证明未串库。

**佐证**：Mac 侧曾出过 baseline-first `LD_LIBRARY_PATH` 串库事故（[`ROADMAP.md`](../../ROADMAP.md) 2026-08-11 条目），已用真实镜像 `ldd` gate 修复——这个教训我们在 RK3588 也沿用「指标行必须出现/消失」作为硬校验。

---

### Q16【中概率】进程 VmHWM 比 cgroup memory.current 大，数据矛盾吗？

**应答**：不矛盾。3GiB 场景 VmRSS（4321MB）> scope memory.current（3072MB），差额约 1.2GB 是模型文件 page cache 页计费在外部 session cgroup（cgroup v2 按首次缺页的 cgroup 计费）。所以「cgroup 口径」和「进程 RSS 口径」不能直接相减。

**证据**：[`优势场景测试-2026-08-13/RK3588-SLIMARC-RSS内存峰值补测-2026-08-13.md`](../rk3588_test_notes/优势场景测试-2026-08-13/RK3588-SLIMARC-RSS内存峰值补测-2026-08-13.md) §4 分析。

---

### Q17【中概率】为什么没有 S 级场景（baseline OOM、SLIM-ARC 存活）？

**应答**：llama.cpp 默认 mmap 按需分页让 baseline 也不 OOM，压力通过 page cache 逐出消化，表现为性能劣化而非 OOM。诚实承认「没有 S 级，最佳是 F2/F3 的 A 级 3.16×」——这反而说明我们没有伪造「救活模型」的叙事，真正让 45GB 能跑的是 mmap，SLIM-ARC 是「受限环境下跑得更快」。

---

## 五、一句话总纲（任何追问都能兜底）

> **「我们做的是让页建议、专家预取、预算这些机制按阶段、按设备、按内存压力去适配的旋钮，不是全局银弹。RK3588 证明了两件事：静态 RANDOM 是负优化（动态 MADV 修复到 4-6×→持平）；内存压到 3GiB 后精准预取兑现 3.16×。每一步都有 raw 日志、复现命令和代码位置。」**
