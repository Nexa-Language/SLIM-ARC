# SLIM-ARC 慢存储 I/O 重构设计

日期：2026-08-13

状态：已确认，进入实现

目标平台：低内存、低带宽嵌入式设备，以及可复现同类约束的 Mac/Colima 环境

## 1. 目标

在不牺牲正确性、可复现性和现有无限制设备兼容性的前提下，降低
Qwen3-Next-80B-A3B 在 2--8 GiB 物理内存和慢存储条件下的冷启动、
page-in/page-out 放大与 token 延迟。实现顺序固定为：

1. A0：修复页范围与 advice 正确性；
2. A1：把预取改为有界、合并、可取消的 I/O 调度；
3. A2：依据吞吐、缺页和压力反馈调整访问策略；
4. B：在 A 路径仍受限时引入显式 expert resident slots；
5. C：只有证据证明 page cache 路径到达上限后，才评估重排文件与
   `io_uring`/`O_DIRECT`。

最终报告和 PPT 不在本阶段更新；按约定于 2026-08-17 只引用通过晋级门禁的
结构化实验结果。

## 2. 已验证的问题

### 2.1 当前瓶颈

在 ARM64 Colima、cgroup v2、2 GiB、4 CPU、swap=0、200 MiB/s 冷缓存条件下，
80A3B 单 token 需要约 55--58 GiB 块设备读取，耗时约 265--276 秒。当前 patched
路径的主要有效增益来自整映射 `POSIX_MADV_SEQUENTIAL`；细粒度普通预取和
expert 预取没有形成可观测的有效 page-in。

这些数据用于定位，不作为最终性能晋级结论：目前只有单次诊断运行，且生成
长度较短。

### 2.2 根因

GGUF tensor 仅保证 32-byte 对齐，而 Linux `posix_madvise` 要求地址按页对齐。
当前两条 `WILLNEED` 路径直接使用 tensor 或 expert slice 的原始地址：

- 普通 worker：`advice_(tensor.addr, tensor.size, POSIX_MADV_WILLNEED)`；
- expert worker：`tensor_addr + expert_id * per_expert_size`。

80A3B 的 144 个三维 expert tensor 基地址普遍不是 4096-byte 对齐。实测同一映射
的页对齐地址返回 0，而 `addr + 32` 返回 `EINVAL`。因此现有 expert 指标长期为
`issued=0`，不是“路由器没有命中”，而是 advice 请求本身无效。

### 2.3 调度放大

图执行 hook 会遍历后续大量 layer 并逐一入队；worker 队列虽有限长，但缺少：

- 同一页范围合并和去重；
- graph/token generation 与 stale cancellation；
- 每轮累计 byte budget 和全局 in-flight budget；
- 普通权重与 expert I/O 的优先级隔离；
- 面向慢存储的低 queue-depth 控制。

这会把“预测多一些”转化为随机 IOPS、重大缺页和读放大，而非有效重叠。

## 3. 系统不变量

1. `WILLNEED` 使用向外覆盖完整目标字节的页范围；`DONTNEED` 只使用向内完整页，
   两者不得复用同一取整语义。
2. 所有地址加法、长度加法和页取整都必须检查溢出。
3. 同一 generation 内重叠或相邻页只能提交一次 advice。
4. 任何 generation 的 requested/issued/in-flight bytes 不得超过配置预算。
5. 新 generation 到达后，尚未提交的旧请求必须取消；已提交请求只记账，不伪装
   为可撤销 I/O。
6. 不在 scheduler 状态锁内调用 `posix_madvise`、`pread` 或压力读取。
7. 默认路径在 feature flag 关闭时保持现有顺序和结果。
8. 失败 advice 必须显式计数；只有返回 0 的范围才能计入 issued bytes。
9. 没有通过 correctness、构建、重复实验门禁的优化不得写入最终性能结论。

## 4. A0：页范围正确性

在 `slim-arc-page-range` 中保留现有 `interior_page_range`，新增
`covering_page_range`：

- `start = floor(addr / page_size) * page_size`；
- `end = ceil((addr + size) / page_size) * page_size`；
- `addr + size`、向上取整和 `end - start` 全部溢出安全；
- `size == 0` 返回空范围；
- 非 2 的幂、零 page size 和地址溢出返回 invalid。

普通和 expert `WILLNEED` 均先转换成 covering ranges，再排序并合并 overlap/
adjacent ranges。`DONTNEED` 继续使用 interior ranges，以免回收仍包含有效数据的
边缘页。

新增指标：

- `advice_requests` / `advice_failures`；
- `requested_bytes` / `covered_bytes` / `issued_bytes`；
- `coalesced_ranges`；
- 按 `EINVAL`、其他 errno 分桶的失败计数。

## 5. A1：有界 I/O 调度器

### 5.1 请求模型

引入值类型 `prefetch_request`：

- `generation`、`layer`、`kind`（weight/expert）；
- 页对齐后的 `[addr, length]`；
- `priority`、`deadline_layer`；
- 可选 expert identity，仅用于统计，不作为裸指针生命周期依据。

graph hook 每次发布新的 generation。scheduler 在锁内完成 snapshot、合并、预算
准入和队列替换，锁外执行 advice。

### 5.2 窗口和预算

第一版固定、可测的慢存储默认值：

- lookahead window：1 layer；
- worker：1；
- chunk：4 MiB；
- 每 generation 总预算：取 runtime effective budget 的有界比例；
- expert 预算独立于普通 weight 预算；
- queue latest-wins，旧 generation 未提交项计为 stale。

