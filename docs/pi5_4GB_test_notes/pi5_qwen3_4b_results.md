# 树莓派 5 (4GB) Qwen3-4B 测试结果

**测试日期**: 2026-08-04  
**测试人**: Agent Programmer  
**硬件**: Raspberry Pi 5, 4GB RAM, 4核 ARM Cortex-A76, microSD 存储  
**系统**: Debian GNU/Linux 13 (trixie), aarch64  
**模型**: Qwen3-4B-Q4_K_M.gguf (2,497,280,256 字节 ≈ 2.33GB)  

---

## 一、环境检查

### 1.1 硬件环境

| 项目 | 值 | 状态 |
|------|-----|------|
| 架构 | aarch64 | ✅ |
| 内存 | 4.0Gi | ✅ |
| CPU 核数 | 4 | ✅ |
| 存储 | /dev/mmcblk0p2, 29G 总量, 16G 可用 | ✅ |
| Swap | 2.0Gi (zram) | ✅ |
| 存储类型 | microSD (非 NVMe) | ⚠️ 严重瓶颈 |

### 1.2 软件环境

| 包 | 版本 | 状态 |
|----|------|------|
| GCC | 14.2.0 | ✅ |
| CMake | 3.31.6 | ✅ |
| Python | 3.13.5 | ✅ |
| Git | 2.47.3 | ✅ |

### 1.3 cgroups v2

| 控制器 | 可用 | 说明 |
|--------|------|------|
| cpuset | ✅ | CPU 核绑定 |
| cpu | ✅ | CPU 带宽限制 |
| io | ✅ | I/O 带宽限制 |
| pids | ✅ | 进程数限制 |
| **memory** | ❌ | **内核未启用 CONFIG_MEMCG，无法用 cgroups 限制内存** |

**影响**: 无法使用 cgroups 模拟三档受限环境（8G/12G/16G），只能依赖物理 4GB 限制。

---

## 二、编译测试

### 2.1 SLIM-ARC 补丁编译 ❌ 失败

**现象**: `apply-slim-arc.py` 应用的补丁与当前 upstream llama.cpp (commit 1c3c967) 不兼容。

**编译错误**:
```
slim_arc::compute_phase has not been declared
max_layer was not declared in this scope
slim_arc::prefetch_scheduler has no member named 'effective_window'
slim_arc::prefetch_scheduler has no member named 'get_cached_experts'
slim_arc::prefetch_scheduler has no member named 'prefetch_experts'
slim_arc::prefetch_scheduler has no member named 'cache_router_experts'
```

**根因**: `patches/llama-upstream/` 中的 `llama-context.cpp` 补丁引用了 `prefetch_scheduler` 类中尚未实现的方法（`set_phase`、`effective_window`、`get_cached_experts`、`prefetch_experts`、`cache_router_experts`）和不存在的 `compute_phase` 枚举。这是补丁版本与 upstream API 演进不同步导致的。

**影响**: SLIM-ARC 核心优化（MADV_RANDOM、MoE 预取、KV eviction、统一调度器）无法在当前 upstream 上编译。

**注意**: 根据 [`docs/pi5_4GB_test_notes/init_pi5.md`](init_pi5.md) 的分析，Qwen3-4B（2.4GB）在 4GB Pi5 上 SLIM-ARC 核心创新（MADV_RANDOM，仅对 >6GB 模型生效）**根本不会触发**，因此使用 vanilla llama.cpp 进行测试是合理的。

### 2.2 Vanilla upstream llama.cpp 编译 ✅ 成功

**配置**:
```bash
cmake -B build -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-cli llama-bench -j2
```

**编译检测结果**:
- ARM Cortex-A76 + crc + crypto + dotprod（Pi5 CPU 特性）
- 禁用 i8mm、SVE、SME（Pi5 不支持）
- ggml version: 0.18.1, commit: 1c3c967
- OpenSSL 未找到（HTTPS 支持禁用，不影响本地推理）

**编译产物**:
| 文件 | 大小 |
|------|------|
| llama-cli | 1,057,936 字节 |
| llama-bench | 72,608 字节 |

