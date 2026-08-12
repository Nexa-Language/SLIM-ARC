# 项目迁移与 UI 模型切换 - 实现与验证留痕

- **日期**: 2026-08-12
- **设备**: yituodabian (Raspberry Pi 5 / aarch64 / 4GB RAM)
- **涉及文件**: `scripts/demo/start-demo.sh`、`scripts/demo/monitor.py`、`scripts/demo/index.html`
- **状态**: 已实现、已验证并留痕

---

## 一、项目迁移过程（microSD → 移动硬盘）

### 1.1 迁移背景
项目原位于设备 microSD 卡（空间有限），现整体迁移到移动硬盘 `/home/yituodabian/data/`（挂载点 `/dev/sda1`，932G 容量，剩余 801G）。

**新项目路径**: `/home/yituodabian/data/SLIM-ARC/`

### 1.2 迁移引发的连锁问题（本任务发现并修复）

| 问题 | 现象 | 根因 | 处理 |
|------|------|------|------|
| llama-server 启动即崩 | `error while loading shared libraries: libllama-server-impl.so: cannot open shared object file` | 二进制内嵌 RUNPATH 仍指向**旧路径** `/home/yituodabian/SLIM-ARC/src/llama-upstream/build/bin`（迁移前路径），迁移后失效 | 启动前 `export LD_LIBRARY_PATH` 指向 `build/bin`（见下文） |
| 80B 模型文件名失效 | `start-demo.sh` 引用 `Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf` | 迁移后实际文件为 `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`（48.4GB），IQ4_XS 文件已不存在 | 修正模型文件名与 MODEL_SIZE |

### 1.3 模型文件与符号链接处理
- `data/models/` 下两个模型均为**普通文件**（非符号链接）：
  - `Qwen3-4B-Q4_K_M.gguf`（2.5GB）
  - `Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`（48.4GB，约 46GB 量级）
- 项目内**无残留符号链接**；`src/llama-upstream` 为真实目录（非链接）
- 迁移后不需符号链接方案，直接使用移动硬盘上的物理文件；唯一需要适配的是二进制 RUNPATH 失效（见 3.3）

---

## 二、start-demo.sh 修复详情

文件: `scripts/demo/start-demo.sh`

### 2.1 80B 模型文件名与大小修正
```bash
# 修正前（第 30-32 行）
MODEL="$PROJECT_ROOT/data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf"   # 已不存在
MODEL_NAME="Qwen3-Next-80B-IQ4_XS"
MODEL_SIZE="38 GB"

# 修正后（SLIM-ARC FIX 2026-08-12）
MODEL="$PROJECT_ROOT/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
MODEL_NAME="Qwen3-Next-80B-Q4_K_M"
MODEL_SIZE="46 GB"
```

### 2.2 按模型区分的启动参数
原实现 4B/80B 共用统一参数 `-t 4 -c 2048 -np 1`（2026-08-12 适配 4GB 设备时统一）。现拆分为独立变量，80B MoE 使用更小的 context 以降低 KV cache 内存：

```bash
# 4b 分支
MODEL_THREADS=4
MODEL_CTX=2048
MODEL_PARALLEL=1

# 80b 分支（SLIM-ARC FIX 2026-08-12）
MODEL_THREADS=4
MODEL_CTX=1024   # 80B MoE 在 4GB 设备上 KV cache 需更小
MODEL_PARALLEL=1
```

启动命令相应改为变量引用（保留 `SLIM_ARC_CTX` 环境变量覆盖能力）：
```bash
nohup "$LLAMA_DIR/build/bin/llama-server" \
    -m "$MODEL" -t "${MODEL_THREADS:-4}" -c "${SLIM_ARC_CTX:-$MODEL_CTX}" -np "${MODEL_PARALLEL:-1}" \
    --host 0.0.0.0 --port 8080 \
    -fa auto -ctk q4_0 -ctv q4_0 --no-repack --no-context-shift \
    > "$PROJECT_ROOT/logs/demo-llama-server.log" 2>&1 &
```

