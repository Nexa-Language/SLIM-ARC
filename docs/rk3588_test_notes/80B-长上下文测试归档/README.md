# RK3588 80B 大模型实验归档

- 整理日期：2026-08-07
- 项目负责人：欧阳易芃
- 归档范围：RK3588 端侧 80B 大模型实验（2026-08-06）+ 长上下文测试（2026-08-07）
- 数据性质：**真实端侧实测原生数据**，全程零代码修改（纯运行参数实验）

---

## 1. 归档背景

本项目（SLIM-ARC）核心价值主张是在内存受限环境运行远超内存的大模型。为验证该机制在**真实端侧**（非 WSL cgroup 模拟）的有效性，在 RK3588（8GB RAM）上完成：

1. **80B 实验（08-06）**：Qwen3-Next-80B-A3B Q4_K_M（45.09GiB）在 8GB 物理内存端侧加载与推理验证，确认 SLIM-ARC 机制（MADV_RANDOM/预取/KV eviction）触发。
2. **长上下文测试（08-07）**：`-c 1024→16384` 五阶段 26 组测试，验证长上下文大 KV cache 场景下 SLIM-ARC 是否体现价值。

## 2. 核心结论（摘要）

| 维度 | 结论 |
|:---|:---|
| 80B 可否在 8GB 端侧部署 | ✅ 可以（45GB mmap 按需分页，RSS 峰值 ~6.5GB < 8GB，无 OOM） |
| 无 SLIM-ARC 能否运行 | ✅ 能，且更快（上游 llama.cpp mmap 自带按需分页） |
| SLIM-ARC 性能收益 | ❌ 负优化（全开比禁用慢 3-4×，长上下文未改善） |
| 唯一正收益机制 | ✅ KV eviction（窄窗口降 RSS：6.34 < 6.49 GiB） |
| 与 x86 WSL 差异 | x86 WSL +437%（正收益）vs RK3588 -70%（负优化），根因是 baseline 环境与 ARM 算力差异 |

## 3. 目录结构

```
80B-长上下文测试归档/
├── README.md                          # 本说明文档
├── 过程日志.md                         # 测试执行过程日志（时间线/命令/阶段）
├── 评估文档.md                         # 与 x86 WSL 对比 + 项目意义评估
├── 计划/                              # 实验计划文档
│   ├── RK3588-SLIMARC-80B实验计划.md
│   └── RK3588-SLIMARC-80B长上下文测试计划.md
├── 报告/                              # 测试报告与性能分析
│   ├── RK3588-SLIMARC-80B测试报告-2026-08-06.md
│   ├── RK3588-SLIMARC-80B长上下文测试报告-2026-08-07.md
│   └── RK3588-SLIMARC-80B性能分析.md
└── 原生数据/                          # 全部实测原始数据
    ├── 汇总/                          # 各阶段结构化汇总表
    ├── bench矩阵/                     # llama-bench B1-B7 原始输出
    ├── 冒烟与TTFT/                    # 冒烟测试/首token延迟/verbose 原始输出
    ├── 长上下文LC/                    # LC1-LC26 全部原始日志+监控快照
    ├── madvise验证/                   # LD_PRELOAD 拦截 madvise 系统调用记录
    └── 环境与模型/                    # SSD 带宽、模型校验记录
```

## 4. 原生数据说明

### 4.1 长上下文 LC 文件命名规范

`raw-80b-lc-<编号>.txt` 及配套监控文件（位于 `原生数据/长上下文LC/`）：

| 后缀 | 内容 |
|:---|:---|
| `raw-80b-lc-N.txt` | 主输出日志（llama-bench/cli stdout+stderr） |
| `-rss.txt` | RSS 峰值监控结果（VmHWM） |
| `-vmstat.txt` | vmstat 持续采样（swap si/so） |
| `-pre/post-free.txt` | 测试前后 `free -h` 快照 |
| `-pre/post-vmstat.txt` | 测试前后 `/proc/vmstat` 快照 |
| `-dmesg.txt` | 测试后 dmesg 尾部（OOM 检查） |

### 4.2 测试组对照速查

| 阶段 | 上下文 | 组号 | 说明 |
|:---:|:---:|:---|:---|
| A | 1024 | LC1-4 | 基线复核（默认/DISABLE/NO_MADV/NO_PREFETCH） |
| B | 4096 | LC5-13 | 中上下文主矩阵（含 t8、cli 端到端） |
| C | 8192 | LC14-20 | 大上下文 + 长生成交叉点验证 |
| C+ | 16384 | LC21-23 | 超大上下文极限（含 KV q4_0） |
| D | 8192 | LC24-26 | KV eviction 专项（窄/宽窗口/无驱逐） |

### 4.3 核心数据文件

- `原生数据/汇总/longctx-summary.txt` —— 26 组测试全部指标汇总表
- `原生数据/汇总/bench-matrix-summary.txt` —— B1-B7 性能矩阵汇总
- `原生数据/madvise验证/madvise-trace-default.txt` —— SLIM-ARC MADV_RANDOM 触发证据
- `原生数据/环境与模型/ssd-bw-test.txt` —— SSD 带宽实测（读 2.1GB/s）

## 5. 复现指引

模型文件：`/home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf`
工具链：`/home/orangepi/src/llama-upstream/build/bin/`（llama-cli / llama-bench，版本 360e134 + SLIM-ARC 补丁）

```bash
# 示例：长上下文基准测试（默认 SLIM-ARC 全开）
llama-bench -m <MODEL> -p 512 -n 128 -t 4 -r 1 --no-warmup

# 示例：KV eviction 触发验证
SLIM_ARC_KV_EVICT=1 SLIM_ARC_KV_SINK=4 SLIM_ARC_KV_WINDOW=256 \
  llama-cli -m <MODEL> -c 8192 -n 256 -t 4 -p "<长prompt>" -st -no-cnv
```

> **注意**：llama-bench 不支持 `-c` 参数（用 `-p` 控制上下文规模）；llama-cli 支持 `-c`。

## 6. 关联文档

- 昨日小模型实验：[`RK3588-SLIMARC测试报告-2026-08-05.md`](../RK3588-SLIMARC测试报告-2026-08-05.md)（保留于上级目录）
- 项目 ROADMAP：[`../../ROADMAP.md`](../../ROADMAP.md)
