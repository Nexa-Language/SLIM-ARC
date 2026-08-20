# start-demo.sh nohup 命令截断 bug 修复记录（nohup.out 问题）

- **日期**: 2026-08-13
- **文件**: [`scripts/demo/start-demo.sh`](../../scripts/demo/start-demo.sh)
- **修复类型**: SLIM-ARC FIX 2026-08-13（最小外科手术式，仅移动注释位置）

## 现象

运行 `scripts/demo/start-demo.sh 80b` 时出现此前未有的输出：

```
nohup: ignoring input and appending output to 'nohup.out'
```

## 根因分析 (Root Cause)

KV 参数化改动（2026-08-12）把两行 `#` 注释插到了 **nohup 多行命令的中间**（`--port 8080 \` 与 `-fa auto ... \` 之间），且注释行**不以 `\` 结尾**：

```bash
nohup ... \
    -m ... -c ... -np ... \
    --host 0.0.0.0 --port 8080 \      # ← 此行以 \ 结尾
    # SLIM-ARC FIX 2026-08-12: KV 量化参数化（...），   # ← 注释行，无续行符
    # 由...决定，默认 q4_0，f16 时用 f16。
    -fa auto -ctk ... \               # ← 被"弹出"为独立命令
    > "$PROJECT_ROOT/logs/demo-llama-server.log" 2>&1 &
```

**bash 规则**：`\` 续行先把换行符"吃掉"合并逻辑行；合并后行内的 `#` 开始注释**直到逻辑行尾**（即 131 行末尾）。后果：
1. 真正执行的 nohup 命令在 `#` 处被截断，只剩 `nohup llama-server ... --port 8080`
2. `-fa auto -ctk -ctv --no-repack --no-context-shift` 参数与 `> ... 2>&1` 重定向**全部丢失**
3. 第 133-134 行变成独立残缺命令 `-fa auto ... > log 2>&1 &`（`-fa` 非有效命令）
4. 真正运行的 llama-server **无重定向** → nohup 落入当前目录 `nohup.out` 并打印提示

### 影响

- 80B 以默认 KV 参数启动（KV 可能退回 f16 而非 q4_0），与 KV q4_0/F16 对照实验预期不符
- 日志不写入 `logs/demo-llama-server.log`，改写到 `nohup.out`
- `--no-repack`、`--no-context-shift` 失效

## 修复内容

将第 131-132 行注释**移到 nohup 命令之前**，恢复多行命令连续性：

```bash
# SLIM-ARC FIX 2026-08-12: KV 量化参数化（SLIM_ARC_KV_TYPE，实验用），
# 由上方导出的 $SLIM_ARC_KV_TYPE 决定，默认 q4_0，f16 时用 f16。
nohup "$LLAMA_DIR/build/bin/llama-server" \
    -m "$MODEL" -t "${MODEL_THREADS:-4}" -c "${SLIM_ARC_CTX:-$MODEL_CTX}" -np "${MODEL_PARALLEL:-1}" \
    --host 0.0.0.0 --port 8080 \
    -fa auto -ctk "${SLIM_ARC_KV_TYPE:-q4_0}" -ctv "${SLIM_ARC_KV_TYPE:-q4_0}" --no-repack --no-context-shift \
    > "$PROJECT_ROOT/logs/demo-llama-server.log" 2>&1 &
```

## 验证

- `bash -n start-demo.sh` → 通过
- 模拟 80b 分支实际生成的命令（完整 case 段 source 验证）：
  ```
  llama-server -m ".../Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf" -t 4 -c 16384 -np 1 \
      --host 0.0.0.0 --port 8080 -fa auto -ctk q4_0 -ctv q4_0 --no-repack --no-context-shift \
      > "$PROJECT_ROOT/logs/demo-llama-server.log" 2>&1
  ```
  ✓ 参数完整、重定向存在、无截断
- `MODEL_CTX=16384`（80b）正确传入 `-c`

## 备注

- 未改 llama.cpp 源码/patch/核心机制；仅调整 demo 脚本注释位置。
- 修复后重启 `bash scripts/demo/start-demo.sh 80b` 即恢复日志写入 `logs/demo-llama-server.log`，不再产生 `nohup.out`。
