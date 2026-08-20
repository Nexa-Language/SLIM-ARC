# 80B 模型加载失败修复记录

- **日期**: 2026-08-12
- **分支**: main (03ba926)
- **修复类型**: SLIM-ARC FIX 2026-08-12（符号链接，最小改动）

## 报错现象

```bash
scripts/demo/start-demo.sh 80b
```

llama-server 启动后立即退出：

```
E llama_model_load_from_file_impl: failed to load model
E cmn  common_init_: failed to load model '/home/orangepi/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf'
E srv    load_model: failed to load model, '/home/orangepi/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf'
E srv  llama_server: exiting due to model loading error
```

## 根因分析 (Root Cause)

- 脚本 [`scripts/demo/start-demo.sh`](../../scripts/demo/start-demo.sh) 与
  [`scripts/demo/llama_cli_server.py`](../../scripts/demo/llama_cli_server.py) 中
  80B 模型路径配置为：
  `/home/orangepi/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`
- 但该文件在仓库内 `data/models/` 目录下**不存在**。
- 实际 80B 模型（46GB，`Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`）位于**仓库外 SSD**：
  `/home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`

### data/models/ 目录验证（修复前）

```
-rw-rw-r-- 4.0G olmoe-1b-7b-0924-instruct-q4_k_m.gguf
-rw-rw-r-- 2.4G Qwen3-4B-Q4_K_M.gguf
# 无 Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
```

### SSD 目录验证

```
-rw-rw-r-- 46G /home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
```

## 修复方案（用户选择方案 A：不改代码，最小改动）

在 `data/models/` 下创建符号链接指向 SSD 上的实际模型文件：

```bash
ln -s /home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf \
      /home/orangepi/SLIM-ARC/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
```

## 修复验证

```
lrwxrwxrwx Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf -> /home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
GGUF 魔数校验: 4747 5546 = "GGUF" ✓
```

- 符号链接目标为有效 GGUF 模型文件。
- `.gitignore` 已忽略 `data/models/*.gguf`（第 235 行），符号链接不会被 git 跟踪，不污染仓库。

## 备注

- 未修改任何核心代码/脚本（符合 SLIM-ARC 红线规则：最小外科手术式改动）。
- 后续如需持久化该路径，可考虑修改脚本配置指向 SSD（方案 B，另行评估）。
