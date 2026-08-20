# SLIM-ARC 监视 UI（demo-ui）多轮修复整合总结

- **日期**: 2026-08-10
- **整合范围**: 以下 5 个留痕目录的全部关键文档
  1. `docs/rk3588_test_notes/demo-ui-2026-08-10/`（首轮启动）
  2. `docs/rk3588_test_notes/demo-ui-debug-2026-08-10/`（"无法持续生成"排查）
  3. `docs/rk3588_test_notes/demo-ui-analysis-2026-08-10/`（两 bug 纯分析报告）
  4. `docs/rk3588_test_notes/demo-ui-scrollfix-2026-08-10/`（滚动修复第一轮）
  5. `docs/rk3588_test_notes/demo-ui-scrollfix-r2-2026-08-10/`（滚动修复第二轮）
- **本整合过程遵守 red-line**: 未新增/修改任何功能代码，仅整合文档 + git 操作。
- **行号来源**: 本文档所有行号均以**当前实际代码**（`scripts/demo/index.html` 541 行、`start-demo.sh` 178 行、`llama_cli_server.py` 202 行）为准，并经 `git diff` 逐一核实，非臆造。

---

## 一、监视 UI 概述

`scripts/demo/` 下的 Web 演示/监控系统（SLIM-ARC Live Demo），由 3 个服务组成，由 `scripts/demo/start-demo.sh` 一键启动：

| 服务 | 端口 | 组件 | 说明 |
|------|------|------|------|
| llama-server | 8080 | `/home/orangepi/src/llama-upstream/build/bin/llama-server` | 推理后端（HTTP + SSE 流式） |
| monitor.py | 8001 | `scripts/demo/monitor.py` | 监控后端（/api/health、/api/monitor） |
| 前端 | 8090 | `python3 -m http.server 8090 --directory scripts/demo` | 静态 Web UI（index.html） |

**访问地址**: 本机 `http://127.0.0.1:8090/index.html`；局域网 `http://192.168.137.74:8090/index.html`。

**当前运行状态**: 三服务全部启动成功、健康检查通过、端到端推理验证通过（详见 [`demo-ui-report-2026-08-10.md`](demo-ui-2026-08-10/demo-ui-report-2026-08-10.md)）。本环境因 80B 模型缺失 + 磁盘不足（28G 仅剩 17G），以 4B 模型（Qwen3-4B-Q4_K_M.gguf）完整跑通链路。

**界面结构**:
- 左栏 `.chat`（flex column）→ 内部滚动容器 `.chat-messages#messages`（`flex:1; overflow-y:auto; min-height:0`）+ `.chat-input` 输入框
- 右栏 `.monitor#monitor`（自带 `overflow-y:auto`）→ 系统内存 / 推理速度 tps-chart / **MoE 专家激活 `#experts`** / SLIM-ARC 优化链

---

## 二、修改总结表（核心）

本次整合共确认 **10 处实际代码改动**，分布在 3 个文件，均含 `SLIM-ARC FIX 2026-08-10` 标注。以下行号经 `git diff` 核实为当前实际位置。

### 2.1 `scripts/demo/index.html`（8 处，541 行）

