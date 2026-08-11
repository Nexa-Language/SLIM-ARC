# Root Cause 分析记录

## 问题 1：llama-server 二进制缺失（build/bin 下无 llama-server 可执行文件）

**现象**：`/home/orangepi/src/llama-upstream/build/bin/` 下只有 llama-cli、llama-bench，
没有 llama-server；但存在 `libllama-server-impl.so`。

**根因**：CMakeCache.txt 显示 `LLAMA_BUILD_SERVER:BOOL=ON`（server 已启用并编译了 impl 库），
但 `llama-server` 主程序 target 之前未构建（可能是上次构建被中断，或只构建了部分 target）。

**修复**：执行 `cmake --build build --target llama-server -j$(nproc)` 完成构建，
成功生成 `build/bin/llama-server`（version 1, aarch64）。

---

## 问题 2：start-demo.sh 的 llama-upstream 路径错误（核心阻塞点）

**现象**：`bash scripts/demo/start-demo.sh 4b` 输出：
```
nohup: failed to run command '/home/orangepi/SLIM-ARC/src/llama-upstream/build/bin/llama-server': No such file or directory
```

**根因**：start-demo.sh 第 12 行 `LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"`，
其中 `PROJECT_ROOT="/home/orangepi/SLIM-ARC"`，于是指向 `/home/orangepi/SLIM-ARC/src/llama-upstream`。
但本项目实际布局中：
- `src/llama-upstream` 被 .gitignore（第 265 行）忽略，是**独立 git clone**，
  实际位于 `/home/orangepi/src/llama-upstream`（SLIM-ARC 仓库之外，在 `$HOME/src/` 下）。
- `/home/orangepi/SLIM-ARC/src/` 目录根本不存在。

这是环境布局与脚本假设不一致导致的路径 bug，属于 scripts/demo/* 脚本 bug，可修复。

**修复**：让 LLAMA_DIR 自动探测两种布局（标准仓库内布局 + 独立 clone 布局），
找不到标准路径时回退到 `$(dirname "$PROJECT_ROOT")/src/llama-upstream`。

---

## 问题 3：llama_cli_server.py 的 llama-cli 路径同样错误（备用方案）

**根因**：llama_cli_server.py 第 35-36 行
`PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent`（= SLIM-ARC），
`LLAMA_CLI = PROJECT_ROOT / "src/llama-upstream/build/bin/llama-cli"`
同样指向不存在的路径。备用方案（WSL2 bind bug 回退）也会失败。

**修复**：LLAMA_CLI 自动探测两种布局，标准路径不存在时回退到 `PROJECT_ROOT.parent / "src/llama-upstream/build/bin/llama-cli"`。

---

## 问题 4：Python 依赖缺失

**根因**：fastapi / uvicorn / requests 均未安装（系统 python3 无这些包）。

**修复**：`python3 -m pip install fastapi uvicorn requests`（默认 PyPI 源可用，
清华源不可用）。安装成功：fastapi 0.141.1, uvicorn 0.52.1, requests 2.34.2。
