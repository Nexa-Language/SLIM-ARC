# 录屏演示方案计划 v1

## 目标
录制一段视频，演示 SLIM-ARC 系统让 80B MoE 大模型在受限内存环境下流畅运行的真实效果。要求视觉冲击力强、能看出"流式产生"、体现核心技术点。

## 方案对比

### 方案 A：纯命令行演示
- 直接跑 `llama-cli` 流式输出文本，录终端
- **优点**：零开发成本，真实
- **缺点**：视觉普通，评委看不懂技术细节，流式效果不够"精美"

### 方案 B：精美 Web 前端 + 后端流式代理（推荐）
- 做一个 ChatGPT 风格的 Web 界面，用户输入 prompt，后端调用 `llama-cli --prompt` 流式返回
- **优点**：视觉精美，流式逐字输出效果震撼，能同时展示内存监控（cgroup 用量）、MADV 状态等
- **缺点**：需要开发，后端需要流式 SSE/WebSocket

### 方案 C：混合（推荐升级版）
- Web 前端 + 左侧聊天流式输出 + 右侧实时监控面板（RAM/活跃专家数/tokens/s）
- 一屏同时展示"流畅推理"和"OS 机制"

## 推荐：方案 C（混合演示页）

### 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  SLIM-ARC Live Demo          [80B IQ4_XS] [32GB warm]  │
├──────────────────────┬──────────────────────────────────┤
│                      │  📊 实时监控                       │
│  💬 Chat             │  ┌────────────────────────────┐  │
│  ┌────────────────┐  │  │ RAM: 12.3/16 GB ████████  │  │
│  │ User: 用 3 句  │  │  │ CPU: 8 cores ████████████ │  │
│  │ 话介绍 SLIM-ARC│  │  │ t/s: 5.16 ▁▂▄▆▇█▇▆▄▂    │  │
│  └────────────────┘  │  │ Active experts: 10/512    │  │
│                      │  │ KV cache: q4_0 ✓          │  │
│  🤖 Assistant:       │  │ MADV_RANDOM: ON ✓         │  │
│  ┌────────────────┐  │  └────────────────────────────┘  │
│  │ SLIM-ARC 是...│  │                                  │
│  │ 一个面向端侧  │  │  ⚙️ 优化链                       │
│  │ Agent 的内存感│  │  A. MADV_RANDOM ✓               │
│  │ 知推理优化框  │  │  B. IQ4_XS + KV q4_0 ✓          │
│  │ 架▏            │  │  C. FlashAttention ✓            │
│  └────────────────┘  │                                  │
│  [输入框] [发送]     │                                  │
└──────────────────────┴──────────────────────────────────┘
```

### 技术实现

**前端**（单页 HTML，复用 site/css/style.css 风格）：
- 聊天区：用户输入 + assistant 流式逐字显示
- 监控面板：进度条 + 折线图（用 Chart.js 或纯 CSS）
- 优化链 checklist：带动画的勾选

**后端**（Python FastAPI 或 Node Express）：
- `POST /api/chat` 接收 prompt
- 启动 `llama-cli -m <model> --prompt <prompt> -t 8 -n 256 --predict-2 --no-conversation` 子进程
- 解析 stdout，逐 token 通过 SSE（Server-Sent Events）推给前端
- 同时读取 `/proc/meminfo` 和 cgroup `memory.current`，通过 SSE 推送监控数据

**模型选择**（权衡速度与效果）：
- 首选 `Qwen3-4B-Q4_K_M`（2.4GB，快，热缓存秒级响应，适合演示）
- 备选 `Qwen3-Next-80B-IQ4_XS`（40GB，32GB 热缓存 5.16 t/s，震撼但慢）
- 建议：先用 4B 快速演示 UI 流畅度，再切 80B 展示"大模型真能跑"

### 录制脚本（建议 2-3 分钟）

1. **开场（10s）**：展示 Web 界面，标题"SLIM-ARC Live Demo"
2. **4B 快速演示（30s）**：输入"用 3 句话介绍 SLIM-ARC"，流式输出，监控面板实时跳动
3. **切 80B（60s）**：切换模型到 80B IQ4_XS，输入复杂问题（如"解释 MoE 架构"），流式输出，监控显示 10/512 专家激活、MADV_RANDOM ON
4. **对比 baseline（30s）**：一键切换"关闭 SLIM-ARC"（SLIM_ARC_DISABLE=1），同样 prompt 卡顿/OOM
5. **收尾（10s）**：显示"64.5× 加速"数据卡片

## 步骤拆解

1. [ ] 确认 `src/llama-upstream/build/bin/llama-cli` 存在且可运行
2. [ ] 确认模型文件存在（4B + 80B）
3. [ ] 开发后端 `scripts/demo/server.py`（FastAPI + SSE）
4. [ ] 开发前端 `scripts/demo/index.html`（聊天 + 监控面板）
5. [ ] 测试流式输出 + 监控数据
6. [ ] 录制视频

## 前置条件

- `llama-cli` 可执行（build 产物）
- 至少 Qwen3-4B 模型可用（80B 可选，40GB 磁盘）
- Python 3.10+ + fastapi + uvicorn
- 浏览器

## 风险

1. **80B 冷启动慢**：首次加载 40GB 模型需 1-2 分钟。对策：提前 warm up（先跑一次预热），录制时用热缓存
2. **流式解析 llama-cli stdout**：llama-cli 默认带 ANSI 转义和进度条。对策：用 `--no-display-prompt --simple-console` 或 `-log-disable`
3. **监控数据频率**：meminfo 读取太快会影响性能。对策：100ms 间隔，单独线程
4. **cgroup 权限**：cgexec 需要 sudo。对策：演示用非 cgroup 模式（32GB 全内存），强调"热缓存流畅运行"

## 简化备选

如果时间紧，方案 B 简化版：
- 只做聊天界面（无监控面板）
- 只用 4B 模型
- 后端用 `llama-server`（llama.cpp 自带 HTTP server），前端直接 fetch
- 1 小时内可完成
