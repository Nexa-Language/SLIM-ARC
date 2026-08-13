
# 结论：部分可行，且只能跑小模型

在 **4GB 主存的树莓派** 上运行 SLIM-ARC，**技术上可以编译，但只能跑最小的 Qwen3-4B 模型；项目主打的 80B 成果在 4GB 树莓派上完全不可行**。下面是详细依据与完整操作步骤。

---

## 一、为什么"部分可行"

### 1. 项目目标环境（来自 [`README.md`](README.md:82)）

- CPU: **x86-64（AVX2 + AVX_VNNI 推荐）**
- RAM: **8–32 GB**（三档 cgroups 隔离）
- 存储: **NVMe SSD（~3.5 GB/s）**

树莓派 4（4GB）是 ARM Cortex-A72（aarch64）、microSD/eMMC 存储，与目标环境差异巨大。

### 2. 代码层面：兼容 ✅

- llama.cpp 官方支持 ARM NEON，可在 aarch64 上编译
- 我检索了 [`patches/`](patches/) 全部 SLIM-ARC 源码，**没有任何 x86 专属指令**（无 `__AVX__`/`_mm_`/`__x86_64__`），全部是 POSIX 标准接口：`mmap`、`posix_madvise(MADV_RANDOM/WILLNEED)`、`mlock`、`std::thread`、读 `/sys/fs/cgroup/memory.max` 等（见 [`slim-arc-prefetch.h`](patches/llama-upstream/slim-arc-prefetch.h:21)、[`apply-slim-arc.py`](scripts/apply-slim-arc.py:64)）
- 所以**编译能通过**，但 ARM 没有 AVX2/VNNI，计算速度远低于开发机

### 3. 内存/存储层面：三个模型逐一评估 ❌

| 模型                  | 文件大小 | 4GB 树莓派可行性               | 原因                                                                                       |
| --------------------- | -------- | ------------------------------ | ------------------------------------------------------------------------------------------ |
| Qwen3-Next-80B IQ4_XS | 39.7 GB  | **不可行**               | 文件 40GB + microSD 读写仅 10~50MB/s（项目依赖 3.5GB/s NVMe），MADV 按需加载在慢盘上会卡死 |
| OLMoE-1B-7B Q4_K_M    | 3.9 GB   | **基本不可行**           | 模型文件≈整机内存，OS 就要分走 ~1GB，必然疯狂 swap                                        |
| Qwen3-4B Q4_K_M       | 2.4 GB   | **可行（唯一现实选择）** | 权重 2.4GB + KV cache(q4_0/短上下文) + 无头 OS ≈ 3.2~3.5GB，勉强在 4GB 内                 |

### 4. 必须诚实说明的一点

核心优化 `MADV_RANDOM` 只对 **>6GB 的模型** 生效（见 [`apply-slim-arc.py`](scripts/apply-slim-arc.py:95) 的 `msz > (6ULL << 30)` 判断）。所以用 Qwen3-4B 在树莓派上跑，**SLIM-ARC 的核心创新（MoE 按需加载）根本不会触发**，本质就是"llama.cpp + KV q4_0 + FlashAttention"的小模型推理。80B 的 64.5× 加速只能在原开发机（x86 + NVMe）上演示。

**建议定位**：4GB 树莓派作为"小模型端侧推理"的补充 demo，80B 成果继续用开发机展示。

---

## 二、操作步骤（所有命令在树莓派 SSH 会话中执行）

> 前提假设：你的 PC 通过 SSH 连到了树莓派，下面每条命令都输入在树莓派终端里。**是的，树莓派需要装 git，并需要 git clone 拉取，而不是把 PC 上的项目文件拷过去。**

### Step 0：确认系统（先检查环境）

```bash
uname -m          # 必须是 aarch64/arm64；若是 armv7l 则 32 位系统，需重装 64 位
cat /etc/os-release
free -h           # 确认 4GB
nproc
df -h /           # 确认存储剩余空间（建议 ≥10GB）
```