| # | 文件 | 位置(行/函数) | 修改内容(前 → 后) | SLIM-ARC FIX 标注 | 验证结论 |
|---|------|--------------|-------------------|------------------|---------|
| 1 | scripts/demo/index.html | :59 `.main` CSS | 无 `grid-template-rows`（默认 auto）→ 追加 `grid-template-rows: minmax(0, 1fr)` | `/* SLIM-ARC FIX 2026-08-10: 默认 auto 行会被 .chat 内容撑高… */` | ✅ r2 FIX-B，curl 200、md5 变化、grep 命中 |
| 2 | scripts/demo/index.html | :68 `.chat` CSS | `display:flex; flex-direction:column` → 追加 `min-height: 0` | `/* SLIM-ARC FIX 2026-08-10: grid item(.chat) 默认自动最小尺寸… */` | ✅ r2 FIX-A，curl 200、md5 变化、grep 命中 |
| 3 | scripts/demo/index.html | :77 `.chat-messages` CSS | `flex:1; overflow-y:auto; padding:24px` → 追加 `min-height: 0` | `/* SLIM-ARC FIX 2026-08-10: flexbox 子项默认 min-height:auto 阻止 overflow-y 生效 */` | ✅ 首轮滚动修复改动1，curl 200、md5 变化、grep 命中 |
| 4 | scripts/demo/index.html | :471 `send()` 系统提示 | `…请简洁友好地回答用户问题，控制在 80 字以内。` → `…请友好地回答用户问题。`（移除 80 字限制） | `// SLIM-ARC FIX 2026-08-10: 移除"控制在 80 字以内"限制，该提示导致模型拒绝长输出` | ✅ 输出长度 96→918 字（约 9.6 倍） |
| 5 | scripts/demo/index.html | :477-478 `send()` max_tokens | `max_tokens: 200` → `max_tokens: 512` | `// SLIM-ARC FIX 2026-08-10: max_tokens 从 200 提升到 512，200 太低导致输出被截断` | ✅ finish_reason "length"→"stop"，完整长输出 |
| 6 | scripts/demo/index.html | :483-491 `send()` 错误处理 | 无 r.ok 检查（静默失败）→ 新增 `if (!r.ok) {…显示 HTTP 错误…}` | `// SLIM-ARC FIX 2026-08-10: 添加 HTTP 状态检查，非 200 时显示错误而非静默失败` | ✅ 错误可见，利于排查 |
| 7 | scripts/demo/index.html | :512-515 `send()` 流式 auto-scroll | `messages.scrollTop = messages.scrollHeight;`（每 token 无条件）→ `if (messages.scrollTop + messages.clientHeight >= messages.scrollHeight - 50) { … }`（底部容差触发） | `// SLIM-ARC FIX 2026-08-10: 仅当用户已在底部附近时才自动滚动，避免阻止回看历史` | ✅ 首轮滚动修复改动2，curl 200、md5 变化、grep 命中 |
| 8 | scripts/demo/index.html | :530-532 `escapeHtml()` 函数 | `s.replace(/&/g,'&').replace(/</g,'<')…`（空操作，未转义）→ `s.replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>')…` | `// SLIM-ARC FIX 2026-08-10: 修复 HTML 转义，原代码替换值为空操作（&→& 等），导致 < > 被当作 HTML 标签解析` | ✅ `<`/`>` 不再被 innerHTML 解析为标签 |

### 2.2 `scripts/demo/start-demo.sh`（1 处，178 行）

| # | 文件 | 位置(行/函数) | 修改内容(前 → 后) | SLIM-ARC FIX 标注 | 验证结论 |
|---|------|--------------|-------------------|------------------|---------|
| 9 | scripts/demo/start-demo.sh | :12-17 脚本头 `LLAMA_DIR` 定义 | 硬编码 `LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"` → 追加自动探测：若标准路径无 llama-server 且仓库外独立 clone 存在则回退到 `$(dirname PROJECT_ROOT)/src/llama-upstream` | `# SLIM-ARC FIX 2026-08-10: llama-upstream 是独立 git clone，实际位于仓库外…自动探测两种布局` | ✅ 消除 `No such file or directory`，三服务成功启动 |

### 2.3 `scripts/demo/llama_cli_server.py`（1 处，202 行）

| # | 文件 | 位置(行/函数) | 修改内容(前 → 后) | SLIM-ARC FIX 标注 | 验证结论 |
|---|------|--------------|-------------------|------------------|---------|
| 10 | scripts/demo/llama_cli_server.py | :36-40 模块级 `LLAMA_CLI` 定义 | 硬编码 `LLAMA_CLI = PROJECT_ROOT / "src/llama-upstream/build/bin/llama-cli"` → 追加 `if not LLAMA_CLI.exists():` 回退到 `PROJECT_ROOT.parent / "src/llama-upstream/..."` | `# SLIM-ARC FIX 2026-08-10: llama-upstream 是独立 git clone，实际位于仓库外…自动探测两种布局` | ✅ 备用方案（WSL2 bind 回退）本环境可用，py_compile 通过 |