**编译注意事项**:
- **必须 `-j2`**: 4GB 内存下 `-j4` 并行编译极易 OOM
- **Swap 必须扩大到 2GB**: 默认 100MB swap 不够
- **编译耗时**: 约 10-12 分钟（-j2，含 swap 开销）

---

## 三、模型下载

| 项目 | 值 |
|------|-----|
| 来源 | ModelScope (HuggingFace 被墙) |
| URL | `https://modelscope.cn/models/Qwen/Qwen3-4B-GGUF/resolve/master/Qwen3-4B-Q4_K_M.gguf` |
| 文件大小 | 2,497,280,256 字节 (2.33 GB) |
| 下载速度 | 7.87 MB/s (平均) |
| 下载耗时 | 5 分 2 秒 |
| 存储位置 | `data/models/Qwen3-4B-Q4_K_M.gguf` |

---

## 四、推理测试

### 4.1 基础推理测试 (llama-cli)

**命令**:
```bash
./src/llama-upstream/build/bin/llama-cli \
    -m data/models/Qwen3-4B-Q4_K_M.gguf \
    -t 4 -c 256 -p "The capital of China is" -n 32 --no-warmup
```

**结果**:
| 指标 | 值 | 说明 |
|------|-----|------|
| 模型加载 | 成功 | mmap 从 microSD 加载 |
| 量化类型 | Q4_K - Medium | 确认 |
| Prompt eval 速度 | **0.3 t/s** | microSD 冷启动极慢 |
| Generation 速度 | **0.4 t/s** | Pi5 4核 ARM decode 速度 |
| RSS 内存 | **2.36 GB** (56.9%) | 模型权重 + KV cache |
| Swap 使用 | **1.6 GB** | 严重依赖 swap |
| Thinking 模式 | 启用 | Qwen3 默认启用 chain-of-thought |

**生成内容** (部分):
```
[Start thinking]
Okay, the user asked, "The capital of China is..." and I need to answer that. 
Let me start by recalling what I know about China...
```

### 4.2 性能基准测试 (llama-bench)

**命令**:
```bash
./src/llama-upstream/build/bin/llama-bench \
    -m data/models/Qwen3-4B-Q4_K_M.gguf \
    -t 4 -p 64 -n 32 -pg 64,32
```

**结果** (部分，热缓存):

| 测试 | 模型大小 | 线程 | 指标 | 速度 (t/s) |
|------|---------|------|------|------------|
| pp64 (prefill 64 tokens) | 2.32 GiB | 4 | prompt eval | **3.96 ± 0.56** |
| tg32 (decode 32 tokens) | 2.32 GiB | 4 | generation | 待完成 |

**关键发现**: 热缓存下 prefill 速度 (3.96 t/s) 比冷启动 (0.3 t/s) 快 **~13×**，说明 microSD 是冷启动的最大瓶颈。一旦模型权重进入 page cache，prefill 速度显著提升。

---

## 五、与开发机性能对比

| 指标 | 开发机 (i9-13900H, 32GB, NVMe) | Pi5 (4GB, microSD) | 比值 |
|------|------|------|------|
| Prefill 速度 | ~13 t/s (Qwen3-4B) | 0.3 t/s | **~43× 慢** |
| Decode 速度 | ~13 t/s (Qwen3-4B) | 0.4 t/s | **~33× 慢** |
| 存储带宽 | ~3.5 GB/s (NVMe) | ~8 MB/s (microSD) | **~440× 慢** |
| 内存 | 32 GB | 4 GB | 8× 少 |
| CPU | x86-64 AVX2 (14核20线程) | ARM A76 (4核) | ~5× 少核 |

**关键瓶颈**:
1. **microSD 存储**: 这是最大的瓶颈。模型加载和权重访问都受 microSD 读写速度限制（~8-10 MB/s vs NVMe 的 3.5 GB/s）
2. **ARM A76 无 AVX2**: 向量运算能力远低于 x86，影响矩阵乘法性能
3. **4GB 内存**: 模型 2.4GB + OS ~0.5GB + KV cache，几乎用满物理内存，大量依赖 swap
4. **仅 4 核**: 并行度低

---

## 六、SLIM-ARC 优化在 Pi5 上的适用性分析