### Step 1：安装依赖（含 git）

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build git python3 python3-pip jq bc
```

### Step 2：拉取 SLIM-ARC 仓库（这就是"拉取"）

```bash
git clone https://github.com/Nexa-Language/SLIM-ARC.git
cd SLIM-ARC
# 如果 GitHub 访问慢，可用比赛 GitLab：
# git clone https://gitlab.eduxiji.net/T2026105589911358/project3136859-389100.git
```

> 注意：模型文件（`data/models/`）在 `.gitignore` 里**不在仓库中**，需单独下载（见 Step 5）。

### Step 3：克隆 upstream llama.cpp 并应用 SLIM-ARC 补丁

```bash
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git src/llama-upstream
python3 scripts/apply-slim-arc.py
```

### Step 4：编译（4GB 内存的关键坑）

```bash
cd src/llama-upstream
cmake -B build -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2      # 必须 -j2 甚至 -j1，多核并行编译极易 OOM
cd ../..
```

> 若编译仍 OOM，先扩容 swap：`sudo nano /etc/dphys-swapfile` 把 `CONF_SWAPSIZE` 调到 2048，再 `sudo systemctl restart dphys-swapfile`。

### Step 5：下载模型（只要 Qwen3-4B Q4_K_M，约 2.4GB）

```bash
mkdir -p data/models
# 方式一：huggingface-cli
pip install -U "huggingface_hub[cli]"
huggingface-cli download Qwen/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf \
    --local-dir data/models
# 方式二：直接下 GGUF 文件（若 HFace 被墙，从 ModelScope 下载后改名放入 data/models/）
```

> 千万别在 4GB 树莓派上下 80B（40GB 文件 + 慢盘）。

### Step 6：（可选）cgroups v2 模拟受限环境

树莓派 OS Bookworm 默认 cgroups v2，可创建更低的 3GB 档位：

```bash
sudo mkdir -p /sys/fs/cgroup/slim-arc-pi
echo 3221225472 | sudo tee /sys/fs/cgroup/slim-arc-pi/memory.max
```

运行时套用：

```bash
sudo cgexec -g memory:cgroup.slim-arc-pi bash -c '...运行命令...'
```

### Step 7：运行 Qwen3-4B

```bash
LD_LIBRARY_PATH=src/llama-upstream/build/bin ./src/llama-upstream/build/bin/llama-cli \
    -m data/models/Qwen3-4B-Q4_K_M.gguf \
    -t 4 -c 256 -ctk q4_0 -ctv q4_0 -fa auto -p "The capital of China is"
```

---

## 三、直接回答你的问题

**"是不是还得安装 git，拉取等？"** —— 是，四步都要：

1. **装 git**（以及 build-essential/cmake 等，见 Step 1）
2. **git clone SLIM-ARC 仓库**（Step 2）
3. **git clone llama.cpp + `apply-slim-arc.py` 打补丁**（Step 3）
4. **cmake 编译 + 单独下载模型文件**（Step 4、5）

不要把 PC 上的工程目录通过 scp 整目录拷贝——直接让树莓派 `git clone` 更干净；只有模型 GGUF 文件大、下载慢，可以考虑 U 盘/移动硬盘拷贝，或用国内镜像（ModelScope）。

## 四、注意事项（坑）

1. **必须是 64 位系统**：树莓派 OS 要装 64-bit（arm64）版本，32 位跑不了现代 llama.cpp
2. **编译内存**：4GB 内存编译必须 `-j2` + 加大 swap，否则 GCC 并行编译直接 OOM
3. **存储介质是最大瓶颈**：microSD 太慢，强烈建议用 USB3 移动硬盘/SSD 启动系统，否则即使小模型预填充也很慢
4. **关掉桌面省内存**：`sudo raspi-config` → 关 GUI，或 `systemctl isolate multi-user.target`，无头模式能多省 ~0.5GB
5. **推荐硬件升级**：若条件允许，用树莓派 5（8GB）会更从容，Qwen3-4B 可流畅跑，OLMoE-1B-7B 也勉强可行
6. 开发机的 WSL2 网络 Bug（[`ROADMAP.md`](ROADMAP.md:5)）与树莓派无关，不影响这里

**一句话总结**：4GB 树莓派可以编译运行 SLIM-ARC 的代码栈，但只适合演示 Qwen3-4B 小模型端侧推理；项目核心的 80B MoE 内存优化成果必须在 x86 + NVMe 的开发机上展示，树莓派装不下也跑不动。