### 2.3 LD_LIBRARY_PATH 修复（迁移关键修复）
```bash
# SLIM-ARC FIX 2026-08-12: 迁移后 llama-server 二进制内嵌 RUNPATH 指向旧路径
# (/home/yituodabian/SLIM-ARC/...)，运行时找不到 libllama-server-impl.so。
# 用 LD_LIBRARY_PATH 显式指向 build/bin 解决（不修改二进制，不动 SLIM-ARC 核心）。
export LD_LIBRARY_PATH="$LLAMA_DIR/build/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

> 说明：不修改 llama.cpp 二进制本身（避免破坏 SLIM-ARC 补丁产物），通过运行时环境变量解决。

---

## 三、UI 切换功能实现方案

### 3.1 整体方案
前端模型切换按钮（4B/80B） + 后端 `/api/switch-model` 重启接口，切换期间 monitor 服务**自身不停止**，前端轮询 `/api/switch-status` 获知结果。

### 3.2 前端（`scripts/demo/index.html`）

**① 顶栏右侧按钮组**（`topbar-right` 内、badge 前）：
```html
<div class="model-switch">
    <button class="model-btn active" id="btn-4b" onclick="switchModel('4b')">4B</button>
    <button class="model-btn" id="btn-80b" onclick="switchModel('80b')">80B</button>
