# Pi5 重测环境快照（2026-08-13）

> 工作线：树莓派 5（本机 `yituodabian`）。与 WSL x86/macOS、RK3588 两条工作线数据严格区分存放。

## 设备与系统

| 项 | 值 |
|:---|:---|
| 设备 | 树莓派 5（Pi5），4GB RAM |
| CPU | 4 核 Cortex-A76，aarch64；无 AVX2 / SVE / i8mm；有 crc32 / crypto / dotprod |
| 内核 | 6.18.34+rpt-rpi-2712 |
| 系统 | Debian（trixie 系），gcc 14.2.0 / cmake 3.31.6 |
| 内存 | 4.0 GiB 总；swap 2.0 GiB（zram） |
| cgroup2 | 挂载于 /sys/fs/cgroup；controllers = `cpuset cpu io pids` |
| cgroup memory | **被内核启动参数 `cgroup_disable=memory` 禁用**（CONFIG_MEMCG=y 但未激活），`/sys/fs/cgroup/memory.max` 不存在 |

## 存储

| 挂载 | 文件系统 | 容量 | 可用 | 备注 |
|:---|:---|:---:|:---:|:---|
| `/`（microSD） | ext4 | 29G | 11G | buffered 读约 96.3 MB/s（含 page cache 命中，物理裸读远低） |
| `/home/yituodabian/data`（USB3 移动硬盘） | **NTFS-3G（FUSE）** | 932G | 804G | buffered 读约 269 MB/s |

> 80B 模型位于 NTFS-3G（FUSE）文件系统上，`mmap + posix_madvise` 语义待验证。

## 模型

| 模型 | 路径 | 大小 | 状态 |
|:---|:---|:---:|:---|
| Qwen3-4B-Q4_K_M.gguf | data/models/（microSD） | 2,497,280,256 B | 可直接运行 |
| Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf | data/models/（软链 → /home/yituodabian/data/，NTFS USB3） | 48,410,988,384 B | 待探测 |

## 构建产物

- llama-cli：version 106 (70dfba5)，GNU 14.2.0，Linux aarch64，built 2026-08-12 00:45
- llama-bench：built 2026-08-12 00:41
- SLIM-ARC 补丁文件（12 个）已注入 src/llama-upstream/src/

## 本次测试范围与红线

1. 阶段1：Qwen3-4B 全矩阵重测（raw 留痕 + 统计）
2. 阶段3：80B 沿 RK3588 路线探测（不修改核心机制代码）
3. 数据仅写入 `docs/pi5_4GB_test_notes/2026-08-13-rerun/`