**git diff 汇总**: `31 insertions(+), 4 deletions(-)`，3 文件（index.html 8 处、start-demo.sh 1 处、llama_cli_server.py 1 处），与上表完全一致。

---

## 三、各轮排查纪要

### 第 1 轮 — 启动（demo-ui-2026-08-10）
- **问题**: `start-demo.sh` 启动失败 `nohup: failed to run command '.../llama-server': No such file or directory`；llama-server 二进制缺失；Python 依赖缺失。
- **根因**:
  - `src/llama-upstream` 是独立 git clone，实际位于 `/home/orangepi/src/llama-upstream`（`.gitignore` 忽略），脚本硬编码 `$PROJECT_ROOT/src/llama-upstream` 指向不存在的路径（路径探测 bug）。
  - `build/bin/` 缺 llama-server 可执行文件（CMakeCache 已开 `LLAMA_BUILD_SERVER=ON`，但主程序 target 未构建）。
  - fastapi/uvicorn/requests 未安装。
- **修复**: ① `start-demo.sh` LLAMA_DIR 自动探测；② `llama_cli_server.py` LLAMA_CLI 自动探测（同步）；③ `cmake --build build --target llama-server`；④ `pip install fastapi uvicorn requests`。
- **结论**: 三服务全部启动、健康检查通过、端到端推理验证通过（4B 模型）。

### 第 2 轮 — "无法持续生成"（demo-ui-debug-2026-08-10）
- **问题**: 聊天界面输出一段就停止，不能持续生成完整回答；强制固定字数时输出"可能内存不足或模型加载问题…"。
- **根因**（前端参数问题，后端完全正常）:
  - 主因: 系统提示"控制在 80 字以内"使模型主动拒绝长输出（96 字, finish_reason="stop"）。
  - 次因: `max_tokens=200` 过低，无字数限制时 378 字即被截断（finish_reason="length"）。
  - 潜在: `escapeHtml()` 替换值为空操作（`&→&`），未实际转义 HTML 实体，`<`/`>` 会被 innerHTML 解析。
  - 另发现: 缺少 `r.ok` 检查，HTTP 错误时静默失败。
- **修复**: 移除 80 字限制、max_tokens 200→512、加 r.ok 检查、修复 escapeHtml（改 4 处）。
- **结论**: 输出长度 96→918 字（约 9.6 倍），finish_reason 均为 "stop"，完整长输出。

### 第 3 轮 — 两 bug 纯分析（demo-ui-analysis-2026-08-10）
- **性质**: Architect 模式**纯分析与规划，未修改任何代码**。
- **Bug1（滚动）**: 分析根因=flexbox `min-height:auto` 使 `.chat-messages` 的 `overflow-y:auto` 不激活 + 流式每 token 无条件滚底阻止回看。给出修改点 1（`.chat-messages` 加 min-height:0）与修改点 2（auto-scroll 容差）。
- **Bug2（MoE 可视化）**: 三层数据链路断裂（前端 Math.random 假数据 → monitor 只传静态数量 → 核心 C++ 统计无 HTTP 出口）。建议方案 1（前端确定性展示，合规）可行；方案 2/3（核心新增 HTTP 端点 / 周期性 dump）**违反 red-line #1，仅作分析记录，不可实施**。
- **结论**: 后续滚动修复据此执行；MoE 真实数据展示因红线约束未实施。

### 第 4 轮 — 滚动修复第一轮（demo-ui-scrollfix-2026-08-10）
- **问题**: 左侧聊天窗口消息变多后无法上下滚动；流式生成期间无法回看历史。
- **根因**: 主因=`.chat-messages` 缺 `min-height:0`（flexbox 子项默认 `min-height:auto` 阻止 overflow 生效）；次因=流式每 token 无条件 `scrollTop=scrollHeight`。
- **修复**: 改动1=`.chat-messages` 加 `min-height:0`（行 77）；改动2=流式 auto-scroll 改 50px 底部容差（行 512-515）；行 460（现 462）发送时滚动保留。
- **验证**: 命令级全部通过（grep/md5/curl）；无头浏览器不可用，真实渲染需人工确认；MoE 区域零改动（diff 证据）。
- **遗留**: 用户实测左栏**仍无法滚动**，提示问题层级更深 → 进入 r2。

