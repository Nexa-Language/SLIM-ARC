# 根因分析 — 对话窗口无法上下滚动（Bug1）

- **日期**: 2026-08-10
- **现象**: 左侧聊天窗口消息变多后无法上下滚动查看历史；消息持续向下"推"，输入框可能被挤出可视区。

---

## 根因 1（主因，致命）: flexbox `min-height: auto` 默认值使 `overflow-y: auto` 永不激活

**涉及代码**（scripts/demo/index.html）:
- `.chat`（行 64-67）: `display: flex; flex-direction: column;`
- `.chat-messages`（行 73-75）: `flex: 1; overflow-y: auto; padding: 24px;` — **缺少 `min-height: 0`**
- `body`（行 21-27）: `height: 100vh; overflow: hidden;`

**机制**:
1. `.chat-messages` 是 `.chat`（flex column）的 flex 子项。
2. CSS Flexbox 规范: flex 子项默认 `min-height: auto`，即**不允许元素缩小到低于其内容固有最小高度**。
3. 因此即使设置 `overflow-y: auto`，当消息累积时 `.chat-messages` 不会收缩，而是跟着内容一起变高——内部从不溢出，滚动条永不出现。
4. 变高的 `.chat-messages` 把 `.chat-input` 推出视口底部；`body` 的 `overflow: hidden` 又把溢出部分直接裁剪。

**结果**: 消息无限往下长，但滚动失效，底部输入框被挤出/裁剪。

**修复**: 在 `.chat-messages` 添加 `min-height: 0;`，覆盖 flexbox 默认的 `min-height: auto`，允许其收缩到 flex 分配的可用空间，内容超出即触发 `overflow-y: auto` 滚动条。

---

## 根因 2（次因）: 流式输出每个 token 强制滚到底部，阻止用户回看

**涉及代码**（scripts/demo/index.html，修改前行 509）:
```javascript
messages.scrollTop = messages.scrollHeight;  // 每个流式 token 到达都无条件执行
```

**机制**: 流式生成时每次收到 token 就强制把滚动位置钉死在底部。即使滚动条可用了，用户在生成期间一旦向上翻看，下一个 token 到达立即被拉回底部，历史回看被持续打断。

**修复**: 改为仅当用户已在底部附近（`scrollTop + clientHeight >= scrollHeight - 50`，50px 容差）时才自动滚动；用户上翻时不强制滚动，回到底部附近后恢复自动跟随。发送新消息时的无条件滚动（行 460）保留——发送时定位到底部是合理 UX。

---

## 修复前 → 修复后行为对照

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 消息超出可视高度 | 滚动条不出现，无法滚动，输入框被挤出 | `.chat-messages` 出现滚动条，可上下滚动，输入框固定在底部 |
| 流式生成期间用户上翻 | 每个 token 强制拉回底部，无法回看 | 保持用户位置不被打断；回到底部附近后恢复自动跟随 |
| 发送新消息 | 立即滚到底部 | 立即滚到底部（保留，预期 UX） |

---

## 验证方式说明

- 命令级验证（grep/md5/curl）全部通过，证明改动已写入文件并被前端服务读取。
- 环境中无任何无头浏览器工具（playwright/node/puppeteer/selenium/chromium 均不可用），
  真实渲染效果（滚动条出现、上翻不被拉回）需人工浏览器验证，步骤见
  step1-verify.txt 与 step2-verify.txt，**未伪造验证结果**。
