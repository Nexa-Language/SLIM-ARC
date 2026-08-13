
# 树莓派 4GB Pi5 全新设备安装清单

## 一、树莓派系统层面（在 SSH 终端执行）

### 1. 首次准备：开启 SSH（若还没开启）

```bash
# 方法一（图形）：sudo raspi-config → Interface Options → SSH → Enable
# 方法二（命令行）：
sudo systemctl enable --now ssh
```

### 2. 系统更新

```bash
sudo apt update && sudo apt full-upgrade -y
```

### 3. 安装 SLIM-ARC 核心依赖

```bash
sudo apt install -y build-essential cmake ninja-build git \
    python3 python3-pip python3-venv \
    curl wget unzip jq bc htop tree vim
```

| 包                  | 作用                                     |
| ------------------- | ---------------------------------------- |
| `build-essential` | gcc/g++/make（编译 llama.cpp 必需）      |
| `cmake`           | 树莓派 OS Bookworm 自带 3.25，满足 3.14+ |
| `ninja-build`     | 可选，加速编译                           |
| `git`             | 拉取 SLIM-ARC 和 llama.cpp               |
| `python3/pip`     | 运行`apply-slim-arc.py`、下载模型      |

### 4. Python 工具 + HuggingFace 下载器

树莓派 OS 的 Python 是"externally-managed"，**建议用 venv**（干净、不污染系统）：

```bash
python3 -m venv ~/slimarc-venv
source ~/slimarc-venv/bin/activate
pip install -U "huggingface_hub[cli]"
```

> 想省事直接装系统级：`pip install --break-system-packages -U "huggingface_hub[cli]"`

### 5. 内存/swap 优化（4GB 必做，否则编译会 OOM）

```bash
sudo nano /etc/dphys-swapfile        # 把 CONF_SWAPSIZE 改成 2048
sudo systemctl restart dphys-swapfile
sudo systemctl set-default multi-user.target   # 关桌面 GUI，省 ~0.5GB（重启生效）
# 恢复桌面：sudo systemctl set-default graphical.target
```

### 6.（可选）cgroup-tools —— 想模拟受限环境才需要

```bash
sudo apt install -y cgroup-tools
```

### 7. 验证环境

```bash
uname -m          # 必须是 aarch64
gcc --version && cmake --version
free -h           # 确认内存
df -h /           # 确认剩余空间 ≥10GB
```

---

## 二、VSCode 必备插件（PC 端安装）

### 核心（必装）

| 插件                                                | 插件 ID                               | 用途                                                     |
| --------------------------------------------------- | ------------------------------------- | -------------------------------------------------------- |
| **Remote - SSH**                              | `ms-vscode-remote.remote-ssh`       | 连接树莓派的核心                                         |
| **Remote - SSH: Editing Configuration Files** | `ms-vscode-remote.remote-ssh-edit`  | 编辑 SSH 配置                                            |
| **C/C++ Extension Pack**                      | `ms-vscode.cpptools-extension-pack` | 包含 C/C++ + CMake Tools + CMake（看/改 llama.cpp 源码） |
| **Python**                                    | `ms-python.python`                  | 看/改 Python 脚本                                        |

### 推荐（可选）

| 插件        | 插件 ID                     | 用途                                   |
| ----------- | --------------------------- | -------------------------------------- |
| GitLens     | `eamodio.gitlens`         | 看 git 提交历史/作者，配合本次同步操作 |
| Git History | `donjayamanne.githistory` | 图形化 git 日志                        |

### ARM 上 C/C++ 的建议（重要）

- 默认 C/C++（cpptools）在 ARM 上能用但偏重
- 更流畅的替代方案：装 **clangd** 插件（`llvm-vs-code-extensions.vscode-clangd`）+ 树莓派侧装 `sudo apt install clangd`
- 如果你只是"跑实验"不看 C++ 源码，装 C/C++ Extension Pack 就够了

---

## 三、VSCode 连接树莓派流程（关键机制）

1. PC 装好 **Remote-SSH** 后：`F1` → `Remote-SSH: Connect to Host...` → 输入 `用户名@树莓派IP`
2. VSCode **自动在树莓派上安装 vscode-server**（无需手动装）
3. **语言插件会自动同步安装到树莓派侧**（C/C++、Python 等随连接自动装到远端）
4. 连接后打开 `~/SLIM-ARC` 文件夹，VSCode 内置终端就是树莓派 SSH 终端，可边写边跑

---

## 四、装完后按上一轮的清单执行

```bash
cd ~
git clone https://github.com/Nexa-Language/SLIM-ARC.git
cd SLIM-ARC
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git src/llama-upstream
python3 scripts/apply-slim-arc.py
cd src/llama-upstream
cmake -B build -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2        # 4GB 内存必须 -j2
cd ../..
source ~/slimarc-venv/bin/activate
mkdir -p data/models
huggingface-cli download Qwen/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf --local-dir data/models
```

一句话总结：树莓派装 **git + build-essential + cmake + python + huggingface-cli + swap 扩到 2GB + 关桌面**；VSCode 装 **Remote-SSH + C/C++ Extension Pack + Python** 即可（clangd 是 ARM 上更流畅的替代）。
