# 修复记录
# 日期: 2026-08-10
# 文件: scripts/demo/index.html

## 改动清单

### 改动1: 移除系统提示中的"控制在 80 字以内"
- 文件: scripts/demo/index.html
- 行: 468 (修复前) → 469 (修复后)
- 标注: `// SLIM-ARC FIX 2026-08-10: 移除"控制在 80 字以内"限制，该提示导致模型拒绝长输出`
- 修复前:
  ```javascript
  { role: 'system', content: '你是 SLIM-ARC 优化后的端侧 AI 助手。SLIM-ARC 利用操作系统虚拟内存机制（mmap+MADV_RANDOM）让 80B MoE 大模型在 8GB 内存设备上流畅运行。请简洁友好地回答用户问题，控制在 80 字以内。' },
  ```
- 修复后:
  ```javascript
  // SLIM-ARC FIX 2026-08-10: 移除"控制在 80 字以内"限制，该提示导致模型拒绝长输出
  { role: 'system', content: '你是 SLIM-ARC 优化后的端侧 AI 助手。SLIM-ARC 利用操作系统虚拟内存机制（mmap+MADV_RANDOM）让 80B MoE 大模型在 8GB 内存设备上流畅运行。请友好地回答用户问题。' },
  ```
- 原因: 系统提示"控制在 80 字以内"使模型主动拒绝长输出，是"输出一段就停"的主要根因

### 改动2: max_tokens 从 200 提升到 512
- 文件: scripts/demo/index.html
- 行: 473 (修复前) → 475 (修复后)
- 标注: `// SLIM-ARC FIX 2026-08-10: max_tokens 从 200 提升到 512，200 太低导致输出被截断`
- 修复前:
  ```javascript
  max_tokens: 200,
  ```
- 修复后:
  ```javascript
  // SLIM-ARC FIX 2026-08-10: max_tokens 从 200 提升到 512，200 太低导致输出被截断
  max_tokens: 512,
  ```
- 原因: max_tokens=200 导致 finish_reason="length"，输出在句子中间被截断

### 改动3: 添加 HTTP 状态检查
- 文件: scripts/demo/index.html
- 行: 478 后新增 (修复后 480-487)
- 标注: `// SLIM-ARC FIX 2026-08-10: 添加 HTTP 状态检查，非 200 时显示错误而非静默失败`
- 新增代码:
  ```javascript
  // SLIM-ARC FIX 2026-08-10: 添加 HTTP 状态检查，非 200 时显示错误而非静默失败
  if (!r.ok) {
      const errText = await r.text();
      bubble.innerHTML = '⚠️ llama-server 返回错误 (HTTP ' + r.status + '): ' + escapeHtml(errText.substring(0, 200));
      sending = false;
      document.getElementById('send').disabled = false;
      input.focus();
      return;
  }
  ```
- 原因: 原代码无 r.ok 检查，HTTP 错误时静默失败显示"(无输出)"，不利于排查

### 改动4: 修复 escapeHtml 函数
- 文件: scripts/demo/index.html
- 行: 513-515 (修复前) → 522-525 (修复后)
- 标注: `// SLIM-ARC FIX 2026-08-10: 修复 HTML 转义，原代码替换值为空操作（&→& 等），导致 < > 被当作 HTML 标签解析`
- 修复前:
  ```javascript
  function escapeHtml(s) {
      return s.replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/\n/g,'<br>');
  }
  ```
- 修复后:
  ```javascript
  function escapeHtml(s) {
      // SLIM-ARC FIX 2026-08-10: 修复 HTML 转义，原代码替换值为空操作（&→& 等），导致 < > 被当作 HTML 标签解析
      return s.replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/\n/g,'<br>');
  }
  ```
- 原因: 原函数替换值与匹配值相同（空操作），未实际转义 HTML 实体，导致模型输出中的 `<` `>` 被 innerHTML 解析为 HTML 标签

## 改动范围
- 仅修改 scripts/demo/index.html
- 未修改 src/llama-upstream 核心推理逻辑
- 未修改 llama-server 启动参数
- 未修改 monitor.py
- 未修改 start-demo.sh
- 不涉及 patches/llama-upstream 镜像同步（demo 脚本不属于镜像范畴）

## 验证结果
- 修复前: 前端参数请求 → 96 字符, finish_reason="stop" (模型拒绝长输出)
- 修复后: 前端参数请求 → 918 字符, finish_reason="stop" (完整长输出)
- 改善: 输出长度提升约 9.6 倍
