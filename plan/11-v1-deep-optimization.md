# 08-v1: 深度优化计划 - 追赶 SOTA

## 背景
当前 80B 16GB: tg8=0.90 t/s，距离"流畅"(2+ t/s)还有差距。论文提出多种优化方法未尝试。

## 未尝试的优化方法（按 ROI 排序）

### P0 高价值易实现
1. **prefill/decode 动态 MADV 切换**
   - prefill 前对 mmap 区域发 `MADV_WILLNEED`（全预读，快速预热）
   - prefill 后切回 `MADV_RANDOM`（decode 精准加载）
   - 预期：消除 prefill -57% 代价，prefill 速度翻倍
   - 实现：保存 mmap 地址范围，graph_compute 中按 phase 切换

2. **KV Cache 量化（f16 → q4_0）**
   - llama-bench 支持 `-ctk q4_0 -ctv q4_0`
   - KV 内存减半，更多 RAM 给权重缓存
   - 预期：长上下文 decode 提升 30-50%

3. **更多线程 + 线程亲和性**
   - 当前用 8 threads，i9-13900H 有 14C/20T
   - 绑定 P-core（性能核）减少调度开销
   - 预期：+10-20%

### P1 中等价值
4. **重新启用 repack + 逐层 evict**
   - repack 加速 GEMM 2-3x，但内存翻倍
   - 方案：启用 repack，但在每层计算后 evict repacked buffer
   - 风险：复杂度高，可能破坏推理

5. **expert tensor DONTNEED**
   - 计算完的专家权重立即 DONTNEED 释放
   - 对 MoE 模型减少内存压力
   - 预期：更多 RAM 给热数据

6. **投机解码（Speculative Decoding）**
   - 用 Qwen3-4B 作为 draft model，80B 作为 verifier
   - 批量验证多个 token，摊薄 I/O
   - upstream llama.cpp 已支持 `--draft-model`
   - 预期：decode 2-3x

### P2 探索性
7. **融合反量化** - 需修改 GEMM kernel
8. **Tile 级流水线** - 需修改计算图
9. **NUMA 感知** - WSL2 单 NUMA，价值有限

## 执行计划

### Step 1: 动态 MADV 切换（P0）
- 在 init_mappings 保存 mmap 区域到全局变量
- graph_compute 中：prefill 前 MADV_WILLNEED，decode 前 MADV_RANDOM
- 测量 prefill 恢复 + decode 保持

### Step 2: KV 量化（P0）
- 测试 `-ctk q4_0 -ctv q4_0` 在 80B 上的效果
- 对比 f16 vs q4_0 的速度和精度

### Step 3: 投机解码（P1）
- 用 Qwen3-4B 作为 80B 的 draft model
- `llama-cli --model 80B.gguf --draft-model Qwen3-4B.gguf`
- 测量 decode 加速

### Step 4: expert DONTNEED（P1）
- graph_compute 后对已计算的 expert tensor 发 DONTNEED
- 测量内存释放和速度影响

## 原计划数据缺口
- [ ] Q8_0 精度对比（未测）
- [ ] 全矩阵消融（只测了 baseline vs slim-arc，缺单点组合）
- [ ] 长 context（32K）测试
- [ ] 多 benchmark（只用了 llama-bench，缺 perplexity/精度）
