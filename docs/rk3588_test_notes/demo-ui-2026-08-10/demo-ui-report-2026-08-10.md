# SLIM-ARC 监视 UI 启动报告（2026-08-10）

## 1. 概述

本次任务目标：在 `/home/orangepi/SLIM-ARC` 中成功启动 SLIM-ARC 监视 UI
（`scripts/demo/` Web 演示系统），全程留痕，最小改动修复启动问题。

**最终结果：✅ 三服务全部成功启动，健康检查全部通过，端到端推理验证通过。**

使用模型：**Qwen3-4B-Q4_K_M.gguf（4B）**（80B 模型文件缺失且磁盘空间不足，详见第 6 节）。

## 2. 启动步骤

1. **环境预检**（详见 [`precheck.txt`](precheck.txt)）：
   - 发现 `src/llama-upstream` 为独立 git clone，位于 `/home/orangepi/src/llama-upstream`
     （非 SLIM-ARC 仓库内）
   - `build/bin/` 缺 llama-server 可执行文件
   - Python 依赖（fastapi/uvicorn/requests）缺失
2. **补齐环境**：
   - `cmake --build build --target llama-server -j$(nproc)` → 生成 llama-server
   - `python3 -m pip install fastapi uvicorn requests`
3. **最小修复脚本路径 bug**（详见 [`fix-record.md`](fix-record.md)）：
   - `start-demo.sh`：LLAMA_DIR 自动探测两种布局
   - `llama_cli_server.py`：LLAMA_CLI 自动探测两种布局（备用方案同步修复）
4. **一键启动**：`bash scripts/demo/start-demo.sh 4b`
   - 首次（timeout 前台验证）：三服务全部就绪 ✓✓✓
   - 二次（nohup 后台持久运行）：llama-server / monitor / 前端全部就绪
5. **健康检查 + 推理验证**（见第 4 节）。

启动日志：
- [`startup-log-1.txt`](startup-log-1.txt)（首次前台验证，timeout 后 trap 清理）
- [`startup-log-2.txt`](startup-log-2.txt)（后台持久运行）

## 3. 三服务状态（端口 / PID）

| 服务 | 端口 | PID | 进程 | 状态 |
|------|------|-----|------|------|
| llama-server | 8080 | 69203 | `/home/orangepi/src/llama-upstream/build/bin/llama-server -m .../Qwen3-4B-Q4_K_M.gguf -t 8 -c 8192 --host 0.0.0.0 --port 8080 -fa auto -ctk q4_0 -ctv q4_0 --no-repack --no-context-shift` | ✅ LISTEN |
| monitor.py | 8001 | 69204 | `python3 /home/orangepi/SLIM-ARC/scripts/demo/monitor.py` | ✅ LISTEN |
| 前端 http | 8090 | 69205 | `python3 -m http.server 8090 --directory /home/orangepi/SLIM-ARC/scripts/demo` | ✅ LISTEN |

监控后端配置（经 monitor /api/health 回显确认）：
```
model: Qwen3-4B-Q4_K_M | size: 2.4 GB | madv: ON | kv_type: q4_0 | fa: ON | repack: OFF | tier: 32GB warm
```

## 4. 健康检查结果

（完整输出见 [`verification-healthcheck.txt`](verification-healthcheck.txt)）

| 检查项 | 命令 | 结果 |
|--------|------|------|
| llama-server | `curl http://127.0.0.1:8080/health` | `{"status":"ok"}` HTTP 200 |
| monitor | `curl http://127.0.0.1:8001/api/health` | `{"status":"ok","config":{...}}` HTTP 200 |
| 前端 | `curl http://127.0.0.1:8090/index.html` | HTTP 200, 21767 bytes |

**端到端推理验证**：
- 流式 `/v1/chat/completions`：SSE 逐 token 输出正常（含 reasoning_content 流）
- 非流式：HTTP 200，`predicted_per_second: 6.45 t/s`
- monitor `/api/monitor`：成功读取 llama-server `/slots`
  `{"n_decoded":20,"n_prompt_tokens":28,"active":true,"slots":4}`，tps_history 正常记录

**浏览器访问**：`http://127.0.0.1:8090/index.html` 返回 HTTP 200（本环境无 GUI，
无法实际打开浏览器，以 HTTP 200 作为可访问确认）。

## 5. 遇到的问题与修复（root-cause）

| # | 问题 | 根因 | 修复 | 详见 |
|---|------|------|------|------|
| 1 | llama-server 二进制缺失 | build 未链接主程序 target（impl 库已有） | `cmake --build build --target llama-server` | [`root-cause-01-path-and-binary.md`](root-cause-01-path-and-binary.md) |
| 2 | start-demo.sh 启动失败 `No such file or directory` | `LLAMA_DIR` 硬编码 `$PROJECT_ROOT/src/llama-upstream`，实际独立 clone 在 `$HOME/src/` 下 | 自动探测两种布局（SLIM-ARC FIX 标注） | 同上 + fix-record |
| 3 | 备用方案 llama_cli_server.py 路径错误 | 同上路径 bug | 同步修复 LLAMA_CLI 探测 | fix-record |
| 4 | Python 依赖缺失 | fastapi/uvicorn/requests 未安装 | `pip install fastapi uvicorn requests` | fix-record |

## 6. 环境限制说明

- **80B 模型不可用**：`data/models/` 下无 `Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf`，
  且本机根分区 28G 仅剩 17G 可用，38GB 模型无法下载/放置。
  因此本环境无法演示 80B 场景，UI 以 4B 模型完整跑通。
- **内置 Web UI assets 缺失**：构建时 huggingface 下载失败（离线环境），仅影响
  llama-server 自带 Web UI，不影响本 demo 的 HTTP 接口（8080/8001/8090 全部正常）。
- 本环境为 8GB RAM 的 RK3588（aarch64），4B 模型推理约 6.45 t/s。

## 7. 改动清单

代码改动（均含 `SLIM-ARC FIX 2026-08-10` 标注，最小外科手术式，未改核心机制）：
- [`scripts/demo/start-demo.sh`](../../scripts/demo/start-demo.sh:12) — LLAMA_DIR 自动探测两种布局
- [`scripts/demo/llama_cli_server.py`](../../scripts/demo/llama_cli_server.py:35) — LLAMA_CLI 自动探测两种布局

环境补齐（非代码改动）：
- 构建 llama-server 二进制
- pip 安装 fastapi/uvicorn/requests

详见 [`fix-record.md`](fix-record.md)。

## 8. 如何访问与停止

**访问**：浏览器打开 `http://127.0.0.1:8090/index.html`
（本机 IP 192.168.137.74，局域网可访问 `http://192.168.137.74:8090/index.html`）

**停止服务**：
```bash
ps aux | grep -E "llama-server|monitor.py|http.server" | grep -v grep | awk '{print $2}' | xargs -r kill
```

**重新启动**：
```bash
cd /home/orangepi/SLIM-ARC
bash scripts/demo/start-demo.sh 4b
```

## 9. 留痕文件列表（docs/rk3588_test_notes/demo-ui-2026-08-10/）

| 文件 | 内容 |
|------|------|
| `precheck.txt` | 环境预检记录 |
| `startup-log-1.txt` | 首次启动（前台验证）日志 |
| `startup-log-2.txt` | 后台持久启动日志 |
| `root-cause-01-path-and-binary.md` | 根因分析 |
| `fix-record.md` | 改动内容记录 |
| `verification-healthcheck.txt` | 健康检查 + 推理验证输出 |
| `demo-ui-report-2026-08-10.md` | 本最终报告 |
