# 修复记录 — 左侧聊天窗口滚动修复（第二轮 r2-2026-08-10）

- **日期**: 2026-08-10
- **目标文件**: scripts/demo/index.html
- **基线**: md5=`5aa63cbab2c9d81315752505dc48c208`，539 行
- **修改后**: md5=`177cfb5a58e45ce87cf8729c82987ee6`，541 行
- **备份**: scripts/demo/index.html.bak（与基线一致，只读）

---

## 改动清单（共 2 处，均为新增行，最小外科手术式）

### FIX-A：`.chat` 增加 `min-height: 0`（新增行 68，原行 64-67）

```css
/* 修改前（行 64-67） */
.chat {
    background: var(--bg);
    display: flex; flex-direction: column;
}

/* 修改后（行 64-68） */
.chat {
    background: var(--bg);
    display: flex; flex-direction: column;
    min-height: 0; /* SLIM-ARC FIX 2026-08-10: grid item(.chat) 默认自动最小尺寸 min-height:auto 会把 grid 行撑高，导致内部 .chat-messages 的 overflow-y:auto 永不触发；允许 .chat 收缩到 grid 行高，使左栏滚动条可激活 */
}
```

### FIX-B：`.main` 增加 `grid-template-rows: minmax(0, 1fr)`（新增行 59，原行 56-62）

```css
/* 修改前（行 56-62） */
.main {
    display: grid;
    grid-template-columns: 1fr 380px;
    height: calc(100vh - 56px);
    gap: 1px;
    background: var(--border);
}

/* 修改后（行 56-63） */
.main {
    display: grid;
    grid-template-columns: 1fr 380px;
    grid-template-rows: minmax(0, 1fr); /* SLIM-ARC FIX 2026-08-10: 默认 auto 行会被 .chat 内容撑高(配合 .chat 的 min-height:auto)，导致左栏 .chat-messages 的 overflow-y:auto 不触发；显式 1fr 使行高固定为容器高度且允许内容溢出不撑行 */
    height: calc(100vh - 56px);
    gap: 1px;
    background: var(--border);
}
```

---

## 保留（沿用上次修复中正确的部分，本次未改动）

- `.chat-messages { flex:1; overflow-y:auto; padding:24px; min-height:0; }`（行 73-77）——上次加的 `min-height:0` 位置正确（`.chat-messages` 确属左栏），保留。
- `send()` 流式 auto-scroll 容差逻辑 `if (messages.scrollTop + messages.clientHeight >= messages.scrollHeight - 50)`（行 513）——合理，保留。

## 逐处验证

- FIX-A：见 `step1-verify.txt`（diff 仅新增 1 行、md5 变化、grep 命中、curl HTTP 200 且读到新规则）。
- FIX-B：见 `step2-verify.txt`（累计 diff 仅 2 行新增、md5 变化、curl HTTP 200 且读到新规则）。

## 验证命令汇总

```bash
diff index.html.bak index.html            # 仅 2 处新增行（59、68），无删除/修改
md5sum index.html index.html.bak          # 177cfb... vs 5aa63c...
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8090/index.html   # 200
curl -s http://127.0.0.1:8090/index.html | grep -n "SLIM-ARC FIX 2026-08-10"
```
