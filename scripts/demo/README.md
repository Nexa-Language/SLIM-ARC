# SLIM-ARC Live Demo 操作指南

## 概述

这是一个 Web 演示系统，展示 SLIM-ARC 优化后的端侧 MoE 大模型推理。左侧聊天界面流式输出，右侧实时监控面板展示内存用量、推理速度、MoE 专家激活和优化链状态。

**核心展示点**：80B MoE 模型（38GB）在 32GB RAM 上通过 mmap + MADV_RANDOM 按需加载流畅运行——这正是 SLIM-ARC 的核心卖点。

## 架构

三个服务协同工作：

| 服务 | 端口 | 作用 |
|------|------|------|
| llama-server | 8080 | llama.cpp 自带 HTTP server，提供 `/v1/chat/completions` 流式接口 |
| monitor.py | 8001 | FastAPI 监控后端，读 `/proc/meminfo` + llama-server `/slots` |
| 前端 http | 8090 | 静态服务 `index.html` |

## 起环境

### 前置条件

- `src/llama-upstream/build/bin/llama-server` 已编译（已满足）
- 模型文件在 `data/models/`（已满足）
- Python 3.10+ + fastapi + uvicorn + requests（已满足）

### 一键启动

```bash
# 4B 模型（快速，2.4GB，适合演示 UI 流畅度）
bash scripts/demo/start-demo.sh 4b

# 80B 模型（震撼，38GB，展示 SLIM-ARC 核心卖点）
bash scripts/demo/start-demo.sh 80b
```

启动脚本会：
1. 启动 llama-server（8080）
2. 启动 monitor.py（8001）
3. 等待服务就绪
4. 尝试自动打开浏览器

**80B 首次加载需要 30-60 秒**（mmap 38GB 模型文件）。日志在 `logs/demo-llama-server.log`。

### 手动启动（分步）

```bash
# 1. 启动 llama-server（4B）
src/llama-upstream/build/bin/llama-server \
    -m data/models/Qwen3-4B-Q4_K_M.gguf \
    -t 8 -c 8192 --host 0.0.0.0 --port 8080 \
    -fa auto -ctk q4_0 -ctv q4_0 --no-repack --no-context-shift

# 2. 启动 monitor（另开终端）
SLIM_ARC_MODEL="Qwen3-4B-Q4_K_M" SLIM_ARC_MODEL_SIZE="2.4 GB" \
SLIM_ARC_MADV=ON SLIM_ARC_KV_TYPE=q4_0 SLIM_ARC_FA=ON SLIM_ARC_REPACK=OFF \
SLIM_ARC_TIER="32GB warm" \
python3 scripts/demo/monitor.py

# 3. 启动前端 http（另开终端）
cd scripts/demo && python3 -m http.server 8090
```

### 切换模型

**不需要热切换**，直接停旧服务启新的：

```bash
# 停所有服务
ps aux | grep -E "llama-server|monitor.py|http.server" | grep -v grep | awk '{print $2}' | xargs -r kill

# 启 80B
bash scripts/demo/start-demo.sh 80b
```

前端会自动显示新模型名和大小（通过 monitor 的 config 传递）。

## 录制视频

### 打开前端

浏览器访问：`http://127.0.0.1:8090/index.html`

### 录制脚本（建议 2-3 分钟）

**场景 1：80B 主演示（推荐）**

1. **开场（10s）**：展示 Web 界面，标题"SLIM-ARC Live Demo"，顶栏显示 `Qwen3-Next-80B-IQ4_XS (38 GB)`
2. **冷启动推理（40s）**：输入"什么是 MoE 架构？"，观察：
   - 左侧流式逐字输出
   - 右侧内存 cache 从 28GB 升到 30GB+（权重按需加载进 page cache）
   - t/s 折线图实时跳动
   - 专家激活显示 10/512（稀疏率 98%）
3. **热缓存二次推理（20s）**：再问一个问题（如"解释 attention 机制"），速度明显更快（热缓存 5+ t/s）
4. **收尾（10s）**：展示优化链 5 项全 ✓，说"64.5× 加速"

**场景 2：4B 快速演示（备选）**

如果 80B 太慢或不稳定，用 4B：
1. `bash scripts/demo/start-demo.sh 4b`
2. 输入问题，流式输出 16 t/s，监控面板正常
3. 适合强调"UI 流畅"而非"大模型"

### 录制技巧

- **OBS Studio / Kazam / WSL 录屏**均可
- **分辨率**：1440×900 或 1920×1080
- **预热**：录制前先跑一次 prompt 让 80B 权重进 cache，正式录制时是热缓存状态
- **鼠标引导**：录制时用鼠标指向监控面板的关键数据（cache 内存、t/s、专家数）

## 展示要点

向评委讲解时重点强调：

1. **"38GB 模型跑在 32GB RAM 上"**：指着顶栏 badge 和右侧"Cache 28GB"，说明 mmap 让模型文件按需加载到 page cache，不需要全部装进物理内存

2. **"10/512 专家激活"**：指着专家激活面板，说明 MoE 稀疏性——每个 token 只激活 2% 的专家，MADV_RANDOM 让 page fault 只加载这 2% 的权重

3. **"流式输出"**：左侧逐字显示，说明推理速度足够支持交互

4. **"优化链协同"**：指着优化链 5 项，说明 A（内核协同释放内存）→ B（量化压缩降低需求）→ C（计算融合加速）的级联效应

## 停止服务

```bash
ps aux | grep -E "llama-server|monitor.py|http.server" | grep -v grep | awk '{print $2}' | xargs -r kill
```

或用 start-demo.sh 的前台模式，Ctrl+C 停止。

## 故障排查

| 问题 | 解决 |
|------|------|
| 前端打不开 | 确认 8090 端口：`ss -tlnp \| grep 8090` |
| 聊天报错"连接失败" | 确认 llama-server：`curl http://127.0.0.1:8080/health` |
| 监控面板全 0 | 确认 monitor：`curl http://127.0.0.1:8001/api/health` |
| 80B 推理卡住 | 冷启动正常（page fault 加载权重），等 30-60 秒；第二次会快 |
| t/s 显示 0 | monitor 读 /slots，推理完成后 n_decoded 停止增长，t/s 会归零（正常） |

## 文件清单

| 文件 | 作用 |
|------|------|
| `scripts/demo/index.html` | 前端单页（聊天 + 监控面板） |
| `scripts/demo/monitor.py` | 监控后端（FastAPI） |
| `scripts/demo/start-demo.sh` | 一键启动脚本 |
| `plan/19-v1-demo-video.md` | 完整录屏方案设计 |
