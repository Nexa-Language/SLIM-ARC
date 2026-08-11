# 最终报告 — 左侧聊天窗口滚动修复（第二轮 r2-2026-08-10）

- **日期**: 2026-08-10
- **目标**: scripts/demo/index.html（监视 UI 前端）
- **结论**: 左侧聊天窗口真实滚动容器为 `.chat-messages#messages`；根因是外层 grid 约束缺失（`.main` 行高 `auto` + `.chat` 的 `min-height:auto`），本次以 2 处最小改动解除外层约束，左栏滚动条可激活。

---

## 一、布局结构（完整梳理，详见 layout-snippet.txt）

```
body(100vh, overflow:hidden)
  .main(grid: 1fr 380px, height:calc(100vh-56px))
    ├ 左栏 .chat(flex column)              ← 行 250-264
    │    ├ .chat-header                     ← 行 251-253
    │    ├ .chat-messages#messages          ← 行 254（CSS 行 73-77）★左栏滚动容器
    │    └ .chat-input                      ← 行 260-263
    └ 右栏 .monitor#monitor(overflow-y:auto) ← 行 267（CSS 行 136-140）
          ├ 系统内存（行 268-280）
          ├ 推理速度 tps-chart（行 282-292）
          ├ MoE 专家激活 #experts（行 294-301）★严禁改动
          └ SLIM-ARC 优化链 #opt-chain（行 303-306）
```

- **左侧聊天真实滚动容器**: `.chat-messages#messages`（CSS 行 73-77，HTML 行 254），即 `flex:1; overflow-y:auto; padding:24px; min-height:0`。
- **`.chat-messages` 归属（纠正误判）**: 全文件仅出现 2 处（CSS 行 73、HTML 行 254），唯一属于**左侧聊天区**；与右侧 `.monitor` 无关。右栏 `.monitor` 自带 `overflow-y:auto`（行 138）——"上次修复只影响右栏"是现象误读，右栏本就可独立滚动；左栏不可滚是真实缺陷。

## 二、根因（详见 root-cause-scrollfix-r2-2026-08-10.md）

1. `.main` 未定义 `grid-template-rows`（默认 `auto`，行 56-62）→ 行高由内容决定，聊天消息变多时 grid 行被撑高，溢出被 `body{overflow:hidden}`（行 26）裁剪。
2. `.chat`（grid item）`overflow:visible`、无 `min-height` → 默认自动最小尺寸 = 内容 min-content，`.chat` 不收缩，随消息增高。
3. 结果: `.chat-messages` 高度被撑到足以容纳全部消息 → `overflow-y:auto`（行 74）永不触发 → 左栏无滚动条、无法上下滚动、输入框可能被挤出。
4. **上一轮为何无效**: 只给 flex 子项 `.chat-messages` 加 `min-height:0`（位置正确、保留），但未解除外层 grid item `.chat` 的自动最小尺寸与 `.main` 行高 `auto`——层级不够深，`overflow-y:auto` 未获激活条件。

## 三、改动详情（共 2 处，均为新增行，详见 fix-record.md）

| # | 文件 | 行 | 修改前 | 修改后 | 标注 |
|---|------|----|--------|--------|------|
| FIX-A | scripts/demo/index.html | 64-68（新增 68） | `.chat { background; display:flex; flex-direction:column; }` | 追加 `min-height:0;` | `/* SLIM-ARC FIX 2026-08-10: grid item(.chat) 默认自动最小尺寸... */` |
| FIX-B | scripts/demo/index.html | 56-63（新增 59） | `.main { ... grid-template-columns:1fr 380px; height:calc(100vh-56px); ... }` | 追加 `grid-template-rows:minmax(0,1fr);` | `/* SLIM-ARC FIX 2026-08-10: 默认 auto 行会被 .chat 内容撑高... */` |

- 保留（沿用上次正确部分）: `.chat-messages` 的 `min-height:0`（行 77）、流式 auto-scroll 容差（行 513）。

## 四、逐处验证（改一处验证一处）

- **FIX-A → step1-verify.txt**
  - `diff index.html.bak index.html`：仅 1 处新增（行 68），无删除/修改
  - md5 `5aa63cb...` → `4d61424...`；行数 539→540
  - `grep -n "SLIM-ARC FIX"` 命中行 67/76
  - `curl http://127.0.0.1:8090/index.html`：HTTP 200，输出命中行 67 新规则
- **FIX-B → step2-verify.txt**
  - 累计 diff 仅 2 行新增（行 59、68）
  - md5 `4d61424...` → `177cfb5...`；行数 540→541
  - `.main` 规则块命中行 59 `grid-template-rows:minmax(0,1fr)`
  - `curl http://127.0.0.1:8090/index.html`：HTTP 200，输出命中行 59 新规则

## 五、人工浏览器验证步骤（环境无无头浏览器，未伪造自动化渲染结果）

1. 浏览器访问 `http://127.0.0.1:8090/index.html`（建议 Ctrl+F5 强制刷新，避免缓存旧版）。
2. 在左侧输入框发送多条较长问题（或一条会返回长文本的问题），使左侧消息总高度超过可视区。
3. 预期: 左侧 `.chat-messages#messages` 右侧出现 6px 宽滚动条，可**上下滚动**查看全部历史；底部输入框始终固定在可视区底部。
4. 流式生成期间向上滚动翻看历史，应**不被强制拉回底部**（容差逻辑行 513 生效）；滚到底部附近后恢复自动跟随。
5. 回归: 右侧监控面板（内存/推理速度/MoE 专家/优化链）仍可独立上下滚动，MoE 专家格子动画正常。

## 六、MoE 可视化零改动证据

- `diff index.html.bak index.html` 仅 2 行新增（FIX-A/FIX-B），**无任何删除/修改行** → MoE 相关代码未触碰。
- 针对 `updateExperts`/`initExperts`/`Math.random`/`getElementById('experts')`/`experts_active`/`experts_total`/`experts-active`/`className = 'expert` 的**去行号内容对比：IDENTICAL（14 行完全一致）**。

## 七、red-line 遵守

1. ✅ 只做 bug 修复，不重构/不新增功能/不改算法——2 处均属滚动失效的最小布局约束修正。
2. ✅ 所有改动带 `SLIM-ARC FIX 2026-08-10: <原因>` 标注。
3. ✅ 镜像规则不涉及（本次仅改 scripts/demo/index.html，与 llama-upstream 无关）。
4. ✅ 全部记录/日志输出至 `docs/rk3588_test_notes/demo-ui-scrollfix-r2-2026-08-10/`。
5. ✅ 无终端交互，命令均为非交互式。
6. ✅ 每个失败留痕: FIX-A 首次 MoE 对比脚本因 `/bin/sh` 不支持进程替换失败（exit 2），已改用临时文件方式重新采集证据并记录（见下）。

## 八、留痕清单（docs/rk3588_test_notes/demo-ui-scrollfix-r2-2026-08-10/）

| 文件 | 内容 |
|------|------|
| layout-snippet.txt | 完整布局结构 + 关键 CSS/HTML 片段（带行号） |
| prechange.txt | 修复前分析：真实容器、`.chat-messages` 归属、根因、方案 |
| step1-verify.txt | FIX-A 逐处验证记录 |
| step2-verify.txt | FIX-B 逐处验证记录 |
| fix-record.md | 改动清单（前后对比 + 标注） |
| root-cause-scrollfix-r2-2026-08-10.md | 真实根因分析 |
| final-report-scrollfix-r2-2026-08-10.md | 本报告 |

附: 备份 `scripts/demo/index.html.bak`（md5 与基线一致）。