</div>
```

**② 交互流程**（`switchModel(target)`）：
1. 若目标=当前模型 → `alert` 提示
2. `confirm("切换到 XB 模型需要重启服务，约需 2-3 分钟加载，确认？")`
3. `POST /api/switch-model {"model":"4b"|"80b"}`
4. 显示全屏加载遮罩：旋转动画 + "正在加载 XB 模型..." + 已等待秒数（从 `/api/switch-status` 的 `elapsed` 读取）
5. 每 3 秒轮询 `/api/switch-status`：
   - `error` 存在 → 显示错误（红色面板，含日志尾部）
   - `!switching && llama_ready` → 显示 "✅ 模型加载完成" 并自动关闭
   - 其余 → 继续轮询，更新等待秒数
6. 总超时保护 10 分钟（`setTimeout`）
7. 按钮在切换期间禁用，防止并发操作

**③ 新增元素/样式**：`.model-switch`、`.model-btn(.active)`、`.overlay`（遮罩）、`.spinner`、`.overlay-title/sub/error/btn`；`currentModel` 由 `pollMonitor()` 根据 `config.model` 同步并刷新按钮高亮。

### 3.3 后端（`scripts/demo/monitor.py`）

**① 模型配置字典**（与 start-demo.sh 保持一致）：
```python
MODEL_CONFIGS = {
    "4b":  {"file": "Qwen3-4B-Q4_K_M.gguf", "name": "Qwen3-4B-Q4_K_M",
            "size": "2.4 GB", "experts_total": 0, "experts_active": 0,
            "threads": 4, "ctx": 2048, "n_parallel": 1},
    "80b": {"file": "Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf",
            "name": "Qwen3-Next-80B-Q4_K_M", "size": "46 GB",
            "experts_total": 512, "experts_active": 10,
            "threads": 4, "ctx": 1024, "n_parallel": 1},
}
```

**② 切换状态机**（线程安全，`switch_lock` 保护）：
```python
SWITCH_STATE = {
    "switching": False, "target_model": None, "current_model": "4b",
    "started_at": None, "finished_at": None,
    "llama_ready": False, "error": None, "llama_pid": None,
}
```

**③ `POST /api/switch-model`**（接收 Pydantic body `{"model": "4b"|"80b"}`）：
1. 安全检查 `is_local_request()`：仅允许回环（127.0.0.1/::1/localhost）+ 本机所有网卡 IP，否则 403
2. 未知模型 → 400；已有切换进行中 → 409
3. 置 `switching=True` 后**立即返回** `{"status":"switching", ...}`，由 daemon 线程 `do_switch()` 后台执行

**④ `do_switch(model_key)`**（后台线程）：
1. `pkill -f "llama-server"` 停止旧进程（monitor.py 命令行不含该串，自身不受影响）
2. 等 8080 端口释放
3. `subprocess.Popen` + `start_new_session=True` 启动新 llama-server（近似 nohup），**注入 LD_LIBRARY_PATH**（迁移修复）
4. 立即更新 `CONFIG`（顶栏模型名/大小/专家数同步）与 `current_model`
5. `_wait_llama_ready()` 轮询 `/health` 直到 HTTP 200

**⑤ 快速失败检测**（`_wait_llama_ready` 增强）：
- 轮询期间仅检查本次启动后**新增**日志，命中 `failed to fit params` / `failed to allocate` / `not enough memory` / `out of memory` 等关键字即 `proc.kill()` 并提前失败
- 解决：4GB 设备加载 80B 时 llama.cpp 打印 abort 但进程卡在 swap 风暴中不退出，原来要等满 600 秒

**⑥ `GET /api/switch-status`**：返回 `switching / target_model / current_model / llama_ready / error / elapsed / llama_pid`，供前端轮询。

**⑦ `GET /api/health`**：附带 `switch` 子对象（switching/target/current/llama_ready/error）。

---

## 四、验证结果

### 4.1 环境基线
- 内存: 4GB（MemTotal 4146304 kB），swap 2GB
- 无服务在运行、端口空闲时启动

### 4.2 4B 基本功能 ✅
- `bash start-demo.sh 4b` 启动成功：llama-server `/health` HTTP 200、monitor `/api/health` 正常、前端 8090 HTTP 200
- 实际推理验证：`/slots` 显示 `is_processing: true`、`n_prompt_tokens: 99` 正在生成 → 推理功能正常
- monitor 配置正确：`Qwen3-4B-Q4_K_M | 2.4 GB`，内存 available ~2.5GB 健康

### 4.3 80B 切换（预期失败路径）✅
- `POST /api/switch-model {"model":"80b"}` → 立即返回 `{"status":"switching","model":"80b"}`
- 80B llama-server 启动并 mmap 加载 46GB 模型（RSS 峰值 ~2.1GB）
- llama.cpp 内存适配检查判定无法放入 4GB：日志 `common_fit_params: failed to fit params to free device memory: was unable to fit model into system memory by reducing context, abort`
- **改进后 15.1 秒内快速失败**（日志关键字检测），`switch-status` 返回完整错误（含日志尾部），`switching=False`，**UI 可据此显示错误信息** ✅
- 切换全程 monitor（8001）保持响应（HTTP 200），服务自身未停止 ✅

### 4.4 80B 失败 → 4B 恢复 ✅
- 从 80B 失败状态 `POST /api/switch-model {"model":"4b"}`
- 44.6 秒后 `llama_ready: true`，llama-server HTTP 200，monitor config 恢复 `Qwen3-4B-Q4_K_M | 2.4 GB`

### 4.5 边界与安全 ✅
- 未知模型 `{"model":"xyz"}` → HTTP 400 + `{"status":"error","error":"未知模型: xyz，可选 4b / 80b"}`
- 并发切换保护：切换中再次请求返回 409（代码路径）
- 本地访问限制：`is_local_request` 仅放行回环与本机 IP（代码路径）
- 前端页面包含切换按钮组、遮罩、切换 JS 函数（静态检查通过，HTML 标签配对完整）

---

## 五、已知限制与注意事项

1. **80B 在本设备必然失败（预期）**：设备仅 4GB 内存，46GB 模型无法装入。切换功能设计为：80B 失败时 UI 优雅显示错误（含日志尾部），用户可一键切回 4B。**在 ≥32GB 内存设备上（SLIM-ARC 目标场景），80B 可正常加载并工作**，本切换机制不做区分。
2. **80B 加载期间 swap 风暴**：mmap 46GB 文件在 4GB 设备会触发严重 swap，快速失败逻辑已尽量缩短（~15s）。若系统出现 80B 进程卡死，可手动 `kill <llama_pid>`，do_switch 会捕获并置错误状态。
3. **切换期间旧推理请求会被中断**：`pkill llama-server` 会取消进行中的请求（预期行为）。
4. **前端确认框使用原生 `confirm()`**：部分嵌入式/远程桌面浏览器可能不支持，如需更佳体验可替换为自定义模态框。
5. **LD_LIBRARY_PATH 是迁移后必要条件**：若将来项目路径再次变更，需同步更新 `start-demo.sh` 与 `monitor.py` 两处的路径逻辑。
6. **80B 使用 `-c 1024`**（比 4B 更小）：这是为 4GB 设备的妥协配置；在内存充足的设备上建议恢复更大的 context。
7. **切换接口的本地访问限制**：仅本机（回环 + 本机网卡 IP）可发起切换；从其他机器浏览器访问本机 UI 时切换按钮会得到 403，符合"只允许本地运维"的安全要求。

---

## 六、相关文件清单

| 文件 | 改动 |
|------|------|
| `scripts/demo/start-demo.sh` | 80B 文件名/大小修正；按模型拆分启动参数；LD_LIBRARY_PATH 修复 |
| `scripts/demo/monitor.py` | 新增 `/api/switch-model`、`/api/switch-status`；切换状态机；快速失败检测；`/api/health` 附 switch 状态 |
| `scripts/demo/index.html` | 顶栏模型切换按钮组；确认对话框；加载遮罩；轮询与错误显示；当前模型高亮 |
| `docs/yituodabian_test_notes/project-migration-and-ui-switch-2026-08-12.md` | 本文档 |

---

## 七、二次修订：反向迁移与性能诊断（2026-08-12）

### 7.1 反向迁移背景
首次迁移后实测发现 **USB 口读速太慢**（移动硬盘 `/dev/sda1`），项目在 USB 上运行缓慢。故执行反向迁移：
- **项目移回 microSD 原位置**：`/home/yituodabian/data/SLIM-ARC/` → `/home/yituodabian/SLIM-ARC/`（rsync -a，3.47GB，1分12秒，内容校验 0 差异）
- **80B 模型移出到移动硬盘**：`Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`（46GB）移到 `/home/yituodabian/data/`
- **4B 模型保留**在项目 `data/models/` 内
- **80B 软链接**：项目 `data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf` → `/home/yituodabian/data/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`（绝对路径，跨文件系统有效）
- 删除源目录 `data/SLIM-ARC/`，验证 llama-server 可执行、软链接目标可读

**最终布局**：
```
/home/yituodabian/SLIM-ARC/              (microSD，项目 3.3G)
└── data/models/
    ├── Qwen3-4B-Q4_K_M.gguf             (2.4G，物理文件)
    └── Qwen3-Next-80B-...Q4_K_M.gguf    (软链接 → /home/yituodabian/data/...)
