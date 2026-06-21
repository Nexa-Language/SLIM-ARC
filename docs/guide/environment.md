# SLIM-ARC 环境配置

## 1. 硬件环境

### 1.1 开发机

- **CPU**: Intel i9-13900H（14 核 20 线程）
- **RAM**: 32GB（WSL2 分配）
- **GPU**: NVIDIA RTX 4060 Laptop（**不使用**，保持纯 CPU）
- **存储**: NVMe SSD（WSL2 原生 ext4）
- **OS**: Ubuntu 22.04 (WSL2)
- **Shell**: Zsh

### 1.2 受限环境（三档 cgroups v2 隔离）

| 档位 | 内存上限 | CPU 核数 | 模拟场景 | cgroup 路径 |
|------|---------|---------|---------|------------|
| Low | 8 GB | 4 核 | 中端手机/嵌入式 | `/sys/fs/cgroup/slim-arc-low` |
| Mid | 12 GB | 6 核 | 高端手机/轻量 PC | `/sys/fs/cgroup/slim-arc-mid` |
| High | 16 GB | 8 核 | 现代 PC/端侧服务器 | `/sys/fs/cgroup/slim-arc-high` |

## 2. 软件依赖

### 2.1 系统包

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build git \
    cgroup-tools cgroup-bin \
    python3 python3-pip python3-venv \
    perf strace \
    jq bc
```

### 2.2 Python 依赖

使用 `uv` 管理（全局规则要求）:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## 3. cgroups v2 配置

### 3.1 创建三档 cgroup

```bash
# 脚本: scripts/env/setup-cgroups.sh
sudo cgcreate -g memory,cpu:/slim-arc-low
sudo cgcreate -g memory,cpu:/slim-arc-mid
sudo cgcreate -g memory,cpu:/slim-arc-high

# 内存限制
echo 8589934592  | sudo tee /sys/fs/cgroup/slim-arc-low/memory.max
echo 12884901888 | sudo tee /sys/fs/cgroup/slim-arc-mid/memory.max
echo 17179869184 | sudo tee /sys/fs/cgroup/slim-arc-high/memory.max

# CPU 核数限制（通过 cpuset）
echo "0-3"   | sudo tee /sys/fs/cgroup/slim-arc-low/cpuset.cpus
echo "0-5"   | sudo tee /sys/fs/cgroup/slim-arc-mid/cpuset.cpus
echo "0-7"   | sudo tee /sys/fs/cgroup/slim-arc-high/cpuset.cpus
echo "0"     | sudo tee /sys/fs/cgroup/slim-arc-low/cpuset.mems
echo "0"     | sudo tee /sys/fs/cgroup/slim-arc-mid/cpuset.mems
echo "0"     | sudo tee /sys/fs/cgroup/slim-arc-high/cpuset.mems
```

### 3.2 运行受限程序

```bash
# 在 Low 档位下运行
sudo cgexec -g memory,cpu:slim-arc-low \
    ./src/flexinfer/host/bin/flexinfer-cli \
    -m data/models/qwen3-4b-q4_k_m.gguf \
    -p "I believe the meaning of life is" \
    -n 64 -t 4 -c 512 -am 2 -tp 1
```

### 3.3 清除缓存（冷启动测试）

```bash
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
```

## 4. 代理配置

外部网络请求通过 `http://127.0.0.1:7897`:

```bash
# 已在 shell rc 中配置，如未生效则手动 export
export http_proxy=http://127.0.0.1:7897
export https_proxy=http://127.0.0.1:7897
export no_proxy=localhost,127.0.0.1
```

## 5. FlexInfer 编译

```bash
cd src/flexinfer
bash build-host.sh
# 产物: src/flexinfer/host/bin/{flexinfer-cli, flexinfer-bench, llama-cli, llama-bench}
```

## 6. 模型下载与转换

### 6.1 下载 HF 模型

```bash
# Qwen3-4B
huggingface-cli download Qwen/Qwen3-4B --local-dir data/hf-models/qwen3-4b

# Qwen3-Next-A3B
huggingface-cli download Qwen/Qwen3-Next-A3B --local-dir data/hf-models/qwen3-next-a3b
```

### 6.2 转换为 4096 对齐 GGUF

FlexInfer Direct I/O 要求张量 4096 字节对齐:

```bash
# 使用 FlexInfer 自带脚本
cd src/flexinfer
bash scripts/convert-hf-models.sh \
    ../../data/hf-models/qwen3-4b \
    ../../data/models/qwen3-4b-q4_k_m.gguf

bash scripts/convert-hf-models.sh \
    ../../data/hf-models/qwen3-next-a3b \
    ../../data/models/qwen3-next-a3b-q4_k_m.gguf
```

**注意**: 若 FlexInfer 不支持 Qwen3-Next 架构，需从最新 llama.cpp backport 架构定义。

## 7. Benchmark 数据集

```bash
# Wikitext-103
bash src/flexinfer/scripts/get-wikitext-103.sh

# HellaSwag
bash src/flexinfer/scripts/get-hellaswag.sh

# C4 和长上下文 prompt 集会放在 data/benchmarks/ 下
```

## 8. 验证环境

```bash
# 验证 cgroup
cgexec -g memory,cpu:slim-arc-low cat /proc/self/cgroup

# 验证内存限制
cgexec -g memory,cpu:slim-arc-low python3 -c "import os; print(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES'))"

# 验证 FlexInfer
./src/flexinfer/host/bin/flexinfer-cli --version
```
