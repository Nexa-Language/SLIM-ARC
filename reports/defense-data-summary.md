# SLIM-ARC 答辩数据汇总

## 一句话总结

**SLIM-ARC 通过 mmap + madvise 内核协同 + 统一 I/O 调度器，让 45GB MoE 模型在 8GB RAM 下 decode 速度提升 343%（4.4倍）。**

## 核心对比数据

### 1. Qwen3-Next-80B (45GB MoE) 在 8GB 环境 — 最核心成果

| 指标 | Baseline | SLIM-ARC | 提升 |
|------|---------|---------|------|
| prefill (pp4 t/s) | 0.17 | 0.20 | +17.6% |
| **decode (tg1 t/s)** | **0.07** | **0.31** | **+343% (4.4×)** |

### 2. Qwen3-4B (Dense, 2.4GB) 在 8GB 环境

| 指标 | Baseline | SLIM-ARC | 提升 |
|------|---------|---------|------|
| prefill (pp64 t/s) | 22.87 | 24.58 | +7.5% |
| **decode (tg16 t/s)** | **6.36** | **7.54** | **+18.6%** |

### 3. OLMoE-1B-7B (MoE, 3.9GB) 在 8GB 环境

| 指标 | Baseline | SLIM-ARC | 提升 |
|------|---------|---------|------|
| prefill (pp64 t/s) | 88.27 | 95.99 | +8.7% |
| decode (tg16 t/s) | 36.53 | 36.62 | 持平 |

## 技术创新点

### 1. mmap + MADV_RANDOM 按需加载
- 不修改 FlexInfer fork（架构不兼容），用 upstream llama.cpp + 内核协同
- `posix_madvise(MADV_RANDOM)` 关闭 readahead，只有访问的页面进 RAM
- 45GB 模型只占 8GB 物理内存

### 2. 禁用 GGML_CPU_REPACK
- CPU backend 默认 repack Q4_K→q4_K_8x8 分配匿名副本（内存翻倍）
- `cmake -DGGML_CPU_REPACK=OFF` 直接用 mmap 原始权重

### 3. prefetch_scheduler 层感知预取
- `madvise(WILLNEED)` 异步预取未来 N 层
- Prefill 大 window，Decode 小 window
- cgroup 自适应：模型能全缓存时自动跳过

### 4. MoE 专家选择性预取（Phase 2a）
- 从 `ffn_moe_topk` tensor 提取 router 输出的 top-k expert IDs
- 跨层预测：用 layer N 的 router 预测 layer N+1 的激活专家
- 对 expert tensor 子区域发 WILLNEED，只预取 2-12.5% 专家

### 5. 统一 I/O 调度器（Phase 3）
- 协调权重预取 + KV 换页 + 专家预取三路 I/O
- 5 种 runtime phase 的 budget 分配表
- 根据 stalls/page_faults/miss_rate 自适应调整

## 模块完成度

| 模块 | 状态 | 代码文件 |
|------|------|---------|
| 按需加载核心 | ✅ | `llama-model-loader.cpp` |
| prefetch_scheduler | ✅ | `slim-arc-prefetch.h/cpp` |
| MoE expert 预取 | ✅ | `register_expert_tensor` + router hook |
| 统一调度器 | ✅ | `slim-arc-unified-scheduler.h/cpp` |
| KV eviction 接口 | ✅ | `slim-arc-kv-eviction.h/cpp` |
| KV 推理流程集成 | 🔧 待实现 | 需修改 `llama-kv-cache.cpp` |
| Benchmark 框架 | ✅ | `run-quick-ablation.sh` |
| 设计文档 | ✅ | `docs/design/` 5 篇 |
| 消融报告 | ✅ | `reports/phase4-ablation-summary.md` |

## 三档环境

| Tier | RAM | CPU | 场景 |
|------|-----|-----|------|
| low | 8GB | 4核 | 端侧设备（Raspberry Pi 级） |
| mid | 12GB | 6核 | 中端设备 |
| high | 16GB | 8核 | 高端设备 |

## 数据复现

```bash
# 编译（禁用 repack）
cd src/llama-upstream/build
cmake -DGGML_CPU_REPACK=OFF ..
cmake --build . --target llama-bench -j$(nproc)

# 设置 cgroups
bash scripts/env/setup-cgroups.sh

# 跑消融
bash scripts/bench/run-quick-ablation.sh

# 80B 8GB 对比
sudo cgexec -g memory,cpu:slim-arc-low env LD_LIBRARY_PATH=build/bin SLIM_ARC_DISABLE=1 \
  ./build/bin/llama-bench -m ../../data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf -t 4 -p 4 -n 1 -mmp 1
sudo cgexec -g memory,cpu:slim-arc-low env LD_LIBRARY_PATH=build/bin \
  ./build/bin/llama-bench -m ../../data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf -t 4 -p 4 -n 1 -mmp 1
```

## 对比论文

| 论文 | 技术 | SLIM-ARC 改进 |
|------|------|--------------|
| FlexInfer | 张量级异步预取 | 用 mmap+MADV_RANDOM 替代 Direct I/O |
| DUAL-BLADE | NVMe-direct KV 换页 | 设计了 KV eviction 接口 |
| MobileMoE | 专家缓存 | 跨层 router 预测 + 子区域 WILLNEED |
| StreamingLLM | sink+sliding window | KV 分层管理设计 |

## 核心卖点

1. **45GB 模型在 8GB 跑通**（baseline repack 启用时 OOM，禁用后能跑但慢）
2. **decode 4.4 倍提升**（8GB 最受限环境，最核心数据）
3. **统一调度器架构**（权重+KV+expert 协同，非单点优化）
4. **可复现**（环境变量开关 + cgroups 脚本 + CSV 数据）
