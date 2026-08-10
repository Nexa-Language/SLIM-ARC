# SLIM-ARC 监视 UI Bug 分析与修改建议报告

- **日期**: 2026-08-10
- **范围**: scripts/demo/ 下 Web 演示系统的两个 UI Bug 分析与修改建议
- **性质**: 纯分析与规划，**未修改任何代码**
- **分析人**: Architect 模式自动分析

---

## 1. red-line 声明

本报告严格遵守项目 `.roo/rules/red-line.md` 的全部 6 条约束：

| # | 规则 | 本报告遵守情况 |
|---|------|---------------|
| 1 | 只做 bug 修复，绝不修改核心代码/机制（不重构、不新增功能、不改变算法逻辑） | 本报告仅为分析与建议，未修改任何代码。建议的修改均为 demo UI 层面的 bug 修复，不触碰核心推理逻辑 |
| 2 | 所有代码改动标注 `// SLIM-ARC FIX <YYYY-MM-DD>: <原因>`，最小外科手术式 | 报告中每个建议修改点均标注建议的 SLIM-ARC FIX 格式 |
| 3 | patches/llama-upstream/ 与 src/llama-upstream/src/ 必须同步（scripts/apply-slim-arc.py 幂等同步）；demo 脚本不属于镜像范畴 | 本报告涉及的修改仅限 scripts/demo/*（index.html、monitor.py），不涉及 llama-upstream 镜像 |
| 4 | 全部测试记录/结果/日志输出到 docs/rk3588_test_notes/ | 本报告保存于 docs/rk3588_test_notes/demo-ui-analysis-2026-08-10/ |
| 5 | 无终端交互：所有命令非交互、自主决策 | 分析过程未涉及终端交互 |
| 6 | 每个失败都要留痕并分析根因 | 本报告即为两个 UI bug 的根因分析与留痕 |

**重要声明**: 本报告为分析+建议文档，未实施任何代码修改。报告中提到的"建议修改"供后续 Code 模式参考执行。

---

## 2. Bug 1 分析：对话窗口无法上下滚动

### 2.1 现象

左侧聊天窗口内容变多后，无法上下滚动查看历史消息。

### 2.2 相关代码位置

| 项目 | 文件 | 行号 | 内容 |
|------|------|------|------|
| body CSS | scripts/demo/index.html | 21-27 | `body { height: 100vh; overflow: hidden; }` |
| 主布局 CSS | scripts/demo/index.html | 56-62 | `.main { display: grid; height: calc(100vh - 56px); }` |
| 聊天区容器 CSS | scripts/demo/index.html | 64-67 | `.chat { display: flex; flex-direction: column; }` |
| **消息滚动容器 CSS** | scripts/demo/index.html | **73-75** | `.chat-messages { flex: 1; overflow-y: auto; padding: 24px; }` |
| 聊天消息 DOM | scripts/demo/index.html | 253 | `<div class="chat-messages" id="messages">` |
| 追加用户消息 JS | scripts/demo/index.html | 446-451 | `send()` 函数内 `messages.appendChild(userDiv)` |
| 追加 assistant 消息 JS | scripts/demo/index.html | 454-459 | `send()` 函数内 `messages.appendChild(asstDiv)` |
| 流式 token auto-scroll | scripts/demo/index.html | 509 | `messages.scrollTop = messages.scrollHeight;` |
| 发送时 auto-scroll | scripts/demo/index.html | 459 | `messages.scrollTop = messages.scrollHeight;` |

### 2.3 根因分析

**主因（致命）: CSS flexbox `min-height: auto` 默认值导致 `overflow-y: auto` 失效**

`.chat-messages`（行 73-75）是 `.chat`（flex column 容器，行 64-67）的子元素，设置了 `flex: 1; overflow-y: auto;`。

在 CSS Flexbox 规范中，flex 子项的默认 `min-height` 值为 `auto`，这意味着**子项不会缩小到低于其内容的固有最小高度**。当聊天消息累积导致 `.chat-messages` 内容高度超过 flex 分配的可用空间时：

1. `.chat-messages` 不会缩小——它增长以容纳全部内容
2. `overflow-y: auto` 无法生效——因为元素内部从未溢出（它跟着内容一起变高）
3. 增高后的 `.chat-messages` 将 `.chat-input` 推出视口底部
4. `body` 设置了 `overflow: hidden`（行 26），溢出内容被直接裁剪

**结果**: 用户看到的是消息不断向下"推"但无法滚动，输入框可能被推出可视区域。

**证据**:
- `.chat-messages` CSS（行 74）: `flex: 1; overflow-y: auto; padding: 24px;` — 缺少 `min-height: 0`
- `.chat` CSS（行 66）: `display: flex; flex-direction: column;` — flex column 布局
- `body` CSS（行 25-26）: `height: 100vh; overflow: hidden;` — body 不滚动，溢出裁剪

**次因: 流式输出时 auto-scroll 阻止回看**

`send()` 函数在每次收到流式 token 时执行 `messages.scrollTop = messages.scrollHeight;`（行 509），将滚动位置强制设为最底部。即使主因修复后滚动可用，在流式输出期间用户也无法向上滚动查看历史——每次 token 到达都会被拉回底部。

### 2.4 修改建议

#### 修改点 1（主因修复）: 为 `.chat-messages` 添加 `min-height: 0`

**文件**: scripts/demo/index.html
**位置**: 行 74，CSS 规则 `.chat-messages`
**当前代码**:
```css
.chat-messages {
    flex: 1; overflow-y: auto; padding: 24px;
}
```
**建议改为**:
```css
.chat-messages {
    flex: 1; overflow-y: auto; padding: 24px;
    min-height: 0; /* SLIM-ARC FIX 2026-08-10: flexbox 子项默认 min-height:auto 阻止 overflow-y 生效 */
}
```
**原理**: `min-height: 0` 覆盖 flexbox 默认的 `min-height: auto`，允许 `.chat-messages` 缩小到低于内容高度，从而激活 `overflow-y: auto` 的滚动条。

#### 修改点 2（次因改善）: 流式输出时仅在用户已处于底部时 auto-scroll

**文件**: scripts/demo/index.html
**位置**: 行 509，`send()` 函数内流式 token 处理
**当前代码**:
```javascript
messages.scrollTop = messages.scrollHeight;
```
**建议改为**:
```javascript
// SLIM-ARC FIX 2026-08-10: 仅当用户已在底部附近时才自动滚动，避免阻止回看历史
if (messages.scrollTop + messages.clientHeight >= messages.scrollHeight - 50) {
    messages.scrollTop = messages.scrollHeight;
}
```
**原理**: 检测用户是否已在滚动容器底部附近（50px 容差），仅在底部时才自动滚动，允许用户在流式输出期间向上滚动查看历史。

**注意**: 行 459 的 `messages.scrollTop = messages.scrollHeight;`（发送消息时）可保留不变——发送新消息时滚动到底部是合理的 UX 行为。

---

## 3. Bug 2 分析：MoE 预取可视化窗口形同虚设

### 3.1 现象

右侧监控面板中 "MoE 专家激活" 可视化没有实际效果，不展示真实数据。

### 3.2 相关代码位置

| 项目 | 文件 | 行号 | 内容 |
|------|------|------|------|
| MoE 可视化 DOM | scripts/demo/index.html | 293-299 | `<div class="experts" id="experts">` + `<span id="experts-active">` |
| 专家格初始化 JS | scripts/demo/index.html | 316-325 | `initExperts(total, active)` — 创建格子 |
| **专家激活更新 JS** | scripts/demo/index.html | **327-342** | `updateExperts(active, total)` — **使用 Math.random()** |
| 轮询消费 JS | scripts/demo/index.html | 420-422 | `pollMonitor()` 内调用 `updateExperts()` |
| 后端 monitor 接口 | scripts/demo/monitor.py | 155-175 | `/api/monitor` 返回 config + metrics |
| 后端 config 定义 | scripts/demo/monitor.py | 40-50 | `CONFIG` 字典，experts_total/active 来自环境变量 |
| 后端 metrics 获取 | scripts/demo/monitor.py | 109-152 | `fetch_llama_metrics()` — 读 llama-server `/slots` |
| SLIM-ARC 核心统计 | patches/llama-upstream/slim-arc-prefetch.h | 69-103 | `prefetch_scheduler` 类的统计方法 |
| SLIM-ARC 指标输出 | patches/llama-upstream/slim-arc-prefetch.cpp | 350-362 | `dump_metrics()` — 仅 stderr 输出，进程退出时调用 |

### 3.3 根因分析

Bug 2 有**三层根因**，形成完整的数据链路断裂：

#### 根因 A（前端）: `updateExperts()` 使用 `Math.random()` 生成假数据

`updateExperts()` 函数（行 327-342）的核心逻辑：

```javascript
// 行 331-335: 随机激活 active 个
const activeSet = new Set();
while (activeSet.size < Math.min(active, count)) {
    activeSet.add(Math.floor(Math.random() * count));
}
```

注释明确写着"随机激活 active 个"。该函数每 500ms 被 `pollMonitor()` 调用一次（行 421），每次调用都**随机**选择不同的专家格子高亮。这导致：

1. 可视化完全是假数据——随机闪烁，与实际推理过程无关
2. 用户看到的"专家激活"没有任何真实含义
3. 即使后端提供了真实数据，当前函数也不消费——它只接收 `active`（数量）和 `total`（总数），不接收"哪些专家被激活"的信息

#### 根因 B（后端）: `/api/monitor` 仅返回静态 config，无实时专家数据

`monitor.py` 的 `/api/monitor` 端点（行 155-175）返回的数据结构：

```python
{
    "config": CONFIG,           # 静态：experts_total=512, experts_active=10（来自环境变量）
    "memory": {...},            # 实时内存
    "metrics": {                # 来自 llama-server /slots
        "n_decoded": ...,
        "n_prompt_tokens": ...,
        "active": ...,
        "slots": ...,
    },
    "tps_history": [...],       # 实时 t/s 历史
    "timestamp": ...,
}
```

`config.experts_total` 和 `config.experts_active` 是**静态值**，来自 `start-demo.sh` 行 88-89 设置的环境变量（80B 模式下为 512 和 10）。这些值在进程启动时固定，不随推理过程变化。

`fetch_llama_metrics()`（行 109-152）从 llama-server `/slots` 接口获取数据，但 `/slots` 只返回：
- `is_processing` — 是否正在处理
- `n_prompt_tokens` — prompt token 数
- `next_token.n_decoded` — 已解码 token 数

**不包含任何专家激活/预取信息。**

#### 根因 C（数据源）: SLIM-ARC 核心有丰富统计，但未通过 HTTP 暴露

SLIM-ARC 的 `prefetch_scheduler` 类（`patches/llama-upstream/slim-arc-prefetch.h`）内部维护了丰富的实时统计：

| 统计项 | C++ 成员/方法 | 类型 | 含义 |
|--------|-------------|------|------|
| 专家预取字节 | `expert_prefetch_bytes_` | `atomic<size_t>` | 实际 WILLNEED 下发字节 |
| 命中字节 | `expert_hit_bytes_` | `atomic<size_t>` | 预取且下一 token 使用的字节 |
| 浪费字节 | `expert_waste_bytes_` | `atomic<size_t>` | 预取但未使用的字节 |
| 路由采样数 | `router_samples_` | `atomic<int>` | 统计采样数 |
| 每层专家激活频次 | `expert_pop_counts_` | `vector<vector<int>>` | 每层每个专家的激活次数 |
| 最近路由专家 | `cached_router_experts_` | `vector<vector<int>>` | 每层最近缓存的路由选中专家 ID |
| 最近预取专家 | `last_prefetched_experts_` | `vector<vector<int>>` | 每层最近实际下发的预取专家集合 |
| 总预取字节 | `total_prefetched_bytes()` | 方法 | 所有预取（权重+专家）总字节 |
| 总预取调用 | `total_prefetch_calls()` | 方法 | 预取调用总次数 |

此外，`unified_io_scheduler`（`slim-arc-unified-scheduler.h`）还有 `io_stats` 结构体包含 `expert_miss_rate`（专家预测 miss 率）和 `bandwidth_utilization`（带宽利用率）。

**但这些数据全部是 C++ 进程内部的 atomic 计数器，没有任何 HTTP 端点暴露它们。** `dump_metrics()` 方法（行 350-362）仅在 `prefetch_scheduler` 析构时（即 llama-server 进程退出时）向 stderr 输出一行汇总：

```
[SLIM-ARC-METRICS] expert prefetch: samples=N issued=Xmb hit=Ymb waste=Zmb hit_rate=R%
```

这不是实时数据，无法被 monitor.py 周期性读取。

### 3.4 数据链路分析

#### 当前数据流（断裂的）

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────┐
│ SLIM-ARC 核心 C++   │     │ llama-server     │     │ monitor.py      │     │ 前端         │
│ prefetch_scheduler  │     │ HTTP API         │     │ /api/monitor    │     │ index.html   │
│                     │     │                  │     │                 │     │              │
│ expert_prefetch_bytes_  │  │ /slots           │     │ fetch_llama_    │     │ updateExperts│
│ expert_hit_bytes_   │ ✗   │ - is_processing  │     │ metrics()       │     │ Math.random()│
│ expert_pop_counts_  │ 未暴露│ - n_decoded     │     │ → 只拿到上面4个 │     │ → 随机假数据 │
│ cached_router_experts│    │ - n_prompt_tokens│     │                 │     │              │
│                     │     │                  │     │ CONFIG (静态)   │     │              │
│                     │     │                  │     │ experts_total=512│    │              │
│                     │     │                  │     │ experts_active=10│    │              │
└─────────────────────┘     └──────────────────┘     └─────────────────┘     └──────────────┘
         │                           │                       │                      │
         │  数据存在但无 HTTP 出口    │  /slots 不含专家数据   │  只传静态数量          │  随机选格子
         └───────────────────────────┴───────────────────────┴──────────────────────┘
                              三层断裂点
```