后续实验只在 `{1,2,3}` layer、`{2,4,8}` MiB chunk、`{1,2}` worker 的小矩阵
内选择，不做无界参数搜索。

### 5.3 调度次序

1. 当前层完成后，仅生成下一窗口需要的候选；
2. 先过滤已 resident/已提交页；
3. expert 依据稳定集合、时序集合、热度和压力策略排序；
4. 统一转换页范围并 coalesce；
5. 按 weight/expert 双预算准入；
6. 分 chunk 低 queue-depth 提交；
7. 新 generation 到达时取消未执行旧项。

新增指标：`requested`、`coalesced`、`admitted`、`issued`、`failed`、`stale`、
`throttled`、`inflight_peak`，并区分 weight/expert。

## 6. A2：反馈控制

只在 A0/A1 correctness 和固定参数基线稳定后启用。每次 tick 读取一次并形成不可变
snapshot：

- cgroup memory current/max 与 pressure state；
- 最近窗口 major faults；
- 块设备 read bytes/read IOPS；
- 实测 advice 到消费之间的 overlap；
- router prediction hit/waste。

控制器使用滞回，不根据单个抖动样本切换：

- I/O 来不及且读放大上升：缩短 window、减少 expert budget；
- overlap 有余量且 fault stall 上升：有限扩大 window；
- critical pressure：停止新 expert advice，仅保留稳定 resident set；
- 连续恢复样本后逐级恢复，不直接跳回最大配置。

全文件访问 hint 只在 phase 边界改变，避免 SEQUENTIAL/RANDOM 高频互相覆盖。

## 7. B：显式 expert resident slots

若 A 路径在慢盘仍被随机 page fault 主导，则引入受预算约束的 resident slot，按
`(layer group, expert id, tensor role)` 标识。策略遵循调研中的两级拆分：

- always-on/shared 权重与 routed experts 分开；
- stable/hot experts 优先常驻；
- temporal candidates 使用 TinyLFU/SIEVE 风格准入，避免一次性热点污染；
- 同一 miss 合并，异步 `pread` 到双缓冲；
- prefill 可做 batch-union，decode 保持小窗口；
- miss 时回退现有 mmap 路径，保证正确性。

2 GiB 档先限制为 1--2 个 layer group，不预设能够缓存完整模型或大量 experts。

## 8. C：实验性直接 I/O

仅当以下证据同时成立时进入：

1. A0--B 已验证且 page cache reclaim/随机 fault 仍是主瓶颈；
2. 模型文件可以离线生成顺序 packed layout；
3. `io_uring` 或 platform-specific async I/O 在目标板可用；
4. 对齐缓冲、checksum、fallback 和文件版本兼容可验证。

`O_DIRECT`/`io_uring` 不作为默认跨平台依赖；macOS 和不支持设备继续使用 mmap/
pread fallback。

## 9. 实验设计与晋级门禁

### 9.1 本地慢存储矩阵

固定 80A3B、2 GiB、4 CPU、swap=0、pp64/tg16，并使用 cgroup v2 `io.max` 模拟
8/20/50/200 MiB/s。每个候选先做小型诊断，再做 cold 2 次、warm 3 次交错运行。

### 9.2 远端设备

Tailscale 设备 `100.66.244.55` 仅在身份、架构、内存、存储、cgroup、模型 hash 和
可用磁盘空间预检通过后运行。先跑无权重 smoke/小模型，再跑 80A3B；任何可能造成
OOM 或磁盘耗尽的步骤均先停止并报告。

### 9.3 晋级条件

- correctness、构建、链接和 runtime metrics gate 全绿；
- 无 OOM、无 swap；
- cold median wall time 改善；
- read bytes 不增加；
- major faults 与 read IOPS 不得同时显著恶化；
- tg16 不退化；
- 8/20 MiB/s 下无明显 I/O 放大；
- 无限制或高速设备无明显回归。

未达到条件的策略保留为 opt-in 或记录为负结果，不进入默认配置。

## 10. 验收标准

1. 未对齐普通/expert tensor 的 `WILLNEED` 单测可稳定复现旧 `EINVAL`，修复后返回 0；
2. covering/interior range 的边界、溢出、零长度和页边缘测试全部通过；
3. 同一 generation 的重叠范围只产生一次 advice；
4. stale generation、预算和 in-flight 上界有确定性单测；
5. patcher 二次应用 byte-identical；
6. pinned llama.cpp 能构建且 variant linkage 正确；
7. 本地和远端结构化 manifest 包含相同 identity、I/O、fault、TPS 与策略指标；
8. 只有通过晋级门禁的结果进入 8 月 17 日的报告和 PPT。

## 11. 风险

- covering range 会额外触及 tensor 两侧同页数据；这是 `WILLNEED` 正确性的必要
  页粒度放大，需通过 coalescing 和 byte 指标量化。
- `posix_madvise(WILLNEED)` 是 hint，不保证异步完成；A1 仍需通过真实 I/O 指标
  判断是否产生有效重叠。
- Colima 的虚拟块设备与真实 eMMC/NVMe 不完全等价；最终结论必须由目标设备复核。
- 显式 resident slots 增加内存复制与生命周期复杂度，只有 A 路径不足时才实现。
- Tailscale 远端可能不在当前 tailnet、离线或资源不满足；连接失败不能用猜测数据
  替代真实实验。
