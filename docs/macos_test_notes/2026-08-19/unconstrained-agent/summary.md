# Mac Qwen3-Next × DeepSeek Harness 极简演示

## 结论

SLIM-ARC 的 Qwen3-Next-80B-A3B Q4_K_M 已在本机 Mac 上以 CPU-only 方式启动，并接入 DeepSeek Harness Web UI。最终会话使用单 Bash 工具的 `SLIM-ARC 极简演示` preset，完成真实时间读取、`hello_world.py` 写入和程序执行。

最终输出：

```text
Hello, world!
Captured at: 2026-08-19 13:54:28 CST
```

UI 中报告的文件路径为 `/workspace/hello_world.py`。完整页面见 [harness-ui-final.png](harness-ui-final.png)。

## 运行配置

| 项目 | 最终配置 |
|---|---|
| Mac | 48 GiB RAM，14 个逻辑 CPU |
| Colima | Apple Virtualization.Framework，AArch64，40 GiB RAM，12 CPU |
| 容器限制 | `memory=0`、`nano_cpus=0`、空 `cpuset`，即无容器 cgroup 限额 |
| 模型 | Qwen3-Next-80B-A3B-Instruct Q4_K_M，48,410,988,384 bytes |
| 模型 SHA-256 | `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a` |
| 镜像 | `slim-arc-llama-a8-server:4f48438e` |
| SLIM-ARC commit | `4f48438e79764c6b04d0f3d3456d1f9968b4a06d` |
| llama.cpp commit | `360e1349f0009c5ad99d21e3c4546b707addc68a` |
| Server | decode 10 threads，prefill 12 threads，4K context，batch 2048，ubatch 512，CPU-only |
| SLIM-ARC 策略 | `SLIM_ARC_DYNAMIC_MADV=0`，保留已建立的热页工作集 |
| Harness | Web UI，`SLIM-ARC 极简演示`，仅持久 Bash |

模型文件以只读 bind mount 直接复用，未复制第二份 48 GB 模型。最终主机磁盘仍有约 53 GiB 可用。

## 性能结果

保守配置为 8 threads、16 GiB VM、batch 256、ubatch 64。其已完成的 headless 基线总耗时 269 秒，服务日志中的典型 prefill 为 3.69 tok/s、decode 约 0.97 tok/s。

最终高吞吐配置的完整 UI 会话指标：

| 指标 | 结果 |
|---|---:|
| UI 端到端用时 | 2分00秒 |
| LLM 时间 | 1分49秒 |
| 工具调用时间 | 11.2秒 |
| 首 token | 46秒 |
| 会话平均首 token | 19.3秒 |
| Harness 会话输出速度 | 2.7 tok/s |
| 缓存命中率 | 67% |
| 输入 / 输出 | 约 1.1K / 141 tokens |

llama-server 的分轮数据：

| 阶段 | Prompt tokens | Prefill | Decode tokens | Decode |
|---|---:|---:|---:|---:|
| 标题请求 | 115 | 9.85 tok/s | 10 | 3.15 tok/s |
| 主请求，生成 `set +H` | 294 | 10.88 tok/s | 21 | 2.64 tok/s |
| 工具反馈后生成写入命令 | 16 | 5.35 tok/s | 73 | 2.86 tok/s |
| 程序执行后生成最终回答 | 43 | 7.23 tok/s | 47 | 1.99 tok/s |

相较保守配置，热态主请求 prefill 从约 3.69 tok/s 提升到 10.88 tok/s，约 2.95 倍；decode 从约 0.97 tok/s 提升到 2.64–2.86 tok/s，约 2.7–2.9 倍。不同轮次长度与缓存状态不同，因此这些数字用于本机演示调优，不替代比赛的固定合同 A/B 数据。

### 吞吐瓶颈诊断与热态配置

Q4_K_M 文件为 48,410,988,384 bytes（约 45.1 GiB），而 Colima VM 为 40 GiB；除模型映射外，llama.cpp 还需要约 1.9 GiB 匿名运行时内存和 KV/graph buffer。因此当模型页被其他任务挤出后，工作集不可能全部常驻：冷态 32-token 直连请求的 decode 会下降到 0.96 tok/s，并观察到约 1 GB 新增块读。这说明此时主瓶颈是页缓存抖动与磁盘回读，而不是 Harness UI。

在同一 CPU-only 镜像中关闭每 token 整段动态 `madvise`，使用 16-token prompt + 24-token generation 进行线程扫描：6/8/10/12 线程的 decode 分别为 1.06/1.65/3.92/2.17 tok/s。10 线程与 M4 Pro 的 10 个性能核匹配，12 线程则会加重共享内存带宽竞争。据此将演示后端调整为 decode 10 线程、prefill 12 线程并关闭整段动态页建议。优化后的两次 24-token 直连验证为 3.58 tok/s（首请求）和 4.31 tok/s（热态）；后者相对原演示的 2.64–2.86 tok/s 提升约 51%–63%。

短矩阵同时记录到专家预取命中率 38.17%：累计预取 83.4 GB，其中 51.5 GB 未命中实际路由专家。这是下一步优化的主要空间，但不应将 20–30 tok/s 视为当前配置的可达目标：Colima Linux 无法使用 Apple Metal，当前镜像也明确输出 `no usable GPU found`。要进入 20 tok/s 级别，需要将演示路径迁到 macOS 原生 Metal，并使用能在 48 GiB 统一内存内同时容纳权重、KV 和运行时 buffer 的更小量化。

## 实验时的演示入口

- DeepSeek Harness UI：`http://127.0.0.1:3080/`
- Qwen3-Next OpenAI-compatible API：`http://127.0.0.1:18080/v1`
- 模型健康检查：`http://127.0.0.1:18080/health`

归档截图显示模型选择、`SLIM-ARC 极简演示` preset、两条 Bash 工具调用、程序路径与真实时间输出。会话 JSONL 和本机有效配置不属于公开研究证据，未纳入仓库。

## 实现说明

DeepSeek Harness 原生 `minimal` preset 同时暴露 Bash 和 `str_replace_editor`。80B CPU-only 首轮需要处理更大的工具 schema，曾触发 300 秒 stream idle timeout。演示版进一步裁剪为单 Bash 工具，并将交互式 Bash 的 history expansion 处理写入 persona：第一条命令独立执行 `set +H`，之后再执行包含 `Hello, world!` 的写入命令。

这种裁剪不修改 DeepSeek Harness 仓库，也不污染它现有的工作树；模型路由、Web overlay 和可复现 preset 均保存在本目录。
