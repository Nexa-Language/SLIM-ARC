# Edge Agent Harness 设计

SLIM-ARC 的主路径优化模型权重页和专家访问；Harness 位于其上层，用较少的无效 token 和较短的工具观测降低端侧 Agent 对推理运行时的额外压力。

## 数据流

1. 保持 `llama-server` 或等价 OpenAI-compatible 服务常驻，避免每轮工具调用重新加载权重。
2. 保留稳定 system prefix，只携带最近对话，并限制工具输出长度。
3. 模型严格输出 `{"tool":"shell","args":[...]}` 或 `{"final":"..."}`。
4. Harness 在固定工作目录执行允许的 argv，记录耗时并把有界 observation 送回模型。
5. 当观测到输出速度低于阈值时，后续轮次降低 `max_tokens`；达到步骤或总时间上限则终止。

## 边界

- 不使用 `shell=True`，拒绝非 allowlist 命令、绝对路径和 `..` 路径逃逸。
- 每次命令有独立超时和 stdout/stderr 字节上限。
- Harness 不管理模型生命周期，不自动下载模型，也不修改 SLIM-ARC 的内存策略。
- JSONL 指标不记录环境变量、认证头或模型回复以外的秘密信息。

## 取舍

常驻 HTTP endpoint 是性能路径；直接 `llama-cli` 兼容模式实现简单但会重复加载模型，只用于功能 smoke。完整 MCP、多 Agent 编排和任意 shell 权限不属于当前比赛版本。当前实现只保留端侧推理最需要的短上下文、慢输出预算、受限工具和可观测闭环。

## 当前证据

确定性本地 smoke 已完成 `model -> uname -m -> observation -> final`。首轮估算输出
速度为 1.999 t/s，下一轮 `max_tokens` 按 0.65 系数由 192 降至 124；工具执行成功且
输出未截断。该结果验证策略执行，不用于宣称真实模型 TPS 或端到端延迟收益。10 个单元
测试覆盖上下文裁剪、预算调整、命令与路径拒绝、输出截断和 fake model 闭环。
