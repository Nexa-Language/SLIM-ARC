# macOS 受限资源 80B 推理与决赛优化设计

## 1. 背景

SLIM-ARC 需要在 macOS 开发机上补充一组可复现的受限资源实验，目标是在尽可能低的物理内存和受限 CPU 核数下运行 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`，并从初赛未完成计划中选择能被实验数据支持的方向继续优化。

macOS 原生没有 Linux cgroups。`ulimit -v` 限制的是虚拟地址空间，会阻止映射约 48.4 GB 的 GGUF，不能模拟“模型保持 mmap、物理页按需驻留”的场景；主动制造全机内存压力又会影响其他应用。因此正式受限资源实验在专用 Linux VM 中完成，macOS 原生只作为不具备严格物理内存上限的补充性能基线。

## 2. 目标与非目标

### 2.1 目标

1. 在 Apple Silicon Mac 上建立 cgroups v2 隔离的 ARM64 Linux 测试环境。
2. 固定模型、llama.cpp commit、构建配置和输入，测出 80B Q4_K_M 的最低无 swap 可生存内存与最低稳定内存。
3. 在最低稳定内存下得到 `pp64 + tg16`、CPU 缩放和关键功能消融结果。
4. 基于 cgroup、缺页和 I/O 数据，验证并实现初赛遗留的内存压力感知调度与错误专家页回收。
5. 保持当前展示路径可用；所有新优化均可关闭、可消融、可回退。

### 2.2 非目标

1. 不将 Linux VM CPU 结果解释为 macOS Metal 性能。
2. 不使用 `memory_pressure` 或其他方式挤压 macOS 主机内存。
3. 不在本阶段深度改造 KV cache allocation/access，也不实现 Tile/dequantization pipeline。
4. 不把使用 swap 才能完成的档位记为无 swap 内存成绩。
5. 不追求只优化单一吞吐指标而牺牲可演示性、正确性或稳定性。

## 3. 固定实验对象

- 模型：Qwen 官方仓库 `Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF` 中的 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`，页面标注大小约 48.4 GB。
- llama.cpp：固定 commit `360e134`，与当前 RK3588/haoma 补丁验证基线一致。
- baseline：未应用 SLIM-ARC patch 的同一 llama.cpp commit。
- patched：通过仓库 `scripts/apply-slim-arc.py` 应用当前 SLIM-ARC patch。
- 架构：Linux ARM64、CPU-only。baseline 与 patched 使用相同编译器、CMake 参数、线程数和模型文件。
- 模型来源、最终字节数与 SHA-256 必须在下载后写入实验清单；下载支持断点续传。

若 patch 无法干净应用到固定 commit，先记录并修复兼容问题，不切换到未经验证的 llama.cpp 当前 master。

## 4. 隔离架构

### 4.1 主机与虚拟机

通过 Homebrew 安装 Colima 与 Docker CLI，创建专用 ARM64 Linux VM：

- VM RAM：16 GB；
- VM vCPU：8；
- VM 磁盘：100 GB 稀疏磁盘；
- 正式测试容器：cgroups v2；
- 模型和 llama.cpp 构建目录：VM 本地 ext4 文件系统。

模型不通过 macOS bind mount 读取。这样首次触碰的模型文件页会进入 guest page cache，并由测试 cgroup 计费，避免共享挂载和跨 cgroup page cache 归属模糊测试口径。

### 4.2 资源限制

正式容器同时使用：

- `memory.max`：当前内存档位；
- `memory.swap.max=0`：正式无 swap 结果；
- CPU quota：当前 CPU 档位；
- llama `-t` 与 `-tb`：与 CPU quota 一致；
- 每个推理进程的硬超时；
- 容器 OOM 事件与退出码采集。

每个冷启动档位开始前，只在专用 VM 内执行 page cache 清理。macOS 主机缓存和系统内存策略不变。一个档位的多次 warm run 保持在同一测试 cgroup 中，使缓存和内存计费关系可解释。

## 5. 测试矩阵

### 5.1 Stage A：正确性与生存阶梯

固定 4 vCPU、`-t 4`、`-tb 4`，运行最小 `pp4 + tg1`：

1. 依次测试 12、8、6、4 GB。
2. 若 4 GB 连续成功两次，继续测试 3、2 GB。
3. 若 4 GB 连续失败两次，补测 5 GB 以定位边界。
4. 单次硬超时为 30 分钟。

