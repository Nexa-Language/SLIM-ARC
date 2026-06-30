# WSL2 网络栈 Bug 记录（未修复）

## 状态：🔴 未修复

## 发现日期
2026-06-30

## 问题描述

WSL2 内核 `6.18.35.2-microsoft-standard-WSL2` 的 TCP bind 系统调用出现严重异常：**所有指定端口的 bind() 都返回 EADDRINUSE，但 `/proc/net/tcp` 和 `ss` 都看不到端口被占用**。

## 症状

1. `python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 8080))"` → `EADDRINUSE`
2. 换任何端口（18080, 28080, 50000 等）都同样失败
3. `bind(0)`（随机端口）能成功
4. `/proc/net/tcp` 里没有 8080 端口的任何 socket
5. `ss -tlnp` 看不到 8080 监听
6. `dmesg` 显示 `WSL ERROR: CheckConnection: getaddrinfo() failed: -5`
7. Unix domain socket 能正常 bind

## 影响范围

- **llama-server 无法启动**：HTTP bind 端口时 abort（`munmap_chunk(): invalid pointer` 是 bind 失败后清理路径的堆 corruption）
- **Python http.server 无法启动**：同样 bind EADDRINUSE
- **Demo 系统（scripts/demo/）完全不可用**：无法录屏演示
- **6/29 能正常跑，6/30 突然不行**，代码和二进制未变

## 根因分析

这不是端口冲突（`/proc/net/tcp` 证明），是 **WSL2 内核的网络协议栈状态异常**。可能是：
- Windows 更新导致 WSL2 内核网络模块状态不一致
- WSL2 的 hyper-v 网络适配器残留状态
- glibc malloc 与 llama-server 全局对象析构的偶发性冲突（但 Python 也失败，排除此假设）

## 已尝试的修复（均无效）

1. ✗ 重启 WSL（`wsl --shutdown` + 重开）— 用户已执行，无效
2. ✗ 重启 Windows 电脑 — 用户已执行，无效
3. ✗ 重新编译 llama-server — 无效（不是二进制问题）
4. ✗ `SLIM_ARC_DISABLE=1` 禁用 SLIM-ARC patch — 无效（不是 patch 问题）
5. ✗ `MALLOC_CHECK_=3` 禁用 glibc 堆检查 — 无效
6. ✗ 换 IPv6 `::1` — 同样 EADDRINUSE
7. ✓ `bind(0)` 随机端口 — 能成功（workaround 基础）

## 建议修复方案（用户在 Windows 侧执行）

### 方案 A（首选）：重置 Winsock
在 Windows PowerShell（管理员）执行：
```powershell
wsl --shutdown
netsh winsock reset
netsh int ip reset
```
然后**重启电脑**。

### 方案 B：重置 WSL 网络
```powershell
wsl --shutdown
wsl --unregister Ubuntu  # ⚠️ 这会删除 WSL 数据，先备份！
# 然后从 Microsoft Store 重装 WSL
```

### 方案 C（临时 workaround）：用 bind(0) 随机端口
修改 demo 脚本，让所有服务 bind(0) 自动选端口，前端动态获取端口。但 llama-server 不支持端口 0，需要改用 llama-cli + Python SSE server 方案。

## 相关文件

- [`scripts/demo/`](scripts/demo/) — Demo 系统（受影响）
- [`logs/demo-*.log`](logs/) — 各种尝试的日志
- `src/llama-upstream/build/bin/llama-server` — 二进制本身正常（`--version` 能输出）