#### 缺口定位

| 层级 | 缺口 | 说明 |
|------|------|------|
| C++ → HTTP | **无端点暴露** | SLIM-ARC 核心有 `expert_pop_counts_`、`expert_prefetch_bytes_` 等实时数据，但 llama-server 的 HTTP handler 没有任何端点返回这些值 |
| HTTP → monitor.py | **/slots 不含专家数据** | llama-server `/slots` 只返回 token 计数和 processing 状态，无专家激活/预取信息 |
| monitor.py → 前端 | **只传静态数量** | `/api/monitor` 的 `config.experts_total/active` 是环境变量静态值，不随推理变化 |
| 前端渲染 | **Math.random() 假数据** | `updateExperts()` 不消费任何"哪些专家"的信息，只用数量随机选格子 |

### 3.5 修改建议

#### 方案分级（按 red-line 合规性排序）

##### 方案 1（red-line 合规，推荐）: 前端改为确定性展示 + 后端补充可获取的间接数据

**不触碰核心代码**，仅在 scripts/demo/* 层面修复：

**修改点 3: 前端 `updateExperts()` 改为确定性展示**

**文件**: scripts/demo/index.html
**位置**: 行 327-342，`updateExperts(active, total)` 函数
**当前代码**:
```javascript
function updateExperts(active, total) {
    const el = document.getElementById('experts');
    const cells = el.children;
    const count = cells.length;
    // 随机激活 active 个
    const activeSet = new Set();
    while (activeSet.size < Math.min(active, count)) {
        activeSet.add(Math.floor(Math.random() * count));
    }
    for (let i = 0; i < count; i++) {
        cells[i].className = 'expert' + (activeSet.has(i) ? ' active' : '');
    }
    const sparse = total > 0 ? ((1 - active / total) * 100).toFixed(1) : 0;
    document.getElementById('experts-active').textContent = `${active} / ${total} 激活`;
    document.querySelector('.experts-label span:last-child').textContent = `稀疏率 ${sparse}%`;
}
```
**建议改为**:
```javascript
// SLIM-ARC FIX 2026-08-10: 移除 Math.random() 假数据，改为确定性展示前 N 个专家激活
// 真实专家激活数据需核心层暴露 HTTP 端点（见报告方案 2/3），当前以静态 config 展示
function updateExperts(active, total) {
    const el = document.getElementById('experts');
    const cells = el.children;
    const count = cells.length;
    const n = Math.min(active, count);
    for (let i = 0; i < count; i++) {
        cells[i].className = 'expert' + (i < n ? ' active' : '');
    }
    const sparse = total > 0 ? ((1 - active / total) * 100).toFixed(1) : 0;
    document.getElementById('experts-active').textContent = `${active} / ${total} 激活`;
    document.querySelector('.experts-label span:last-child').textContent = `稀疏率 ${sparse}%`;
}
```
**原理**: 移除 `Math.random()`，改为确定性地高亮前 `active` 个格子。不再是"假"的随机闪烁，而是如实展示 config 中的静态稀疏率信息（10/512 激活，稀疏率 98%）。用户至少能看到正确的稀疏比例展示。

**修改点 4: 后端 monitor.py 可选增加 /proc 间接数据**

**文件**: scripts/demo/monitor.py
**位置**: `fetch_llama_metrics()` 函数（行 109-152）内，可选追加
**建议**: 可在 `/api/monitor` 返回中增加一个 `moe_stats` 字段，从 llama-server 进程的 `/proc/<pid>/smaps_rollup` 读取 RSS（常驻内存），间接反映 mmap 加载进度：

```python
# SLIM-ARC FIX 2026-08-10: 增加间接 MoE 内存指标（RSS/模型大小比反映按需加载进度）
# 注意：这是间接指标，非专家级粒度。真实专家级数据需核心 HTTP 端点（见报告方案 2）
```

**局限性**: `/proc/smaps` 只能反映整体内存驻留情况，无法到专家粒度。此为可选增强，非必须。

##### 方案 2（需核心改动，违反 red-line #1，仅作分析记录）: llama-server 新增 HTTP 端点暴露专家统计

**如果要展示真实的专家级数据**，需要在 llama-server 的 HTTP handler 中新增端点（如 `/api/slim-arc-stats`），调用 `prefetch_scheduler` 的方法返回 JSON：

```json
{
    "expert_prefetch_bytes": 12345678,
    "expert_hit_bytes": 9876543,
    "expert_waste_bytes": 2469135,
    "hit_rate": 0.80,
    "router_samples": 500,
    "expert_pop_counts": [[3,5,2,0,...], ...],
    "cached_router_experts": [[12,45,7], ...]
}
```

**但这需要修改 llama-server 的 HTTP handler 代码**（位于 `src/llama-upstream/src/` 中的 server 相关文件），属于：
- **新增功能**（违反 red-line #1 "不新增功能"）
- 需要同步 patches/llama-upstream/ 与 src/llama-upstream/src/（red-line #3 镜像规则）
- 超出 "bug 修复" 范畴

**结论**: 此方案在当前 red-line 约束下**不可行**，仅作分析记录。如未来 red-line 放宽或单独审批，可考虑。

##### 方案 3（折中，需核心改动但最小化）: 修改 `dump_metrics()` 为周期性 stderr 输出 + monitor.py 解析

将 `dump_metrics()` 从"仅退出时调用"改为"每 N 秒输出一次到 stderr"，然后 `monitor.py` 通过 `tail` llama-server 的日志文件解析 `[SLIM-ARC-METRICS]` 行。

**但这仍然需要修改 `slim-arc-prefetch.cpp`**（核心代码），且需要同步 patches/ 和 src/。同样违反 red-line #1。

**结论**: 同样不可行，仅作分析记录。

### 3.6 数据链路缺口总结

| 环节 | 现状 | 需要什么 | red-line 合规可行性 |
|------|------|---------|-------------------|
| C++ 核心 → HTTP | 数据存在（atomic 计数器），无 HTTP 端点 | llama-server 新增 `/api/slim-arc-stats` 端点 | ❌ 违反 red-line #1（新增功能+改核心代码） |
| HTTP → monitor.py | `/slots` 不含专家数据 | 需要新端点或 `/slots` 扩展 | ❌ 依赖上一环 |
| monitor.py → 前端 | 只传静态 `experts_total/active` | 可选：增加间接指标（RSS/模型大小比） | ✅ 可行但粒度粗 |
| 前端渲染 | `Math.random()` 假数据 | 改为确定性展示或消费真实数据 | ✅ 可行（方案 1） |

**最终建议**: 在当前 red-line 约束下，**方案 1 是唯一合规的修改路径**——移除 `Math.random()` 改为确定性展示，如实反映 config 中的稀疏率。真实专家级数据需要核心层 HTTP 端点支持，受 red-line #1 约束暂不可实施。

---

## 4. 修改点汇总表

| # | 文件 | 位置（行号） | 建议改动 | SLIM-ARC FIX 标注 | red-line 合规 |
|---|------|------------|---------|-------------------|--------------|
| 1 | scripts/demo/index.html | 74 | `.chat-messages` 添加 `min-height: 0` | `// SLIM-ARC FIX 2026-08-10: flexbox 子项默认 min-height:auto 阻止 overflow-y 生效` | ✅ bug 修复 |
| 2 | scripts/demo/index.html | 509 | auto-scroll 改为仅底部附近时触发 | `// SLIM-ARC FIX 2026-08-10: 仅当用户已在底部附近时才自动滚动，避免阻止回看历史` | ✅ bug 修复 |
| 3 | scripts/demo/index.html | 327-342 | `updateExperts()` 移除 `Math.random()`，改确定性展示 | `// SLIM-ARC FIX 2026-08-10: 移除 Math.random() 假数据，改为确定性展示前 N 个专家激活` | ✅ bug 修复 |
| 4 | scripts/demo/monitor.py | 109-152（可选） | 可选增加 `/proc` 间接内存指标 | `# SLIM-ARC FIX 2026-08-10: 增加间接 MoE 内存指标` | ✅ 可选增强 |

---

## 5. 风险与边界

### 5.1 绝对不能碰的

| 范围 | 原因 |
|------|------|
| `patches/llama-upstream/slim-arc-prefetch.h/cpp` | 核心预取调度器，修改需同步镜像且属于核心机制改动 |
| `patches/llama-upstream/slim-arc-unified-scheduler.h/cpp` | 核心统一 I/O 调度器 |
| `patches/llama-upstream/slim-arc-kv-eviction.h/cpp` | 核心 KV 驱逐机制 |
| `patches/llama-upstream/slim-arc-on-demand.h/cpp` | 核心按需加载机制 |
| `scripts/apply-slim-arc.py` | 补丁应用脚本，修改影响镜像同步 |
| llama-server HTTP handler 源码 | 属于 llama-upstream 核心，新增端点=新增功能 |
| 任何推理/计算/调度算法逻辑 | red-line #1 明确禁止 |

### 5.2 可以修改的（本报告建议范围内）

| 范围 | 说明 |
|------|------|
| `scripts/demo/index.html` | 前端 UI bug 修复（CSS + JS），不属于 llama-upstream 镜像范畴 |
| `scripts/demo/monitor.py` | 监控后端 bug 修复/增强，不属于 llama-upstream 镜像范畴 |

### 5.3 Bug 2 的根本限制

Bug 2 的"形同虚设"根因之一是**核心统计数据未通过 HTTP 暴露**。在 red-line #1（不新增功能、不改核心代码）约束下，无法通过新增 llama-server HTTP 端点来暴露 `prefetch_scheduler` 的实时统计。因此：

- **能做的**: 移除前端假数据（`Math.random()`），改为如实展示静态 config 稀疏率
- **不能做的**: 展示真实专家级激活/预取数据（需核心 HTTP 端点）
- **替代方案**: 如需真实数据展示，需单独审批 red-line 豁免，或通过 `/proc` 间接指标（粒度粗）

---

## 6. 留痕清单

| 文件 | 说明 |
|------|------|
| docs/rk3588_test_notes/demo-ui-analysis-2026-08-10/ui-bug-analysis-report-2026-08-10.md | 本报告（主文档） |
| docs/rk3588_test_notes/demo-ui-analysis-2026-08-10/code-snippets.txt | 关键代码片段证据 |

---

## 7. 附录：分析过程阅读的文件清单

| 文件 | 用途 |
|------|------|
| scripts/demo/index.html | 前端 CSS + JS 全部代码（535 行） |
| scripts/demo/monitor.py | 监控后端全部代码（189 行） |
| scripts/demo/start-demo.sh | 启动脚本，确认环境变量与 llama-server 启动参数 |
| scripts/demo/llama_cli_server.py | 备用 CLI server，确认模型配置 |
| patches/llama-upstream/slim-arc-prefetch.h | SLIM-ARC 核心预取调度器头文件，确认可用统计方法 |
| patches/llama-upstream/slim-arc-prefetch.cpp | 预取调度器实现，确认 `dump_metrics()` 输出格式与调用时机 |
| patches/llama-upstream/slim-arc-unified-scheduler.h | 统一 I/O 调度器，确认 `io_stats` 结构 |
| patches/llama-upstream/slim-arc-kv-eviction.h | KV 驱逐管理器，确认统计方法 |
| scripts/apply-slim-arc.py | 补丁应用脚本，确认 SLIM-ARC 核心注入点 |
