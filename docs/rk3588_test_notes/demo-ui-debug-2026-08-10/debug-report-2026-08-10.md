# SLIM-ARC 监视 UI "无法持续生成"问题排查报告
# 日期: 2026-08-10
# 排查者: Zoo (debug mode)

## 一、问题现象

1. UI 无法持续生成：聊天界面输出一段就停止，不能持续生成完整回答
2. 强制生成固定字数时，输出"可能内存不足或模型加载问题，建议检查设备内存和模型兼容性"

## 二、排查过程

### 步骤1: 定位错误文案来源
- 在 scripts/demo/ 全部文件和整个 SLIM-ARC 项目中搜索"内存不足"、"模型加载问题"、"模型兼容性"
- **结果**: 该错误文案在代码库中不存在
- **结论**: 该文案是模型自身生成的文本，不是程序错误处理分支的产物
- 详见: error-source.txt

### 步骤2: 后端直连消融（隔离前后端）
- 绕过前端，直接 curl 调用 llama-server(8080)
- **前端参数** (max_tokens=200, 80字限制): 输出 96 字, finish_reason="stop", 模型拒绝长输出
- **宽松参数** (max_tokens=512, 无限制): 输出 1690 字, finish_reason="stop", 完整长文章
- **结论**: 后端完全正常，问题在前端参数
- 详见: ablation-backend.txt

### 步骤3: 参数消融
| 系统提示 | max_tokens | finish_reason | 字符数 | 结论 |
|---------|-----------|--------------|--------|------|
| 80字限制 | 200 | stop | 96 | 模型拒绝 |
| 80字限制 | 200 | stop | 26 | 非流式同样拒绝 |
| 无限制 | 200 | length | 378 | max_tokens截断 |
| 无限制 | 512 | stop | 1690 | 完整输出 |
- **结论**: 两个因素叠加导致"一段就停"
- 详见: ablation-params.txt

### 步骤4: 进程/内存/OOM 状态排查
- 三个服务正常运行 (PID 69497/69498/69499)
- 端口 8080/8001/8090 均 LISTEN
- 内存: 7.8GB 总, 5.4GB 可用, 无不足
- dmesg/journalctl: 无 OOM 事件
- /slots: 无卡死 slot
- **结论**: 系统资源完全正常
- 详见: process-mem-status.txt

### 步骤5: 前后端联动消融（SSE 解析）
- index.html SSE 解析逻辑正确: reader.read() → split('\n') → 'data: ' → JSON.parse → delta.content
- [DONE] 处理正确 (continue, 非 break)
- 发现 escapeHtml 函数 bug: 替换值为空操作，未实际转义 HTML 实体
- 发现缺少 r.ok 检查: HTTP 错误时静默失败
- **结论**: SSE 解析无提前停止 bug，但 escapeHtml 和错误处理有 bug

## 三、根因（含证据）

### 根因1（主因）: 系统提示"控制在 80 字以内"
- **位置**: index.html:468
- **机制**: 系统提示直接指示模型限制回答长度，模型遵循指令拒绝长输出
- **证据**: 
  - 前端参数 → 96 字, finish_reason="stop" (模型主动停止)
  - 宽松参数 → 1690 字, finish_reason="stop" (自然结束)
  - /slots: n_decoded=18, n_remain=182 (200额度中仅用18)
- 详见: root-cause-01-system-prompt-80char-limit.md

### 根因2（次因）: max_tokens=200 过低
- **位置**: index.html:473
- **机制**: 即使移除字数限制，200 token 不足以生成完整长文章
- **证据**:
  - max_tokens=200 + 无限制 → 378 字, finish_reason="length" (截断)
  - max_tokens=512 + 无限制 → 1690 字, finish_reason="stop" (完整)
- 详见: root-cause-02-max-tokens-too-low.md

### 根因3（潜在）: escapeHtml 函数无效
- **位置**: index.html:513-515
- **机制**: 替换值为空操作（&→&, <→<, >→>），未转义 HTML 实体
- **影响**: 模型输出含 `<` `>` 时，innerHTML 解析为 HTML 标签，可能吞掉后续内容
- **证据**: hexdump 确认替换值与匹配值字节相同
- 详见: root-cause-03-escapeHtml-broken.md

