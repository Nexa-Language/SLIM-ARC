# macOS 原生 SLIM-ARC 80B 决赛演示

## 一分钟结论

在 Apple M4 Pro、48 GiB 统一内存上，SLIM-ARC 现在可以原生运行完整的
Qwen3-Next-80B-A3B-Instruct：

- 总参数量为 79.67B，每 token 激活约 3B 参数；不是替换成小模型。
- importance-aware `IQ2_M` 文件为 26,056,028,256 bytes，较官方 Q4_K_M 的
  48,410,988,384 bytes 减少 46.18%。
- 完整权重和执行工作区可同时进入 Metal；真实 256-token API 请求达到
  **46.21 tok/s**，Prefill 为 **172.35 tok/s**。
- 128-token、两次重复的 `llama-bench` 为 **45.90/45.72 tok/s**，均值
  **45.81 tok/s**。
- 同一 IQ2_M 权重在 1-thread CPU-only、关闭可选 SLIM-ARC 策略时为
  **4.96 tok/s**，受控加速为 **9.23 倍**。
- 用官方 Q4_K_M、background QoS、1-thread CPU-only 做直观慢速档时，真实 server
  Decode 为 **1.83 tok/s**；与完整优化栈相比约 **25.2 倍**。这是系统栈演示，不冒充
  单变量消融。

## 现场演示：先慢后快

两轮都使用同一台 Mac、同一个原生 `llama-server` 和同一句问题。不要同时运行两个
80B server。

固定问题：

```text
用两句话介绍 SLIM-ARC 如何让 80B MoE 模型在内存受限设备运行。
```

### 第一轮：慢速、无优化调度档

```bash
bash scripts/macos/run-native-demo.sh baseline llama
```

终端打印 `Ready` 后，浏览器会打开 <http://127.0.0.1:18080/>。这一档使用官方
Q4_K_M、CPU-only、1 thread、macOS background QoS，并关闭 expert prefetch、
residency、reclaim 等可选策略。真实冷请求的 22-token Prefill 用时 12.92 秒，8-token
Decode 用时 4.36 秒，即 `1.83 tok/s`；可以直观看见首 token 等待和逐 token 输出。

展示完后执行：

```bash
bash scripts/macos/run-native-demo.sh stop
```

### 第二轮：SLIM-ARC 完整优化栈

```bash
bash scripts/macos/run-native-demo.sh optimized llama
```

仍输入同一句问题，建议把最大输出设为 128 tokens。优化档使用 importance-aware
IQ2_M、全量 Metal offload、FlashAttention 和 6-thread 调度。真实 256-token请求达到
`46.21 tok/s`，平均约 `21.64 ms/token`。IQ2 已在页缓存中时模型加载约 1.85 秒；刚展示
完另一份 48.4GB Q4、页缓存完全切换时实测为 23.83 秒。

推荐现场解说：

> 前一轮展示 80B MoE 在 background 单线程 CPU、官方 Q4 权重和关闭可选访存策略时的
> 退化，真实 server 约 1.83 token/s。现在切换到 SLIM-ARC 的重要性感知低比特布局和
> 统一内存全驻留路径；
> 同一 80B-A3B 架构的实测持续速度超过 45 token/s，权重占用从 48.4GB 降到
> 26.1GB。这里展示的是完整系统栈效果；同权重受控 A/B 也有 4.96 到 45.81 token/s，
> 约 9.23 倍。

## DeepSeek Harness 极简 UI

如果需要用 Agent/Harness 界面展示：

```bash
bash scripts/macos/run-native-demo.sh optimized harness
```

打开 <http://127.0.0.1:3080/> 后，选择
`Qwen3-Next-80B-A3B (SLIM-ARC)`。极简模式只保留持久 Bash 和文件编辑工具，避免标准
编码 Agent 注入约 16K tokens 的系统上下文。性能主展示仍推荐 llama 自带聊天页，因为
它没有 Agent 工具协议的首 token 开销。

最终浏览器复现中，Harness 显示 1K input、71 output、`47 tok/s`；server 对应日志为
`47.28 tok/s`，没有 token-limit warning。演示脚本通过用户级 `launchctl` 托管 server 和
Harness，因此启动命令退出后两个页面仍保持在线，`stop` 会同时移除两个托管进程。

Harness 使用的 `pi-ai` 适配器会固定预留 4096 tokens 的上下文安全余量。因此 overlay
将适配器侧 `contextWindow` 声明为 8192，而 server 使用真实的 4096-token 上下文。如果
两边都写 4096，适配器会把 `max_completion_tokens` 夹成 1，页面会在首 token 后错误显示
“已达到输出 token 上限”。

## 三个可复现档位

