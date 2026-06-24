# Phase 2b: KV Cache 内存占用分析

## 概述

分析不同模型在不同上下文长度下的 KV Cache 内存占用，论证 Phase 2b KV 换页的必要性。

## KV Cache 内存计算

### 公式
```
KV Cache (bytes) = n_layer × 2(K+V) × n_seq × n_head_kv × head_dim × dtype_size
```

### Qwen3-4B (Dense)
- n_layer = 36, n_head_kv = 4(GQA), head_dim = 128, f16
- Per token: 36 × 2 × 4 × 128 × 2 = 73,728 bytes ≈ 72 KB
- 512 tokens: 36 MB
- 4K tokens: 288 MB
- 32K tokens: 2.3 GB
- 128K tokens: 9.2 GB（超过 8GB RAM）

### OLMoE-1B-7B (MoE)
- n_layer = 16, n_head_kv = 4, head_dim = 128, f16
- Per token: 16 × 2 × 4 × 128 × 2 = 32,768 bytes ≈ 32 KB
- 512 tokens: 16 MB
- 4K tokens: 128 MB
- 32K tokens: 1 GB
- 128K tokens: 4 GB

### Qwen3-Next-80B-A3B (MoE)
- n_layer = 48, n_head_kv = 8(GQA), head_dim = 128, f16
- Per token: 48 × 2 × 8 × 128 × 2 = 196,608 bytes ≈ 192 KB
- 512 tokens: 96 MB
- 4K tokens: 768 MB
- 32K tokens: 6 GB（接近 8GB 限制）
- 128K tokens: 24 GB（远超 16GB RAM）

## 内存预算分析

### 8GB 环境（最受限）
| 模型 | 权重 | KV@4K | KV@32K | KV@128K | 可行性 |
|------|------|-------|--------|---------|--------|
| Qwen3-4B | 2.4GB | 288MB | 2.3GB | 9.2GB | 32K可行，128K需换页 |
| OLMoE | 3.9GB | 128MB | 1GB | 4GB | 32K可行，128K需换页 |
| Qwen3-Next-80B | 45GB(mmap) | 768MB | 6GB | 24GB | 32K需换页，128K必须换页 |

### 16GB 环境
| 模型 | 权重 | KV@4K | KV@32K | KV@128K | 可行性 |
|------|------|-------|--------|---------|--------|
| Qwen3-4B | 2.4GB | 288MB | 2.3GB | 9.2GB | 128K可行 |
| OLMoE | 3.9GB | 128MB | 1GB | 4GB | 可行 |
| Qwen3-Next-80B | 45GB(mmap) | 768MB | 6GB | 24GB | 32K可行，128K需换页 |

## Phase 2b KV 换页收益

### 目标场景：长上下文（32K+）
- 80B + 32K context: KV 6GB + 权重(mmap按需) → 需要 KV 换页
- 80B + 128K context: KV 24GB → 必须换页

### 换页策略（StreamingLLM 启发）
```
[sink tokens 0-3] [sliding window N-3..N] [cold region 4..N-4]
      ↓                    ↓                      ↓
   常驻 RAM             常驻 RAM              换出到 SSD
```

### 预期效果
- 32K context: KV RAM 占用从 6GB → 256MB（sink 4 + window 4092），节省 96%
- 128K context: KV RAM 从 24GB → 256MB，节省 99%

## 当前实现状态

### 已完成
- [`slim-arc-kv-eviction.h/cpp`](../src/llama-upstream/src/slim-arc-kv-eviction.cpp): 完整的 KV eviction manager 接口
  - `register_block`: 注册 KV block
  - `evict_block`: RAM → SSD mmap 文件
  - `prefetch_block`: SSD → RAM（madvise WILLNEED）
  - `run_eviction`: 按注意力分数驱逐
  - `prefetch_cold_blocks`: 预取即将访问的 cold KV

### 待集成
- 在 `llama-kv-cache.cpp` 的 allocation 后调用 `register_block`
- 在 attention 计算后收集注意力分数，调用 `update_attention_scores`
- 在 decode 路径调用 `run_eviction` 和 `prefetch_cold_blocks`

## 结论

Phase 2b 的 KV 换页对长上下文场景至关重要：
- 32K context 下 80B 需要 KV 换页避免 OOM
- 128K context 下所有模型都需要 KV 换页
- 接口已完整实现，推理流程集成是后续工作

参考 DUAL-BLADE 的 NVMe-direct 思路，SLIM-ARC 用 mmap 临时文件 + madvise 实现等效效果，且与权重 prefetch 共享统一调度器。
