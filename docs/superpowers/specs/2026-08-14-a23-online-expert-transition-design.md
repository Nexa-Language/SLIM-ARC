# A23 在线跨层 Expert 转移预取设计

## 1. 背景与实验结论

A22 在当前层额外执行下一层 Router matmul，并以其 TopK 结果对下一层 expert 页发出
`WILLNEED`。Mac 2 GiB/no-swap 的 Top2 两次中位数相对同镜像 control 有收益，但仍慢于
历史 A20；Raspberry Pi 5 4GB/no-swap 的 Top10 三次中位数相对 control 为
`prefill -0.84%`、`decode -0.57%`、`wall +0.30%`。A22 将 Pi expert byte hit rate 提高到
`82.74%`，却没有转化为端到端吞吐，说明额外 Router 计算和预取读放大抵消了命中收益。

A23 的核心假设是：相邻层原生 Router 输出之间存在可在线学习的稳定相关性。系统只观察
已经必须执行的 Router，不再构建任何额外 Router tensor，通过小型有界转移表预测下一层
候选，从而把慢盘 I/O 尽早移出关键路径。

## 2. 目标与非目标

### 2.1 目标

1. 下一层预测不增加 ggml 节点、Router matmul 或模型权重读取。
2. 不训练、不生成校准文件，不复制 48 GB 模型；运行时状态控制在 1 MiB 量级。
3. 原生 Router 始终是执行语义的唯一权威；预测只影响 `WILLNEED`。
4. 预测、更新和衰减均为确定性、有界操作，适合慢盘开发板。
5. 用同合同 Mac 与 Raspberry Pi 冷缓存实验判断端到端收益，而不是仅看命中率。

### 2.2 非目标

1. A23 不替代 A20、A22，也不改变模型输出或 expert 选择。
2. 第一版不持久化转移表，不跨进程复用学习结果。
3. 第一版只在 `n_tokens == 1` 的 decode graph 中学习和预测；不把批量 prefill 的 expert
   并集错误解释为逐 token 转移。
4. 第一版不实现训练式低秩 predictor、残差校准、LRU-K/ARC 或显式异步 `pread`。

## 3. 外部接口与开关

新增两个严格 opt-in 环境变量：

- `SLIM_ARC_CROSS_LAYER_TRANSITION=1`：启用 A23；其他值均关闭。
- `SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK=N`：预测并预取分数最高的 `N` 个下一层 expert，
  合法范围为 `1..64` 且不得超过模型 expert 数。

A23 与 A22 的 `SLIM_ARC_CROSS_LAYER_GATE=1` 互斥。两者同时出现时 A23 优先，A22 的额外
Router graph 节点不构建，并输出一次非机器可解析的诊断提示。所有新开关默认关闭，旧路径
保持字节级行为不变。

首轮测试点固定为：

- Mac：A23 Top2、Top4，对照 A20 最佳配置和同镜像 transition-off control；
- Raspberry Pi：A23 Top2、Top4、Top8，对照同镜像 transition-off control；
- 所有 Pi 正式筛选均冷缓存、4 threads、`pp16/tg4`、运行期 no-swap，结束后恢复 zram。

## 4. 状态模型

### 4.1 有界转移行

每个 `(source_layer, source_expert)` 保存最多四个 `target_expert` 槽位。每个槽位包含：

- `uint16_t target_expert`；
- `uint16_t count`。

无效槽使用保留 ID 表示。Qwen3-Next 的 expert ID 远小于 `uint16_t` 上限；若其他模型的
expert 数超过上限，A23 对该模型自动关闭。每层使用一个 dense `vector<transition_row>`，不为
每个 expert 创建独立容器；状态按实际注册的层和 expert 数懒分配。以 48 层、512 expert
估算，槽位正文约 384 KiB，加上每层容器和计数元数据仍控制在 1 MiB 量级。

### 4.2 更新规则

收到相邻层同一 decode graph 的真实选择 `source_ids` 和 `target_ids` 后，对二者笛卡尔积
更新对应转移行：

1. 已存在目标：计数饱和加一；
2. 存在空槽：按目标 ID 升序插入；
3. 行已满：替换计数最小的槽，平局时替换目标 ID 最大者，新计数设为被替换计数加一；
4. 输入中的负数、越界 ID 和重复 ID 在更新前过滤。

每个 source layer 独立记录有效观察数；该层每完成 64 次相邻层 decode 观察，就将该层所有
非零计数右移一位，最低保留为一，避免早期流量永久主导。衰减只遍历该层已分配行，不能按
全模型 update 次数触发，否则多层模型会过度衰减。

### 4.3 预测规则

对当前层真实 `source_ids`：

1. 汇总每个 source 行中目标的计数，使用饱和 `uint32_t` 分数；
2. 目标按分数降序、expert ID 升序稳定排序；
3. 返回前 `transition_topk` 个唯一目标；
4. 没有历史时返回空，不使用未经验证的同 ID fallback。