| 档位 | 命令 | 权重 | 执行路径 | 实测 Decode |
|---|---|---|---|---:|
| Slow baseline | `bash scripts/macos/run-native-demo.sh baseline llama` | Q4_K_M | background CPU, 1 thread | 1.83 tok/s server / 1.04 tok/s bench |
| Controlled CPU | `bash scripts/macos/run-native-demo.sh cpu-iq2 llama` | IQ2_M | CPU-only, 1 thread | 4.96 tok/s |
| SLIM-ARC optimized | `bash scripts/macos/run-native-demo.sh optimized llama` | IQ2_M | full Metal, FA, 6 threads | 46.21 tok/s API / 45.81 tok/s bench |

`cpu-iq2` 与 `optimized` 使用完全相同的权重，适合说明执行路径贡献；`baseline` 与
`optimized` 展示从官方 Q4 无优化退化档到完整 SLIM-ARC 栈的现场观感。两种比较必须分开
表述。

## 为什么全驻留路径关闭 host expert prefetch

SLIM-ARC 的策略随内存层次变化：当 48.4GB Q4 无法完整驻留时，按需映射、预测预取和
错误页回收用于掩盖缺页 I/O；importance-aware IQ2_M 把权重降到约 26.1GB 后，完整模型
已能留在 Metal 推荐工作集内，此时继续对 host mmap 发 `WILLNEED` 会与 GPU 争用带宽。

128-token 调优结果验证了这一点：

| Metal 配置 | Decode 均值 |
|---|---:|
| 6 threads，host expert prefetch off，FA on | **45.81 tok/s** |
| 8 threads，host expert prefetch off，FA on | 45.22 tok/s |
| 10 threads，host expert prefetch off，FA on | 43.28 tok/s |
| 12 threads，host expert prefetch off，FA on | 39.93 tok/s |
| 12 threads，host expert prefetch on，FA on | 39.58 tok/s |

因此最终档不是“关闭 SLIM-ARC”，而是选择 SLIM-ARC 的全驻留分支，避免在已经驻留时重复
做主机 I/O 建议。

## 模型制备与复现

量化工具来自仓库固定的 llama.cpp 源码，不需要下载另一份 80B 权重：

```bash
cmake --build src/llama-upstream/build-macos --target llama-quantize -j 4
```

importance matrix 来源固定为
`ilintar/Qwen3-Next-80B-A3B-Instruct-GGUF@9daa2ea7c6eb2fea72816ffe79a9be1b5322e4c1`
的 `qwen3_next_full_imatrix.gguf`，本地 SHA-256 为
`0d574fc250a9b163c14dfe86e5c87e25db389bb83fe7de96dd644b9d897465e1`。它包含
2,588 个校准 chunks、540 个 importance entries。

从现有 Q4 本地生成 IQ2_M：

```bash
src/llama-upstream/build-macos/bin/llama-quantize \
  --allow-requantize \
  --imatrix data/calibration/qwen3_next_full_imatrix.gguf \
  data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf \
  data/models/Qwen3-Next-80B-A3B-Instruct-IQ2_M-SLIM-ARC.gguf \
  IQ2_M 12
```

本机量化耗时约 794.50 秒。由于输入是 Q4 而非 F16，这属于 requantization；它满足现场
运行和回答连贯性验证，但未经独立精度基准前，不应声称与原模型精度等价。
生成文件 SHA-256 为
`d8c223bde11695dd562cc5144bf952a059a66e4b6b654b57efddf4a6746406c3`。

## 最终测量合同

设备为 Apple M4 Pro、48 GiB 统一内存。最终 server 参数为 `-ngl 99 -fa on -t 6
-tb 6 -c 4096 -b 512 -ub 256`，单并发、KV 为 F16。进程在加载后 `ps` 报告 RSS
约 25,836,896 KiB（约 24.64 GiB）。

最终 256-token API 请求：

| 指标 | 数值 |
|---|---:|
| Prompt tokens | 63 |
| Completion tokens | 256 |
| Prefill | 172.35 tok/s |
| Decode | **46.21 tok/s** |
| Decode latency | 21.64 ms/token |
| Model load | 1.85 s（warm）/ 23.83 s（从 Q4 冷切换） |

`llama-bench` 的同权重受控 CPU 档为 `4.9617 tok/s`；全 Metal、6-thread 的两个
128-token 样本为 `45.9004` 和 `45.7161 tok/s`。

## 现场注意事项

1. 演示前关闭 Docker/Colima、大型 IDE 和无关浏览器标签页。
2. 先等终端打印 `Ready` 再提问；warm load 约 2 秒，从 Q4 冷切换约 24 秒。
3. 两轮使用同一句 prompt 和相同最大输出长度，不比较首 token 与稳态 Decode。
4. 切换前执行 `bash scripts/macos/run-native-demo.sh stop`，不要并行加载两个 80B。
5. 页面打不开时执行 `bash scripts/macos/run-native-demo.sh status`；健康检查应返回
   `{"status":"ok"}`。
6. 新运行的日志默认位于 `${TMPDIR:-/tmp}/slim-arc-native-demo/`；可通过
   `SLIM_ARC_STATE_DIR` 指定其他本地目录，运行状态不进入 Git。
7. 低比特模型和 calibration 文件是本机可再生大文件，不应提交到 Git。
