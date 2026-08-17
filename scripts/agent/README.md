# SLIM-ARC Edge Agent Harness

该 Harness 用常驻 OpenAI-compatible endpoint 完成有界的 `LLM -> shell -> observation -> LLM` 循环，重点减少端侧 Agent 的上下文和输出开销。它不负责启动或下载模型。

```bash
python3 scripts/agent/edge_agent.py \
  --endpoint http://127.0.0.1:8080 \
  --model local-model \
  --cwd ./demo-workdir \
  --metrics ./agent-metrics.jsonl \
  "检查当前目录磁盘占用，并用一句话总结"
```

模型只能返回以下两种 JSON：

```json
{"tool":"shell","args":["df","-h","."]}
```

```json
{"final":"当前目录所在文件系统还有 47 GiB 可用空间。"}
```

默认 shell allowlist 只包含只读诊断命令；命令不经过 shell 解释器，且受到固定工作目录、路径逃逸检查、8 秒超时和 4 KiB 输出上限约束。若端侧 decode 低于 `--slow-tps`，下一轮自动缩减 `max_tokens`，最低不小于 `--min-tokens`。

`--llama-cli` 与 `--llama-model` 可提供兼容 fallback，但该路径每步都会重新加载模型，不应作为性能演示路径。

## 已验证的闭环

仓库用确定性 OpenAI-compatible SSE endpoint 验证了完整流程：模型先请求
`uname -m`，Harness 在受限工作目录执行命令并回填 observation，随后模型返回最终答案。
首轮估算输出速度为 1.999 t/s，触发下一轮 `max_tokens` 从 192 收缩到 124；工具
return code 为 0，输出没有截断。该 smoke 只证明工具闭环、指标和预算策略生效，不代表
真实 80B 模型的吞吐提升。

对应截图位于
`reports/Competition_Report_Finals/figures/agent_harness_smoke.png`。基础回归测试：

```bash
uv run --with pytest pytest -q tests/agent/test_edge_agent.py
```