固定平局规则保证测试、Mac 和开发板上的候选顺序一致。

## 5. Decode graph 数据流

每次 `graph_compute` 创建 graph-local Router 状态，保存本 graph 已观察到的逐层真实 expert
集合；跨 graph 的转移表由 model-owned `prefetch_scheduler` 持有。

处理第 `L` 层原生 Router 回调时顺序固定：

1. 用真实选择结算此前对第 `L` 层的预取 generation；
2. 若 graph-local 中存在第 `L-1` 层真实选择，调用
   `observe_transition(L-1, source_ids, target_ids)`；
3. 调用 `predict_transition(L, target_ids, topk)` 得到第 `L+1` 层候选；
4. 通过现有 `prefetch_experts(L+1, ...)` 发出有预算的页预取并保存 generation；
5. 将当前真实选择保存到 graph-local 状态，供下一层更新。

graph-local 状态同时保存每层实际发出的预测集合。下一层原生 Router 返回时，在结算
generation 的同时把预测集合与真实集合交给
`record_expert_transition_result(predicted, actual)`，
更新 `matched_experts`，不依赖 page advice 是否成功。

首个 decode graph 只建立转移表，预测为空；第二个 decode graph 起才可能预取。graph 失败或
某层 Router 回调缺失时，沿用现有 generation cancel 路径，不能让待结算记录泄漏。

锁只保护转移表的短时更新和快照。排序、`madvise` 和 I/O advice 均在锁外执行，避免把慢盘
等待放大为调度串行化。

## 6. 模块与改动范围

新增纯逻辑模块：

- `patches/llama-upstream/slim-arc-expert-transition.h`
- `patches/llama-upstream/slim-arc-expert-transition.cpp`
- `tests/cpp/test-slim-arc-expert-transition.cpp`

集成改动限定为：

- `slim-arc-prefetch.{h,cpp}`：持有转移表、开关、统计和线程安全 API；
- `scripts/apply-slim-arc.py`：复制/CMake 接线，并在原生 Router 回调接入数据流；
- `tests/run-cpp-unit.sh`：注册一个纯逻辑测试目标；
- patcher fixture：断言 A23 不生成 A22 的额外 Router tensor，且二次 apply 幂等。

不修改模型文件格式、GGUF、KV cache、权重布局或现有运行时指标 schema。

## 7. 可观测性

新增独立文本行，避免破坏现有 `[SLIM-ARC-RUNTIME] schema=3` 解析器：

```text
[SLIM-ARC-TRANSITION] schema=1 updates=... prediction_rounds=...
empty_rounds=... predicted_experts=... matched_experts=... decays=...
```

`matched_experts` 在下一层真实 Router 返回时按唯一 expert ID 交集计算。端到端实验同时记录：

- pp/tg TPS 与 wall time；
- expert issued/hit/waste bytes；
- major faults 与 filesystem input blocks；
- 运行期 swap、温度、退出码和 zram 恢复状态。

## 8. 最小验证与实验淘汰标准

只保留以下实现门禁：

1. 纯逻辑 C++ 测试：冷启动空预测、学习后命中、四槽替换、确定性平局、64 graph 衰减、
   非法/重复 ID；
2. patcher fixture：A23/A22 互斥、回调顺序和二次 apply；
3. 应用到固定 llama.cpp `360e134` 后完成目标二进制编译；
4. Mac 一个短 smoke 后直接进入 2 GiB/no-swap 冷缓存筛选；
5. 只有 Mac 无明显退化才部署到 Pi 做 Top2/4/8 串行筛选。

保留 A23 的必要条件：

- Raspberry Pi 至少两个重复中，decode TPS 中位数高于同镜像 control，且 wall time不退化；
- expert hit 提升不能伴随明显 filesystem input 或 waste bytes 放大；
- 无 advice failure、进程失败、swap 使用或 zram 恢复失败。

若 A23 未达到条件，默认关闭并保留研究证据，下一步转向显式顺序 expert pack + 异步
`pread`/双缓冲，而不是继续扩大预测 TopK。

## 9. 风险与回退

- 跨层关联可能随 prompt 快速变化：通过 64 graph 衰减和固定小 TopK 控制污染。
- 四槽 heavy-hitter 可能损失长尾：先用 Top2/4/8 观察 recall，再决定是否扩大槽位；不预设扩容。
- 第一 decode graph 无跨层预取：这是避免未经学习读放大的明确取舍，A20 仍作为性能基准。
- 多 context 共享 model runtime 时样本会混合：第一版允许共享统计，但表更新受独立 mutex 保护；
  比赛正式 benchmark 为单 context。
- 任一结果退化时只需关闭 `SLIM_ARC_CROSS_LAYER_TRANSITION`，不会改变 A20/A22 行为。
