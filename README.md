<div align="center">

# SLIM-ARC

### Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization

面向内存受限端侧系统的 MoE 大模型推理运行时

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![OS Competition](https://img.shields.io/badge/OS%20Challenge-2026%20Proj%2059-cyan.svg)](https://gitlab.eduxiji.net/T2026105589911358/project3136859-389100)
[![School](https://img.shields.io/badge/Sun%20Yat--sen%20University-SYSU-purple.svg)](https://www.sysu.edu.cn/)

</div>

## 项目简介

SLIM-ARC 是中山大学参加 2026 全国大学生计算机系统能力大赛操作系统设计赛 Proj59 的作品。项目通过 mmap、阶段感知页建议、分层预取、MoE Router 反馈、专家驻留与回收、统一内存预算和 KV cache 管理，使远大于物理内存的 MoE 模型能够在端侧设备上运行。

系统保持模型权重和 Router 语义不变，主要优化数据何时进入页缓存、哪些页面应当保留，以及普通权重、专家和 KV cache 如何共享有限资源。

## 主要结果

| 平台与约束 | 模型 | 结果 |
|---|---|---|
| Mac/Colima，2 GiB，4 vCPU，no-swap | Qwen3-Next-80B-A3B Q4_K_M，48.41 GB | Prefill 3.908455 token/s，Decode 0.709095 token/s |
| RK3588，3 GiB cgroup，swap 0 | Qwen3-Next-80B-A3B Q4_K_M | Decode 0.70 → 2.21 token/s（3.16×） |
| Raspberry Pi 5，4 GiB，USB/FUSE，no-swap | Qwen3-Next-80B-A3B Q4_K_M | shared/hot 驻留使 Decode 提升 14.16%，wall time 缩短 6.58% |
| Raspberry Pi 5，16 MiB 预取预算 | 同上 | 投机 weight I/O 降低 98.44%，吞吐近似不变 |

详细实验合同、系统设计和数据见 [决赛技术报告](reports/Competition_Report_Official/main.pdf)。

## 系统设计

- **阶段感知页访问**：分别识别模型加载、Prefill、Decode 与 MoE Decode，并选择对应的 readahead 和预取窗口。
- **MoE 专家反馈闭环**：以 generation token 关联预测和实际 Router 选择，统计命中、浪费和成功建议字节。
- **安全页回收**：只处理完全位于专家切片内部的页面，避免触及相邻专家共享的边界页。
- **压力感知驻留**：依据 cgroup 压力、专家热度和浪费 EWMA 选择驻留集合。
- **统一资源预算**：协调普通权重、专家和 KV cache，限制后台 I/O 与在途字节。
- **模型所有权运行时**：通过租约和有界队列管理后台任务，保证映射地址的生命周期。

## 快速开始

```bash
git clone https://github.com/ggml-org/llama.cpp src/llama-upstream
python3 scripts/apply-slim-arc.py

cmake -S src/llama-upstream -B src/llama-upstream/build \
  -DGGML_CPU_REPACK=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build src/llama-upstream/build -j4
```

运行时开关和端侧配置位于 `config/` 与 `scripts/`。C++ 单元测试入口：

```bash
bash tests/run-cpp-unit.sh
```

## 目录结构

```text
patches/llama-upstream/       SLIM-ARC 的独立 C++ 模块
scripts/apply-slim-arc.py     可重复应用的 llama.cpp 集成脚本
scripts/macos/                Mac/Colima 受限内存实验工具
tests/                        C++ 与 Python 测试
config/                       运行时和实验配置
reports/Competition_Report_Official/  决赛技术报告
```

## 项目信息

- 比赛：2026 全国大学生计算机系统能力大赛操作系统设计赛
- 赛题：Proj59 内存受限环境的大语言模型推理优化
- 学校：中山大学
- 成员：欧阳易芃、马福泉、刘昊
- 指导教师：赵帅、张献伟
- 演示视频：[Bilibili P2](https://www.bilibili.com/video/BV1fXTF6HEAw?p=2)

## License

[MIT License](LICENSE)
