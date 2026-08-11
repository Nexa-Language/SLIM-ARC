# Demo UI 启动修复记录（fix-record）

日期：2026-08-10
范围：仅 bug 修复 / 环境缺失补齐，未修改任何核心代码/机制、未重构、未新增功能。

---

## 改动清单

### 1. `scripts/demo/start-demo.sh`

**位置**：第 12 行附近（`LLAMA_DIR` 定义处），共新增 4 行。

**改动前**：
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
DEMO_DIR="$PROJECT_ROOT/scripts/demo"
```

**改动后**：
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# SLIM-ARC FIX 2026-08-10: llama-upstream 是独立 git clone，实际位于仓库外
# (PROJECT_ROOT/../src/llama-upstream)，此处自动探测两种布局，避免路径不存在
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ] && [ -x "$(dirname "$PROJECT_ROOT")/src/llama-upstream/build/bin/llama-server" ]; then
    LLAMA_DIR="$(dirname "$PROJECT_ROOT")/src/llama-upstream"
fi
DEMO_DIR="$PROJECT_ROOT/scripts/demo"
```

**为什么**：本项目实际布局中 `src/llama-upstream` 是独立 git clone（.gitignore 第 265 行忽略），
位于 `/home/orangepi/src/llama-upstream`（`$HOME/src/` 下），而非 `SLIM-ARC/src/llama-upstream`。
原脚本硬编码 `$PROJECT_ROOT/src/llama-upstream` 指向不存在的路径，导致
`nohup: failed to run command '.../llama-server': No such file or directory`。
修复为自动探测两种布局，标准路径存在则用标准路径，否则回退到仓库外独立 clone 路径。

**标注**：`# SLIM-ARC FIX 2026-08-10: ...`

---

### 2. `scripts/demo/llama_cli_server.py`（备用方案同步修复）

**位置**：第 35-36 行（`LLAMA_CLI` 定义处），共新增 2 行。

**改动前**：
```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LLAMA_CLI = PROJECT_ROOT / "src/llama-upstream/build/bin/llama-cli"
```

**改动后**：
```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# SLIM-ARC FIX 2026-08-10: llama-upstream 是独立 git clone，实际位于仓库外
# (PROJECT_ROOT.parent/src/llama-upstream)，此处自动探测两种布局
LLAMA_CLI = PROJECT_ROOT / "src/llama-upstream/build/bin/llama-cli"
if not LLAMA_CLI.exists():
    LLAMA_CLI = PROJECT_ROOT.parent / "src/llama-upstream/build/bin/llama-cli"
```

**为什么**：与 start-demo.sh 相同的路径 bug（备用方案 WSL2 bind 回退脚本同样硬编码了
不存在的路径）。同步修复，使备用方案在本环境也可用。已通过 `python3 -m py_compile`
语法检查，并验证解析结果为 `/home/orangepi/src/llama-upstream/build/bin/llama-cli`（存在）。

**标注**：`# SLIM-ARC FIX 2026-08-10: ...`

---

## 环境补齐（非代码改动）

### 3. llama-server 二进制构建

- 现象：`/home/orangepi/src/llama-upstream/build/bin/` 缺 `llama-server` 可执行文件
  （只有 llama-cli / llama-bench / libllama-server-impl.so）。
- 根因：CMakeCache 已启用 `LLAMA_BUILD_SERVER=ON`，但 `llama-server` 主程序 target
  之前未构建完成。
- 处理：`cmake --build build --target llama-server -j$(nproc)` 构建成功，
  生成 `build/bin/llama-server`（version 1, aarch64）。
- 备注：构建过程中 UI assets 下载失败（离线环境，huggingface SSL connect error），
  仅影响内置 Web UI 嵌入，不影响 HTTP 服务功能。

### 4. Python 依赖安装

- 缺失：fastapi / uvicorn / requests（python3 无法 import）。
- 处理：`python3 -m pip install fastapi uvicorn requests`
  （默认 PyPI 源可用；清华源不可用）。
- 结果：fastapi 0.141.1, uvicorn 0.52.1, requests 2.34.2。

---

## 未做改动

- 未修改 `src/llama-upstream/` 任何源码（无需要）。
- 未修改 `patches/llama-upstream/`（本次修复不涉及核心机制，无需同步镜像）。
- 未新增任何演示功能。
- `monitor.py`、`index.html` 无需改动（运行正常）。

---

## 遗留说明（环境限制）

- 80B 模型 `Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf` 不存在，且本机磁盘 28G 仅剩 17G，
  38GB 模型无法安装，故本次使用 4B 模型（Qwen3-4B-Q4_K_M.gguf）验证 UI 完整链路。