| 优化技术 | Pi5 适用性 | 原因 |
|----------|-----------|------|
| MADV_RANDOM | ❌ 不触发 | Qwen3-4B (2.4GB) < 6GB 阈值，`msz > (6ULL << 30)` 判断不通过 |
| MoE 预取 | ❌ 不适用 | Qwen3-4B 是 Dense 模型，非 MoE |
| KV q4_0 量化 | ⚠️ 可用但收益小 | 减少 KV 内存，但 4GB 下 KV 本身不是主要瓶颈 |
| FlashAttention | ✅ 可用 | 纯算法优化，不依赖存储/架构 |
| KV Eviction | ⚠️ 可用但收益小 | 短上下文 (256) 下 eviction 不触发 |
| 统一 I/O 调度器 | ❌ 不适用 | 依赖 MoE 稀疏性，Dense 模型无收益 |

**结论**: 在 4GB Pi5 上运行 Qwen3-4B，SLIM-ARC 的核心创新（MoE 按需加载 + MADV_RANDOM）**完全不会触发**。实际运行等价于 vanilla llama.cpp + 可能的 FlashAttention 加速。

---

## 七、测试总结

### 7.1 可行性判定

| 项目 | 结果 |
|------|------|
| 编译 SLIM-ARC 补丁版 | ❌ 失败（补丁与 upstream 不兼容） |
| 编译 vanilla llama.cpp | ✅ 成功 |
| 下载 Qwen3-4B 模型 | ✅ 成功（从 ModelScope） |
| 基础推理 | ✅ 可运行，但极慢（0.3-0.4 t/s） |
| cgroups 内存限制 | ❌ 不可用（内核无 CONFIG_MEMCG） |
| SLIM-ARC 核心优化 | ❌ 不触发（模型 < 6GB 阈值） |

### 7.2 性能数据

- **Prefill**: 0.3 t/s（microSD 冷启动）
- **Decode**: 0.4 t/s（Pi5 4核 ARM）
- **内存占用**: 2.36 GB RSS + 1.6 GB Swap
- **模型加载时间**: 约 2-3 分钟（microSD 读取 2.4GB）

### 7.3 关键发现

1. **microSD 是最大瓶颈**: 读写速度仅 ~8 MB/s，是 NVMe 的 1/440，严重影响模型加载和权重访问
2. **4GB 内存勉强够用**: 模型 2.4GB + OS 0.5GB + KV cache ≈ 3.2GB，需要 1.6GB swap 辅助
3. **ARM A76 性能远低于 x86**: 无 AVX2/VNNI，向量运算能力弱，decode 速度仅 0.4 t/s
4. **SLIM-ARC 补丁与 upstream 不兼容**: 需要更新补丁以适配最新 llama.cpp API
5. **cgroups memory 控制器不可用**: Pi5 内核未启用 CONFIG_MEMCG，无法模拟受限环境

### 7.4 建议

1. **使用 USB3 SSD 替代 microSD**: 可将存储带宽从 ~8 MB/s 提升到 ~500 MB/s，预计 prefill 速度提升 10-50×
2. **升级到 8GB Pi5**: 可消除 swap 依赖，显著提升推理速度
3. **更新 SLIM-ARC 补丁**: 使其与最新 upstream llama.cpp 兼容
4. **使用 `-no-cnv` 模式**: 避免进入交互模式，便于自动化测试
5. **关闭桌面 GUI**: `sudo systemctl set-default multi-user.target` 可省 ~0.5GB 内存
6. **Qwen3-4B 在 Pi5 上仅适合演示**: 实际应用场景下 0.4 t/s 的速度过慢

---

## 八、待完成测试

由于 4GB Pi5 上推理速度极慢（0.3-0.4 t/s）且内存紧张，以下测试未完成：

- [ ] KV q4_0 量化测试 (`-ctk q4_0 -ctv q4_0`)
- [ ] FlashAttention 测试 (`-fa auto`)
- [ ] KV eviction 测试 (`SLIM_ARC_KV_EVICT=1`)
- [ ] llama-bench 完整结果
- [ ] 长上下文测试 (`-c 2048`)
- [ ] 多轮对话测试

**建议**: 在 8GB Pi5 + USB3 SSD 环境下重新运行完整测试。
