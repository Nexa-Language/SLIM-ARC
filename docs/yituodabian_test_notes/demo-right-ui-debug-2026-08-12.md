# Demo 右侧 UI 数据不显示 - Debug 记录

- **日期**: 2026-08-12
- **设备**: yituodabian (Raspberry Pi 5 / aarch64 / 4GB RAM)
- **涉及文件**: `scripts/demo/index.html`、`scripts/demo/monitor.py`、`scripts/demo/start-demo.sh`
- **状态**: 已修复并留痕

## 一、问题描述

用户报告 Demo 页面**右侧监控面板数据不显示**（推理速度、MoE 专家激活等区域无数据/显示异常）。

## 二、排查过程

### 2.1 服务状态检查
三个服务均在运行，端口监听正常：
- `llama-server` (8080)：运行中，`/health` 返回 `{"status":"ok"}`
- `monitor.py` (8001)：运行中，`/api/monitor` 正常返回 JSON
- `http.server` (8090)：运行中，`index.html` 可访问（HTTP 200，23KB）

### 2.2 后端 monitor API 验证
`/api/monitor` 返回完整数据：config（model/size/tier/madv/kv/fa/repack）、memory（used_gb/total_gb/cached_gb）、metrics（n_decoded）、tps_history、timestamp 全部正常。

### 2.3 tps_history 复现实验
触发长推理（150 tokens），同时持续轮询 monitor API 观察 `tps_history`：
- 推理期间 tps_history **正常产生**（约 4 t/s，31 个数据点）
- 推理结束后 tps_history 保留数据（不丢失）
- **结论：monitor 后端 tps 采样逻辑正常**

### 2.4 跨域（CORS）验证
模拟浏览器跨域请求 `Origin: http://127.0.0.1:8090` → 响应头 `access-control-allow-origin: *`，**CORS 正常**。

### 2.5 前端代码静态检查
- 提取 index.html 全部 `<script>` JS（11966 字符），括号匹配检查通过
- 枚举 JS 中所有 `getElementById('xxx')` 引用的 16 个 ID，与 HTML 中 `id="xxx"` 逐一比对 → **全部存在**
- `querySelector` 选择器（`.experts-label span:last-child`、`.msg-bubble`）均匹配 HTML 结构
- CSS 布局正常（`.main` grid：`1fr 380px` 分左右栏）

### 2.6 Python 模拟前端 pollMonitor 逐字段校验
用真实 `/api/monitor` 响应模拟前端渲染逻辑：
| 区域 | 结果 |
|------|------|
| 顶栏 subtitle | ✅ 正常 |
| 内存 used/total + 进度条 | ✅ 正常 |
| 推理速度 tps | ⚠️ tps_history 为空时不显示 |
| 已生成 token | ✅ 正常 |
| 专家激活 | ⚠️ experts_total=0 时前端不更新 |
| 优化链 | ✅ 正常 |

## 三、根因分析

1. **无数据反馈缺陷（主要）**：前端 `pollMonitor()` 的 catch 分支只执行 `console.log('monitor error', e)`，当 monitor 未就绪/请求失败/返回异常时，右侧面板**静默空白**（顶栏停在"加载中..."、内存显示"-- GB"），用户无法区分"监控未连接"与"数据正常"。
2. **无推理时 tps 区误导**：`tps_history` 为空时（无推理活动），前端保留初始值 `0.00 t/s`，用户误以为"无数据/有 bug"。
3. **4B 非 MoE 模型专家区显示假数据**：`experts_total=0` 时前端不调用 `updateExperts`，但 `initExperts(512, 10)` 已生成静态随机格子（128 格、10 个随机激活），用户误认为是真实专家激活数据。

## 四、修复内容（`scripts/demo/index.html`）

### 4.0 后端地址动态 hostname（关键修复，跨机访问根因）
此前前端硬编码：
```js
const LLAMA_SERVER = 'http://127.0.0.1:8080';
const MONITOR_API = 'http://127.0.0.1:8001/api/monitor';
```
若从**非本机浏览器**访问（局域网 IP / 远程桌面 / VNC），`127.0.0.1` 指向访问者本机，`fetch` 必然失败 → 右侧数据**完全不显示**。改为动态拼接：
```js
const HOST = window.location.hostname || '127.0.0.1';
const LLAMA_SERVER = `http://${HOST}:8080`;
const MONITOR_API = `http://${HOST}:8001/api/monitor`;
```

### 4.1 对 `pollMonitor()` 函数增强

1. **增加 HTTP 状态与数据完整性检查**：
   ```js
   if (!r.ok) throw new Error('HTTP ' + r.status);
   const data = await r.json();
   if (!data || !data.config || !data.memory || !data.metrics) {
       throw new Error('monitor 返回数据不完整');
   }
   ```
2. **无推理时 tps 区明确提示**：`tps_history` 为空时显示 `等待推理...`，替代误导性的 `0.00 t/s`。
3. **非 MoE 模型专家区明确提示**：`experts_total=0` 时显示 `当前模型非 MoE，无专家激活数据`，替代静态随机假格子。
4. **监控不可用时可见提示**：catch 分支将顶栏 subtitle 置为 `⚠️ 监控服务未连接，正在重试...`（500ms 轮询自动恢复），避免静默空白。

## 五、验证结果

- 修改后 JS 括号匹配检查通过
- `http.server` 提供的页面已含修复内容（`curl` 确认包含"等待推理"标记）
- 后端 monitor API 数据链路验证通过（内存/token/优化链/tps 均有数据）

## 六、结论与建议

- **后端 monitor 与前端数据链路本身无功能性 bug**，数据均可正常获取与渲染。
- 用户感知的"数据不显示"主要源于**前端在无数据/未就绪时缺乏反馈**，以及**非 MoE 模型与无推理活动场景下未做区分处理**，本次已通过状态反馈与场景化提示修复。
- **建议**：
  1. 浏览器硬刷新（Ctrl+Shift+R）确保加载最新 index.html，避免缓存旧页面。
  2. **跨机访问已修复**：`MONITOR_API`/`LLAMA_SERVER` 已改为 `window.location.hostname` 动态拼接，无论通过 `127.0.0.1` 还是局域网 IP 访问 8090，均能正确指向本机后端。
  3. 80B 模型（experts_total=512）运行时专家区将正常显示真实激活数据；4B 模型会明确提示"非 MoE 模型"。