## 四、修复方式

### 修复1: 移除系统提示中的"控制在 80 字以内"
- 改为"请友好地回答用户问题"
- 标注: `// SLIM-ARC FIX 2026-08-10`

### 修复2: max_tokens 从 200 提升到 512
- 标注: `// SLIM-ARC FIX 2026-08-10`

### 修复3: 添加 HTTP r.ok 状态检查
- 非 200 时显示错误信息而非静默失败
- 标注: `// SLIM-ARC FIX 2026-08-10`

### 修复4: 修复 escapeHtml 函数
- `&`→`&`, `<`→`<`, `>`→`>`
- 标注: `// SLIM-ARC FIX 2026-08-10`

详见: fix-record.md

## 五、验证结果

### 修复前
- 前端参数请求 → 96 字符, finish_reason="stop" (模型拒绝长输出)
- 输出内容: "我无法写长文，但可以帮你精简内容或提供简要回答。"

### 修复后
- 修复后参数请求 (max_tokens=512, 无字数限制) → 918 字符, finish_reason="stop" (完整长输出)
- 输出内容: 完整的 AI 与科技主题文章
- 改善: 输出长度提升约 9.6 倍

### 验证命令
```bash
curl -s -N -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"system","content":"你是 SLIM-ARC 优化后的端侧 AI 助手。SLIM-ARC 利用操作系统虚拟内存机制（mmap+MADV_RANDOM）让 80B MoE 大模型在 8GB 内存设备上流畅运行。请友好地回答用户问题。"},{"role":"user","content":"请写一篇较长的文章，至少200字"}],"stream":true,"max_tokens":512,"temperature":0.7,"top_p":0.9,"chat_template_kwargs":{"enable_thinking":false}}'
```

## 六、留痕文件清单

| 文件 | 内容 |
|------|------|
| error-source.txt | 错误文案来源定位结果 |
| ablation-backend.txt | 后端直连消融原始输出 |
| ablation-params.txt | 参数消融结果表 |
| process-mem-status.txt | 进程/端口/内存/OOM 检查 |
| root-cause-01-system-prompt-80char-limit.md | 根因1: 系统提示限制 |
| root-cause-02-max-tokens-too-low.md | 根因2: max_tokens过低 |
| root-cause-03-escapeHtml-broken.md | 根因3: escapeHtml无效 |
| fix-record.md | 改动清单 |
| debug-report-2026-08-10.md | 本报告 |

## 七、如何复现/复测

### 复现问题（修复前行为）
1. 启动服务: `bash scripts/demo/start-demo.sh 4b`
2. 访问 http://127.0.0.1:8090/index.html
3. 输入"请写一篇较长的文章，至少200字"
4. 观察: 输出很短就停止（模型拒绝长输出）

### 验证修复（修复后行为）
1. 刷新浏览器（加载修复后的 index.html）
2. 输入"请写一篇较长的文章，至少200字"
3. 观察: 模型持续生成完整长回答（500-1000+字）

### 命令行验证
```bash
# 流式
curl -s -N -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"system","content":"你是 SLIM-ARC 优化后的端侧 AI 助手。请友好地回答用户问题。"},{"role":"user","content":"请写一篇较长的文章，至少200字"}],"stream":true,"max_tokens":512,"chat_template_kwargs":{"enable_thinking":false}}'

# 非流式
curl -s -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"system","content":"你是 SLIM-ARC 优化后的端侧 AI 助手。请友好地回答用户问题。"},{"role":"user","content":"请写一篇较长的文章，至少200字"}],"stream":false,"max_tokens":512,"chat_template_kwargs":{"enable_thinking":false}}'
```

## 八、范围与边界声明
- 本次修改仅涉及 scripts/demo/index.html（前端 bug 修复）
- 未修改 src/llama-upstream 核心推理逻辑
- 未修改 llama-server 启动参数
- 不涉及 patches/llama-upstream 镜像同步
- 所有改动均带 SLIM-ARC FIX 2026-08-10 标注