/home/yituodabian/data/                  (移动硬盘 /dev/sda1)
└── Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf  (46G，物理文件)
```

### 7.2 启动后 4B 推理变慢诊断
**现象**：4B 推理从之前的 ~4 t/s 降至 0.09-0.4 t/s，模型加载 59s（之前 ~20s）。
**诊断过程**：
1. llama-server `/health` 正常、三服务 200，但推理请求 90s 超时
2. vmstat：推理时 `wa`（I/O 等待）80%，`us` 仅 2-6%；`MAJFLT` 达 10.6 万 → **大量缺页**
3. 推理时 `bi`（块读入）持续 50-59 MB/s → **模型页不在内存，持续从磁盘读**
4. microSD 读速实测 1.5GB/s（正常，非磁盘硬件问题）
5. 内存分析：llama-server 2.3GB + VSCode server ~0.8GB ≈ 3.9GB，4GB 内存几乎占满，swap 2GB 满 → **模型页被逐出、无法常驻**

**根因结论**：**非 SLIM-ARC/UI 代码 bug**，而是系统内存压力。SLIM-ARC 补丁确认生效（`libllama.so` 含 `slim_arc::apply_dynamic_madv` 等符号），参数 `-t 4 -c 2048 -np 1` 合理。之前 ~4 t/s 是模型页 warm 在 page cache 的热窗口。

### 7.3 内存释放方案与效果
执行：
1. 停止非核心 VSCode 扩展进程（pylance 124MB、cpptools、markdown、json 共 ~181MB），保留主进程保持连接
2. 重置 zram swap（`swapoff/swapon /dev/zram0`）

**效果**（连续推理实测）：
| 次数 | 耗时 | 速度 |
|------|------|------|
| 第 1 次 | 21.8s / 20 tok | 1.74 t/s |
| 第 2 次 | 8.8s / 20 tok | 3.85 t/s |
| 第 3 次 | 4.5s / 20 tok | **4.73 t/s** ✅ |

推理速度完全恢复（模型页 warm 后回到 ~4.7 t/s）。

### 7.4 git 大量待提交处理
反向迁移后 `git status` 显示 **1082 个变更文件**。根因：**NTFS 迁移使所有文件权限变为可执行（100644→100755）**，git 将模式变化标记为 modified（1071 个权限变更 + 少量真实修改）。

**处理**：用 Python 基于 `git diff --raw -z` 批量恢复 252 个误加可执行位的文件为 100644 → git 状态降至 **3 个真实修改 + 10 个未跟踪**。

**提交推送**（2 个 commit 已推送 `origin/main`）：
- `e17e55c2` feat(demo): UI 模型切换 + 就绪检测修复 + 80B 文件名修正（3 文件，567 插入）
- `4a6abc72` docs(notes): 项目迁移留痕、UI 切换文档与 80B 测试日志（12 文件）

### 7.5 已知限制补充
1. **4GB 设备推理速度依赖内存状态**：模型页 warm 时 ~4.7 t/s；系统内存被大量后台进程占用时会降速。改善手段：释放 VSCode 扩展/后台进程内存、重置 swap。
2. **80B 模型在移动硬盘**：`start-demo.sh 80b` / UI 切换 80B 通过软链接读取移动硬盘上的 46GB 模型；4GB 设备上仍会因内存不足失败（预期），需 ≥32GB 设备。
3. **软链接依赖移动硬盘挂载**：若 `/home/yituodabian/data` 未挂载，80B 软链接失效（4B 不受影响）。
