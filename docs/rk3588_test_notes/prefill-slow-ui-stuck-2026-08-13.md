# 80B 长 context 下 prefill 极慢导致 UI 卡住诊断记录

- **日期**: 2026-08-13
- **现象**: UI 聊天窗口完全不动（几十秒到几分钟），但 monitor 面板 token 数持续增长
- **根因**: 80B 在 `-c 16384` 下 prefill 长 prompt（2482 token）极慢，期间无 SSE 输出

## 诊断证据

/slots 实测（2026-08-13 02:02 UTC）：
```
n_ctx: 16384
is_processing: true
n_prompt_tokens: 2482
n_prompt_tokens_processed: 18
n_decoded: 0
n_predicted: 0
```

- `n_prompt_tokens_processed: 18` / `n_prompt_tokens: 2482` → prefill 刚开始（18/2482 = 0.7%）
- `n_decoded: 0` → 还没生成任何 token，无 SSE 数据推送
- 80B prefill 速度 ~0.39 t/s → 2482 token prefill 需 ~6364s ≈ 106 分钟

## 根因链

1. 为支持 15000 token 长输出，把 `-c` 从 1024 → 16384
2. `-c 16384` 允许更长 prompt（聊天历史累积到 2482 token）
3. 80B 在大 context 下 prefill 极慢（pp 0.39 t/s），2482 token prefill 需 ~106 分钟
4. prefill 期间 llama-server **不推送 SSE 数据** → 前端 reader.read() 挂起 → UI 纹丝不动
5. monitor /slots 轮询独立工作 → 某些指标在变化 → 用户看到"token 数在增加"

## 之前为何没问题

- `-c 1024` 时 prompt 短（~几十 token），prefill 几秒完成
- `-c 16384` 后 prompt 长（2482 token），prefill 时间暴增

## 建议修复方向

1. **前端 prefill 进度提示**：在等待期间从 /slots 读取 n_prompt_tokens_processed/n_prompt_tokens 显示进度
2. **限制聊天历史长度**：前端只保留最近 N 轮对话，避免 prompt 无限累积
3. **用户侧**：刷新页面清空聊天历史，减少 prompt token 数