### 第 5 轮 — 滚动修复第二轮 r2（demo-ui-scrollfix-r2-2026-08-10）
- **问题**: 上一轮已给 `.chat-messages` 加 `min-height:0`（位置正确、保留），但左栏仍不可滚；右栏 `.monitor` 本就可独立滚动（"只影响右栏"是现象误读）。
- **根因（真实）**: 问题层级在外层 grid：
  1. `.main` 未定义 `grid-template-rows`（默认 auto）→ 行高由内容决定，消息变多时行被撑高，溢出被 `body{overflow:hidden}` 裁剪；
  2. `.chat`（grid item）`overflow:visible` 且无 `min-height` → 自动最小尺寸=内容 min-content，不收缩；
  3. 结果 `.chat-messages` 高度被撑到容纳全部消息 → `overflow-y:auto` 永不触发。
  - **上一轮为何无效**: 只处理了 flex 子项 `.chat-messages`，未解除外层 grid item `.chat` 的自动最小尺寸与 `.main` 行高 auto——层级不够深。
- **修复**: FIX-A=`.chat` 加 `min-height:0`（行 68）；FIX-B=`.main` 加 `grid-template-rows:minmax(0,1fr)`（行 59）。保留上一轮正确部分（`.chat-messages` min-height:0、auto-scroll 容差）。
- **验证**: 逐处验证（diff 仅 2 行新增、md5 变化、curl 200）；MoE 区域内容对比 IDENTICAL；无头浏览器不可用，真实渲染需人工确认。

---

## 四、未实施项 / 红线说明

1. **MoE 可视化真实数据展示（未实施）**:
   - 现状: 前端 [`updateExperts()`](scripts/demo/index.html:330) 仍使用 `Math.random()` 随机高亮格子（假数据，`experts_total/active` 来自 monitor 静态 config），详见 [`ui-bug-analysis-report-2026-08-10.md`](demo-ui-analysis-2026-08-10/ui-bug-analysis-report-2026-08-10.md) Bug2。
   - 分析建议的"前端改为确定性展示前 N 个专家"（方案 1）**未实施**；"新增 llama-server HTTP 端点暴露核心专家统计"（方案 2）与"`dump_metrics()` 周期输出"（方案 3）**违反 red-line #1（新增功能 + 改核心代码），明确不可实施**。
   - 原因: red-line #1 只做 bug 修复、绝不新增核心功能/机制；展示真实专家级数据需核心层 C++（`prefetch_scheduler` 的 `expert_pop_counts_` 等）经 HTTP 暴露，超出 bug 修复范畴。`git diff` 确认 MoE 相关代码零改动。
   - 因此本汇总明确标注: **MoE 真实数据展示仅分析、未实施**。
2. **本整合过程未修改任何代码**: 仅生成本总结文档 + git 操作留痕。
3. **镜像规则**: patches/llama-upstream/ 与 src/llama-upstream/src/ 同步（apply-slim-arc.py）——本次所有改动均在 `scripts/demo/` 内，不涉及 llama-upstream，无需镜像同步。
4. **未触碰项**: `monitor.py`、`src/llama-upstream/`、`patches/llama-upstream/`、`scripts/apply-slim-arc.py` 全程零改动。

---

## 五、留痕文件索引（5 个目录）

### `docs/rk3588_test_notes/demo-ui-2026-08-10/`
| 文件 | 内容 |
|------|------|
| demo-ui-report-2026-08-10.md | 首轮启动最终报告 |
| fix-record.md | 改动清单（start-demo.sh / llama_cli_server.py） |
| precheck.txt | 环境预检记录 |
| startup-log-1.txt | 首次启动（前台验证）日志 |
| startup-log-2.txt | 后台持久启动日志 |
| root-cause-01-path-and-binary.md | 路径 + 二进制根因 |
| verification-healthcheck.txt | 健康检查 + 推理验证输出 |

