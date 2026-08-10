# 修复记录 — 对话窗口无法上下滚动（Bug1 两处）

- **日期**: 2026-08-10
- **目标文件**: scripts/demo/index.html（仅此一个文件）
- **修复性质**: bug 修复（CSS + JS），最小外科手术式改动，含 SLIM-ARC FIX 标注
- **基线 MD5**: 25acbdcc29ad6acdc673482d58582b0c（535 行）
- **最终 MD5**: 5aa63cbab2c9d81315752505dc48c208（539 行，+4 行 = 第1处+1 行 + 第2处+3 行）
- **备份文件**: docs/rk3588_test_notes/demo-ui-scrollfix-2026-08-10/index.html.bak

---

## 改动清单

### 改动 1（主因，致命）: `.chat-messages` 添加 `min-height: 0;`

| 项 | 内容 |
|----|------|
| 文件 | scripts/demo/index.html |
| 位置 | 行 73-75 `.chat-messages` CSS 规则（修改前 73-75，修改后新增一行到 76） |
| SLIM-ARC FIX | `/* SLIM-ARC FIX 2026-08-10: flexbox 子项默认 min-height:auto 阻止 overflow-y 生效 */` |

**改动前后对比**:
```diff
         .chat-messages {
             flex: 1; overflow-y: auto; padding: 24px;
+            min-height: 0; /* SLIM-ARC FIX 2026-08-10: flexbox 子项默认 min-height:auto 阻止 overflow-y 生效 */
         }
```

**验证结论**: ✅ 通过
- grep 命中新增行（当前文件行 75）；md5 变化（25acbdcc→250eac5e）
- curl 前端服务 200，且服务返回内容含新增行（证明 http.server 已读取更新文件）
- 无头浏览器不可用，真实滚动效果需人工验证（见 step1-verify.txt 人工步骤）

---

### 改动 2（次因）: `send()` 流式 auto-scroll 改为底部容差触发

| 项 | 内容 |
|----|------|
| 文件 | scripts/demo/index.html |
| 位置 | 修改前行 509（流式 token 处理内）；修改后行 510-513 |
| SLIM-ARC FIX | `// SLIM-ARC FIX 2026-08-10: 仅当用户已在底部附近时才自动滚动，避免阻止回看历史` |

**改动前后对比**:
```diff
                                     text += delta.content;
                                     bubble.innerHTML = escapeHtml(text) + '<span class="cursor"></span>';
-                                    messages.scrollTop = messages.scrollHeight;
+                                    // SLIM-ARC FIX 2026-08-10: 仅当用户已在底部附近时才自动滚动，避免阻止回看历史
+                                    if (messages.scrollTop + messages.clientHeight >= messages.scrollHeight - 50) {
+                                        messages.scrollTop = messages.scrollHeight;
+                                    }
                                 }
```

**未改动项**: 行 459（现 460）发送新消息时的 `messages.scrollTop = messages.scrollHeight;` 按分析报告建议保留不变。

**验证结论**: ✅ 通过
- grep 确认新条件逻辑存在（当前行 511）；行 460 发送时滚动保持无条件
- md5 变化（250eac5e→5aa63cb）；curl 200 且服务返回内容含新逻辑（行 511）
- 无头浏览器不可用，"上翻不被强制拉回"需人工验证（见 step2-verify.txt 人工步骤）

---

## 逐处验证结论汇总

| 步骤 | 内容 | 结果 |
|------|------|------|
| 步骤 0 | 目录/基线/备份/prechange.txt | ✅ 完成（见 prechange.txt） |
| 步骤 1 | 改动 1 + 验证（grep/md5/curl/无头工具探测） | ✅ 通过，留痕 step1-verify.txt |
| 步骤 2 | 改动 2 + 验证（grep/md5/curl/无头工具探测） | ✅ 通过，留痕 step2-verify.txt |
| 步骤 3 | MoE 可视化零改动对比 + 汇总 | ✅ 通过（见下） |

---

## MoE 可视化零改动证据（red-line 遵守）

| 证据项 | 内容 | 结果 |
|--------|------|------|
| 全文件 diff | 备份 vs 当前仅两处改动（+1 行 CSS、+3 行 JS） | ✅ 仅改动 1/2 |
| Math.random 行 | 备份 334 → 当前 335（偏移 +1 来自改动 1 插入行），内容一致 | ✅ 零改动 |
| updateExperts 定义 | 备份 327 → 当前 328（偏移 +1），内容一致 | ✅ 零改动 |
| initExperts 定义 | 备份 316 → 当前 317（偏移 +1），内容一致 | ✅ 零改动 |
| pollMonitor 调用 | 备份 421 → 当前 422（偏移 +1），内容一致 | ✅ 零改动 |
| MoE 区域逐行对比 | sed 提取 备份316-422 vs 当前317-423 → `diff` 完全一致 (MATCH) | ✅ 零改动 |
| monitor.py | 本次任务未触碰 | ✅ 零改动 |

> 说明: 因改动 1 在 MoE 区域（行 316 之后）之前插入 1 行，当前文件 MoE 相关行号 = 备份行号 + 1；两文件对应区域内容 diff 完全一致，证明 MoE 可视化代码零改动。
