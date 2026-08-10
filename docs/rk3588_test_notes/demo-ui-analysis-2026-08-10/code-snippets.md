# 关键代码片段证据 — UI Bug 分析 2026-08-10

本文件记录分析过程中引用的关键代码片段，作为报告的证据留痕。

---

## Bug 1 证据：对话窗口无法滚动

### 证据 1: body CSS — overflow: hidden 阻止 body 滚动

文件: scripts/demo/index.html 行 21-27
```css
body {
    font-family: 'Segoe UI', 'PingFang SC', 'Noto Sans CJK SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    overflow: hidden;  /* ← body 不滚动，溢出被裁剪 */
}
```

### 证据 2: .chat 容器 — flex column 布局

文件: scripts/demo/index.html 行 64-67
```css
.chat {
    background: var(--bg);
    display: flex; flex-direction: column;  /* ← flex column，子项默认 min-height: auto */
}
```

### 证据 3: .chat-messages — flex:1 + overflow-y:auto 但缺少 min-height:0

文件: scripts/demo/index.html 行 73-75
```css
.chat-messages {
    flex: 1; overflow-y: auto; padding: 24px;
    /* ← 缺少 min-height: 0，flexbox 默认 min-height: auto 阻止 overflow-y 生效 */
}
```

### 证据 4: 流式输出 auto-scroll — 每次 token 强制滚到底

文件: scripts/demo/index.html 行 506-510
```javascript
if (delta && delta.content) {
    text += delta.content;
    bubble.innerHTML = escapeHtml(text) + '<span class="cursor"></span>';
    messages.scrollTop = messages.scrollHeight;  /* ← 每 token 强制滚底，阻止回看 */
}
```

### 证据 5: 发送消息时 auto-scroll

文件: scripts/demo/index.html 行 459
```javascript
messages.scrollTop = messages.scrollHeight;
```

---

## Bug 2 证据：MoE 预取可视化形同虚设

### 证据 1: updateExperts() 使用 Math.random()

文件: scripts/demo/index.html 行 327-342
```javascript
function updateExperts(active, total) {
    const el = document.getElementById('experts');
    const cells = el.children;
    const count = cells.length;
    // 随机激活 active 个                          ← 注释明确写"随机"
    const activeSet = new Set();
    while (activeSet.size < Math.min(active, count)) {
        activeSet.add(Math.floor(Math.random() * count));  /* ← Math.random() 假数据 */
    }
    for (let i = 0; i < count; i++) {
        cells[i].className = 'expert' + (activeSet.has(i) ? ' active' : '');
    }
    const sparse = total > 0 ? ((1 - active / total) * 100).toFixed(1) : 0;
    document.getElementById('experts-active').textContent = `${active} / ${total} 激活`;
    document.querySelector('.experts-label span:last-child').textContent = `稀疏率 ${sparse}%`;
}
```

### 证据 2: pollMonitor() 只传静态 config 值

文件: scripts/demo/index.html 行 420-422
```javascript
// 专家
if (data.config.experts_total > 0) {
    updateExperts(data.config.experts_active, data.config.experts_total);
    /* ← 只传 config 中的静态数量，不传"哪些专家"信息 */
}
```

### 证据 3: monitor.py CONFIG — 静态环境变量

文件: scripts/demo/monitor.py 行 40-50
```python
CONFIG = {
    "model": os.environ.get("SLIM_ARC_MODEL", "Qwen3-4B-Q4_K_M"),
    "model_size": os.environ.get("SLIM_ARC_MODEL_SIZE", "2.4 GB"),
    "experts_total": int(os.environ.get("SLIM_ARC_EXPERTS_TOTAL", "0")),   # ← 静态
    "experts_active": int(os.environ.get("SLIM_ARC_EXPERTS_ACTIVE", "0")), # ← 静态
    "madv": os.environ.get("SLIM_ARC_MADV", "ON"),
    ...
}
```

### 证据 4: start-demo.sh 设置静态环境变量

文件: scripts/demo/start-demo.sh 行 88-89
```bash
export SLIM_ARC_EXPERTS_TOTAL="$EXPERTS_TOTAL"   # 80b 模式 = 512
export SLIM_ARC_EXPERTS_ACTIVE="$EXPERTS_ACTIVE"  # 80b 模式 = 10
```

### 证据 5: fetch_llama_metrics() — /slots 不含专家数据

文件: scripts/demo/monitor.py 行 109-152
```python
def fetch_llama_metrics() -> dict:
    """从 llama-server /slots 读取推理状态"""
    ...
    r = requests.get(f"{LLAMA_SERVER}/slots", timeout=2)
    ...
    result = {
        "slots": len(slots),
        "active": True,
        "n_decoded": total_decoded,           # ← 只有 token 计数
        "n_prompt_tokens": active_slot.get("n_prompt_tokens", 0),  # ← 只有 prompt 数
    }
    # ← 没有任何专家激活/预取数据
```

### 证据 6: SLIM-ARC 核心 prefetch_scheduler 有丰富统计但未暴露

文件: patches/llama-upstream/slim-arc-prefetch.h 行 69-103
```cpp
// Collect statistics
size_t total_prefetched_bytes() const { return total_bytes_.load(); }
int    total_prefetch_calls()   const { return total_calls_.load(); }

// Phase 2a: MoE expert prefetch
...
void dump_metrics() const;
size_t expert_prefetch_bytes() const { return expert_prefetch_bytes_.load(); }
size_t expert_hit_bytes()     const { return expert_hit_bytes_.load(); }
size_t expert_waste_bytes()   const { return expert_waste_bytes_.load(); }
```

### 证据 7: dump_metrics() 仅在析构时输出到 stderr

文件: patches/llama-upstream/slim-arc-prefetch.cpp 行 108-110, 350-362
```cpp
prefetch_scheduler::~prefetch_scheduler() {
    // SLIM-ARC FIX 2026-08-09: 退出时输出专家预取指标（改进 1）
    dump_metrics();   /* ← 仅在进程退出时调用 */
    ...
}

void prefetch_scheduler::dump_metrics() const {
    ...
    fprintf(stderr,
            "[SLIM-ARC-METRICS] expert prefetch: samples=%d issued=%.1fMB "
            "hit=%.1fMB waste=%.1fMB hit_rate=%.2f%% (accounted %.1fMB)\n",
            ...);
    /* ← 输出到 stderr，非 HTTP 端点，非周期性 */
}
```

### 证据 8: expert_pop_counts_ — 每层专家激活频次（有数据但无出口）

文件: patches/llama-upstream/slim-arc-prefetch.h 行 154-155
```cpp
// 每层专家激活频次计数（近窗口）
mutable std::vector<std::vector<int>>          expert_pop_counts_;
```

文件: patches/llama-upstream/slim-arc-prefetch.cpp 行 217-235
```cpp
// SLIM-ARC FIX 2026-08-09: 热门专家频次累加（改进 4）
...
for (int i = 0; i < n; ++i) {
    int eid = expert_ids[i];
    if (eid >= 0 && eid < (int)expert_pop_counts_[layer].size()) {
        expert_pop_counts_[layer][eid]++;  /* ← 实时累加，但无 HTTP 暴露 */
    }
}
```