### `docs/rk3588_test_notes/demo-ui-debug-2026-08-10/`
| 文件 | 内容 |
|------|------|
| debug-report-2026-08-10.md | "无法持续生成"排查最终报告 |
| fix-record.md | 改动清单（index.html 4 处） |
| error-source.txt | 错误文案来源定位 |
| ablation-backend.txt | 后端直连消融原始输出 |
| ablation-params.txt | 参数消融结果表 |
| process-mem-status.txt | 进程/端口/内存/OOM 检查 |
| root-cause-01-system-prompt-80char-limit.md | 根因1 |
| root-cause-02-max-tokens-too-low.md | 根因2 |
| root-cause-03-escapeHtml-broken.md | 根因3 |

### `docs/rk3588_test_notes/demo-ui-analysis-2026-08-10/`
| 文件 | 内容 |
|------|------|
| ui-bug-analysis-report-2026-08-10.md | 两 bug 纯分析报告（含 MoE 红线结论） |
| code-snippets.md | 关键代码片段证据 |

### `docs/rk3588_test_notes/demo-ui-scrollfix-2026-08-10/`
| 文件 | 内容 |
|------|------|
| final-report-scrollfix-2026-08-10.md | 滚动修复第一轮最终报告 |
| fix-record.md | 改动清单（.chat-messages / auto-scroll） |
| prechange.txt | 修复前状态 |
| root-cause-scrollfix-2026-08-10.md | 根因分析（主因/次因） |
| step1-verify.txt | 改动1 验证 |
| step2-verify.txt | 改动2 验证 |
| index.html.bak | 修复前原文件备份 |

### `docs/rk3588_test_notes/demo-ui-scrollfix-r2-2026-08-10/`
| 文件 | 内容 |
|------|------|
| final-report-scrollfix-r2-2026-08-10.md | 滚动修复第二轮最终报告 |
| fix-record.md | 改动清单（.chat / .main） |
| layout-snippet.txt | 完整布局结构 + 关键 CSS/HTML 片段 |
| prechange.txt | 修复前分析 |
| root-cause-scrollfix-r2-2026-08-10.md | 真实根因分析（外层 grid） |
| step1-verify.txt | FIX-A 验证 |
| step2-verify.txt | FIX-B 验证 |

---

## 六、如何复测 / 访问

### 浏览器访问
1. 启动服务: `cd /home/orangepi/SLIM-ARC && bash scripts/demo/start-demo.sh 4b`
2. 浏览器打开 `http://127.0.0.1:8090/index.html`（局域网可用 `http://192.168.137.74:8090/index.html`；建议 **Ctrl+F5 强制刷新**避免缓存旧版）
3. 在左侧输入框发送较长问题，验证:
   - 消息超可视区后出现滚动条、可上下滚动、输入框固定在底部（滚动修复）
   - 流式生成期间上翻不被强制拉回（容差逻辑）
   - 长文本完整持续输出（"无法持续生成"修复）

### 健康检查命令
```bash
curl http://127.0.0.1:8080/health            # 期望 {"status":"ok"}
curl http://127.0.0.1:8001/api/health        # 期望 {"status":"ok","config":{...}}
curl http://127.0.0.1:8090/index.html        # 期望 HTTP 200
```

### 停止服务
```bash
ps aux | grep -E "llama-server|monitor.py|http.server" | grep -v grep | awk '{print $2}' | xargs -r kill
```

### 端到端推理（命令行流式）
```bash
curl -s -N -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"system","content":"你是 SLIM-ARC 优化后的端侧 AI 助手。请友好地回答用户问题。"},{"role":"user","content":"请写一篇较长的文章，至少200字"}],"stream":true,"max_tokens":512,"chat_template_kwargs":{"enable_thinking":false}}'
```

---

## 附：本整合涉及的 git 操作留痕

见同目录 `git-push-log.txt`（git status/add/commit/push 输出摘要、commit hash、远程地址、push 结果）。