“可生存”要求同一档位无 swap 连续成功两次，输出非空且未发生 cgroup OOM。连续两次 OOM、崩溃、非法输出或超时即判定该档失败，并停止继续向更低档位搜索。

### 5.2 Stage B：最低稳定内存

从最低可生存档开始运行 `pp64 + tg16`，单次硬超时为 90 分钟。失败则回退到上一档，直到得到最低稳定档。

最低稳定档至少完成：

1. 一次冷启动；
2. 一次 warm run；
3. baseline 与当前完整 SLIM-ARC 的同条件 A/B；
4. 时间允许时再补第二次 warm run 和关键开关消融。

### 5.3 Stage C：CPU 缩放

固定最低稳定内存，依次测试 2、4、6、8 vCPU。每档的 `-t`、`-tb` 与 CPU quota 一致，得到独立的核数—性能曲线。内存阶梯不同时改变 CPU，以避免混杂变量。

### 5.4 Stage D：受控 swap 探索

只有无 swap 的 4 GB 或更低档位失败后才执行。设置有限的 2–4 GB swap 上限并单独成表，必须同时报告：

- `memory.peak`；
- swap 峰值；
- wall time 与 tok/s；
- OOM/timeout；
- 与最低无 swap 稳定档的差异。

该结果不进入“最低无 swap 内存”结论。

## 6. 消融配置

第一轮不修改代码，先使用现有开关比较：

1. 同 commit upstream baseline；
2. 当前 SLIM-ARC 默认配置；
3. no-prefetch；
4. decode `SEQUENTIAL` / `NORMAL` / `RANDOM`；
5. expert confidence gating；
6. expert budget admission control；
7. 时间允许时的组合最优配置。

实际命令以固定 llama.cpp commit 的 `--help` 和仓库现有环境变量为准，运行器需把完整 argv、环境变量、二进制 hash 和 patch 状态写入 manifest。

## 7. 指标与结果格式

每次运行记录：

- 结果：成功、OOM、timeout、signal、非零退出码；
- 正确性：输入、非空输出、token 数；
- 性能：模型加载时间、TTFT、prefill tok/s、decode tok/s、wall time；
- 内存：`memory.current`、`memory.peak`、`memory.events`、`memory.stat`；
- VM：major/minor faults、page cache、swap、PSI；
- I/O：cgroup `io.stat`、进程读字节；
- CPU：usage、throttling、quota、线程数；
- 可复现信息：主仓 commit、llama.cpp commit、模型 SHA-256、构建参数、测试配置、时间戳。

原始日志不可只保留终端摘要。每次运行生成机器可读 manifest 与原始 stdout/stderr，最终报告从这些数据生成，避免手工抄录错误。

## 8. 决赛优化设计

### 8.1 P0：现有配置消融

先确定 MADV 和现有 expert prefetch 控制在当前 Linux ARM64 + NVMe 环境中的真实效果。RK3588 日志显示专家预取命中率约 19%–55%，存在数十 GB 的预取浪费，但不能直接推断 Apple Silicon VM 中的最佳策略。

没有 profile 或 cgroup 指标支持时，不修改核心调度代码。

### 8.2 P1：内存压力感知 admission control

当前 `unified_io_scheduler` 会计算并下发 `weight_bytes`，但普通 layer-ahead prefetch 的 `worker_loop()` 没有消费 `memory_budget_`；expert budget 也只在显式开关打开时生效。P1 补齐这个闭环：

1. Linux 下读取当前 cgroup 的 `memory.current` 和 `memory.max`；
2. 预留安全 headroom 后计算本轮有效 prefetch budget；
3. 普通权重和 expert prefetch 都必须遵守预算；
4. 内存压力高时缩小窗口或跳过预取，计算路径继续按需缺页；
5. 非 cgroups 平台或读取失败时回退当前行为；
6. 新策略先由环境变量启用，不改变其他平台默认值；
7. 记录 requested、issued、skipped、pressure-throttled bytes 和采样次数。

实现必须处理并发读写、整数溢出、`memory.max=max`、cgroup 文件短读/解析失败与测试容器嵌套路径，不得静默把解析错误解释为零预算。

### 8.3 P2：错误 expert 预取页回收

