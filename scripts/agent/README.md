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
