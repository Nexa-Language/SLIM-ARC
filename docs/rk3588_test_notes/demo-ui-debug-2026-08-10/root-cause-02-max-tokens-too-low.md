# 根因分析: max_tokens=200 导致输出被截断

## 日期: 2026-08-10

## 根因描述
index.html:473 设置 max_tokens=200，对于长文本生成请求来说太低。
即使移除系统提示中的字数限制，200 token 的上限也会导致输出在句子中间被截断。

## 证据链

### 证据1: 前端代码 (index.html:473, 修复前)
```javascript
max_tokens: 200,
```

### 证据2: 参数消融 (max_tokens=200, 无字数限制)
- 请求: "请写一篇较长的文章，至少200字" + 系统提示"请详细回答问题"
- 响应: 378 字符，内容在"例如"处被截断
- finish_reason: "length" (因达到 max_tokens 上限而截断)
- 结论: 200 token 不足以生成完整的 200 字以上文章

### 证据3: 参数消融 (max_tokens=512, 无字数限制)
- 同样的请求，max_tokens 提升到 512
- 响应: 1690 字符，完整文章
- finish_reason: "stop" (自然结束)
- 结论: 512 token 足够生成完整的长回答

### 证据4: llama-server 日志
```
task 2016 | eval time = 34045.98 ms / 200 tokens (170.23 ms per token, 5.87 t/s)
```
- 确认模型生成了恰好 200 token 后被截断

## 结论
max_tokens=200 是"输出一段就停"的**次要根因**。
在系统提示限制被移除后，200 token 仍会导致输出被截断（finish_reason="length"）。
提升到 512 后，模型能自然完成长文本生成。