不立即驱逐全部已激活专家。利用现有 `last_prefetched_experts_` 与下一次真实 router 结果计算：

`wasted = prefetched - actually_selected`

仅对 wasted expert tensor 范围内完整覆盖的 page-aligned 区间发出 `DONTNEED`，避免误伤相邻活跃 expert 的共享页。实现要求：

1. 独立环境变量控制；
2. 地址范围和长度溢出检查；
3. 与 prefetch worker 的并发关系明确；
4. 记录 reclaimed bytes、调用次数、失败数；
5. 对 repeated expert 的缺页与延迟做 A/B；
6. 默认关闭，达到晋级门槛后才进入推荐配置。

### 8.4 后置方向

- 深度 KV offload：当前接口与真实 KV allocation/access hook 尚未完成；短上下文 `pp64 + tg16` 不足以证明其价值，后续用长上下文独立设计。
- Tile/dequantization pipeline：仅有设计稿且侵入计算内核；只有 profile 证明 compute/dequant 而非 page fault/I/O 为瓶颈时启动。
- Speculative decoding：已有低接受率和明显负收益记录，本轮不优先。

## 9. 优化晋级与回退规则

新优化至少满足以下一项：

1. 解锁更低的无 swap 稳定内存档；或
2. 同档位 `memory.peak` 下降至少 10%，且 `pp64 + tg16` 总耗时退化不超过 15%。

同时必须满足：

- 输出正确性与 baseline 一致；
- 无新增崩溃、死锁、数据竞争或不可控后台线程；
- 开关关闭时行为回到当前主线；
- 有单元或集成测试覆盖预算计算、cgroup 解析、边界地址和失败回退；
- A/B 使用同模型、同 commit、同冷/热口径。

不满足门槛的实现保持默认关闭；如果只增加复杂度且没有可复现收益，则从主线改动中移除，只在实验记录中保留负结果。

## 10. 12 小时执行与停止条件

执行优先级：环境校验与断点下载 → 固定 commit 双构建 → 生存阶梯 → 最低稳定档完整测试 → 消融 → P1/P2 实现与复测。

为避免下载或构建吞掉全部时间：

- 下载可恢复，完成后校验；
- 每个阶段写 checkpoint；
- 到 12 小时截止点不再启动新实验；
- 优先保留“当前代码最低内存 + 一个完整 `pp64 + tg16`”结果；
- 自动终止仍在运行的测试子进程，保留现有 VM、模型、构建缓存和日志以便续跑；
- 主机剩余磁盘进入安全阈值时停止下载或构建，不自动删除用户文件。

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 48.4 GB 模型下载超时或中断 | 12 小时内无完整结果 | 断点续传、校验、阶段 checkpoint |
| VM 文件缓存计费口径错误 | 低内存结论失真 | 模型放 VM ext4、冷启动清 guest cache、采集 cgroup memory.stat |
| ARM VM 无 Metal | 吞吐低于 macOS 原生 | 明确结果是 Linux CPU 系统实验，另补原生性能基线 |
| cgroup OOM | 单档失败 | 容器级隔离、连续两次判定、向上回退 |
| prefetch 限流降低吞吐 | 优化负收益 | 15% 门槛、完整 A/B、默认可关闭 |
| DONTNEED 造成反复缺页 | decode 抖动 | 只回收错误预取页、记录 faults、默认关闭 |
| 上游 patch 漂移 | 构建不可复现 | 固定 `360e134`，不静默切 master |
| 磁盘占用过高 | 影响主机 | 100 GB 稀疏上限、执行前后检查余量、不自动删除用户数据 |

## 12. 验收标准

本阶段完成需同时满足：

1. 可重复创建或恢复专用 VM，并确认 cgroups v2 生效；
2. 模型 hash、llama.cpp commit、构建参数均有记录；
3. 至少得到当前代码的最低无 swap 可生存档与最低稳定档；
4. 至少在稳定档完成一次 `pp64 + tg16`；
5. 得到 baseline 与当前 SLIM-ARC 的同条件结果；
6. 有完整原始日志、机器可读 manifest 和总结表；
7. P1/P2 只有在前置数据支持时实施，并按晋级规则决定是否启用；
8. macOS 主机未被全局内存压力测试影响，测试退出后无遗留推理进程。
