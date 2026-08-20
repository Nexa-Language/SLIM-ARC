# UI 热切换 80B 进程被误杀修复记录

- **日期**: 2026-08-12
- **文件**: [`scripts/demo/monitor.py`](../../scripts/demo/monitor.py)
- **修复类型**: SLIM-ARC FIX 2026-08-12（最小外科手术式，仅改 monitor.py，不动 llama.cpp / 核心机制）

## 现象

- 终端直接 `scripts/demo/start-demo.sh 80b` 启动 80B：**正常跑通**（llama-server 日志显示 2.44 t/s 推理）。
- 通过 UI 顶栏按钮热切换 4B -> 80B：llama-server 进程启动后**立即退出**（monitor 日志/`ps` 显示 `<defunct>` 僵尸进程 PID 4072）。

## 根因分析 (Root Cause)

- UI 热切换由 [`monitor.py`](../../scripts/demo/monitor.py) 的 `do_switch()` 执行：`pkill` 旧进程 -> `Popen` 新 llama-server -> `_wait_llama_ready()` 轮询就绪。
- `_wait_llama_ready()` 扫描新增日志，若命中 `_LLAMA_FAIL_KEYWORDS` 即 `proc.kill()` 并判定失败。
- `_LLAMA_FAIL_KEYWORDS` 原含 `"failed to fit params"`。
- 80B（46GB）加载到 7.8GB 设备时，llama.cpp 会打印：
  `common_fit_params: failed to fit params to free device memory: ... abort`
- **关键事实**：该日志只是 **WRN 警告，不是致命错误**。llama.cpp 的 [`common.cpp`](../../src/llama-upstream/common/common.cpp) 调用 `common_fit_params()` 后**不检查返回值**，模型仍会通过 mmap+MADV_RANDOM 按需加载继续启动（这正是 SLIM-ARC 的核心机制，也是终端直接启动能跑通的原因）。
- 因此 `_wait_llama_ready` 在 3 秒轮询到该警告时误判为启动失败，`kill()` 杀掉了正在正常 mmap 加载的 llama-server 进程。

### 日志证据（demo-llama-server.log 尾部）

```
0.00.028.092 I srv load_model: loading model '.../Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf'
0.00.932.414 W common_fit_params: failed to fit params to free device memory: ... abort   <- 仅警告
0.01.358.736 W load: control-looking token ...                                          <- 仍在继续加载
```

## 修复内容（最小改动）

1. 将 `"failed to fit params"` 从 `_LLAMA_FAIL_KEYWORDS` **移除**（不再作为快速失败/杀进程关键字）。
2. 在 `_wait_llama_ready()` 中对该关键字**单独检测**：仅打印告警日志，**不 kill**，继续轮询等待就绪。
3. 兜底机制保持不变：若 80B 真因内存不足 OOM 进程退出，`proc.poll()` 会检测到并返回 False（UI 仍会显示失败提示，不会无限等待）。

```python
# _LLAMA_FAIL_KEYWORDS 移除了 "failed to fit params"
if "failed to fit params" in new_log.lower():
    print("[SLIM-ARC] llama.cpp 报告 'failed to fit params'（非致命警告，模型仍通过 mmap 加载中），继续等待就绪...", flush=True)
```

## 验证

- `python3 -m py_compile monitor.py` 通过。
- 逻辑：fit 警告不再触发 kill；80B 可继续 mmap 加载直至 `/health` 返回 200。

## 备注

- 未修改 llama.cpp / SLIM-ARC 核心机制（红线规则：只做 bug 修复、最小外科手术式改动）。
- 全部改动已标注 `// SLIM-ARC FIX 2026-08-12`。
