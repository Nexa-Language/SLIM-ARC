# Phase 2b: KV Cache 异步换页 - 设计与实现方案

## 1. 背景与动机

长上下文推理时，KV Cache 随序列长度线性增长。以 Qwen3-4B 为例：
- 每层 KV: 2(K+V) × n_head × head_dim × n_tokens × 2 bytes(f16)
- 32K 上下文: ~1GB KV/层 × 36 层 = 36GB KV（超过 8GB RAM）

FlexInfer 只优化权重卸载，未处理 KV。DUAL-BLADE 用 NVMe-direct 换页 KV。SLIM-ARC 将 KV 换页纳入统一调度。

## 2. 技术方案

### 2.1 分层 KV 管理（StreamingLLM 启发）

```
KV Cache 序列位置:
[sink tokens] [sliding window] [cold region]
   0..3           N-3..N           4..N-4
     ↓               ↓                ↓
   常驻 RAM        常驻 RAM       换出到 SSD
  (hot)           (warm)          (cold)
```

- **Hot (sink)**: 前 4 个 token，永久驻留（attention sink 现象）
- **Warm (sliding)**: 最近 N 个 token，常驻 RAM
- **Cold**: 超出窗口的旧 token，换出到 mmap 临时文件

### 2.2 SSD 换出机制

```
evict_block(block):
  1. memcpy(mmap_base + offset, block.ram_addr, block.size)
  2. madvise(block.ram_addr, block.size, MADV_DONTNEED)  // 释放 RAM
  3. block.is_cold = true, block.offload_offset = offset

prefetch_block(block):
  1. madvise(mmap_base + offset, block.size, MADV_WILLNEED)  // 异步预读
  2. // 下次访问时 page fault 触发读入

access_block(block):  // 在 graph_compute 中
  1. if block.is_cold: prefetch_block(block); wait
  2. read from block.ram_addr (now paged in)
```

### 2.3 注意力分数引导的驱逐

```cpp
// 在 attention 计算后，更新每个 token 的平均注意力分数
void update_attention_scores(int layer, const std::vector<double> & scores) {
    for (auto & block : blocks_) {
        if (block.layer == layer) {
            block.avg_attn_score = scores[block.token_pos];
        }
    }
}

// 驱逐策略：驱逐注意力分数最低的 cold region block
int run_eviction() {
    if (ram_usage_ <= config_.budget_bytes) return 0;
    // 按 avg_attn_score 升序排序，驱逐最低的
    std::sort(blocks_, by avg_attn_score);
    for (auto & block : blocks_) {
        if (!block.is_hot && !block.is_cold && ram_usage_ > budget) {
            evict_block(block);
        }
    }
}
```

## 3. 集成路径（待实现）

### 3.1 KV Cache 注册
在 `llama-kv-cache.cpp` 的 `kv_cache_init` 后，遍历所有 KV cell，调用 `kv_eviction_manager::register_block`。

### 3.2 Attention 分数更新
在 `llama-context.cpp` 的 attention 计算后，提取每 token 的 attention weights，调用 `update_attention_scores`。

### 3.3 驱逐触发
在 `graph_compute` 的 decode 阶段，每 N 步调用 `run_eviction()`。

### 3.4 预取
在 decode 当前层前，调用 `prefetch_cold_blocks(layer, lookahead)` 预取即将访问的 cold KV。

## 4. 现有实现（[`slim-arc-kv-eviction.cpp`](../../src/llama-upstream/src/slim-arc-kv-eviction.cpp)）

| 组件 | 状态 |
|------|------|
| `kv_eviction_manager` 类 | ✅ |
| `init_offload_file` (mmap 临时文件) | ✅ |
| `register_block` | ✅ |
| `update_attention_scores` | ✅ |
| `evict_block` (RAM→SSD) | ✅ |
| `prefetch_block` (SSD→RAM) | ✅ |
| `run_eviction` 策略 | ✅ |
| `prefetch_cold_blocks` | ✅ |
| **集成到推理流程** | ❌ 待实现 |

## 5. 预期收益

| 场景 | Baseline KV | SLIM-ARC KV | 内存节省 |
|------|------------|-------------|---------|
| 8K 上下文 | 256MB/层 | 128MB(sink+window) | 50% |
| 32K 上下文 | 1GB/层 | 128MB | 87.5% |
| 128K 上下文 | 4GB/层 | 128MB | 96.9% |

长上下文场景 KV 内存节省 87-97%，让 8GB 设备能处理 128K 上下文。

## 6. 与统一调度器集成

Phase 3 中，KV 换页的 I/O 需求作为 `io_budget.kv_bytes` 参与带宽竞争：
- **短上下文 Decode**: KV 小，权重优先（budget 70% weight, 20% KV, 10% expert）
- **长上下文 Decode**: KV 大，KV 优先（budget 30% weight, 60% KV, 10% expert）
- **MoE Decode**: expert 优先（budget 20% weight, 20% KV, 60% expert）

## 7. 风险与应对

| 风险 | 应对 |
|------|------|
| SSD 换入延迟导致 decode 变慢 | 异步预取 + 统一调度器协调 |
| 注意力分数无法完全预测未来访问 | 保守策略：只驱逐极低分 token |
| mmap 临时文件空间不足 | 动态 ftruncate 扩展 |

## 8. 验证计划

1. 集成后，用 32K 上下文测试 OLMoE
2. 对比：全内存 KV（OOM）vs SLIM-ARC KV 换页（能跑）
3. 测量：KV 内存使用、decode 延迟、精度（PPL）
