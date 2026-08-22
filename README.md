<div align="center">

<img src="assets/slim-arc-logo.png" alt="SLIM-ARC Logo" width="116" />

# SLIM-ARC

### Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization

面向内存受限端侧系统的 MoE 大模型推理运行时

[![CI](https://github.com/Nexa-Language/SLIM-ARC/actions/workflows/ci.yml/badge.svg)](https://github.com/Nexa-Language/SLIM-ARC/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/code-Apache--2.0-blue.svg)](LICENSE)

<img src="assets/slim-arc-readme-cover.png" alt="SLIM-ARC memory-aware MoE inference runtime" width="100%" />

[项目官网](https://slim.nexa-lang.com/) ·
[技术报告](reports/Competition_Report_Finals/main.pdf) ·
[最终答辩材料](reports/SLIM-ARC_FINAL.pdf) ·
[Wiki](https://github.com/Nexa-Language/SLIM-ARC/wiki) ·
[Release](https://github.com/Nexa-Language/SLIM-ARC/releases)

</div>

## 项目简介

SLIM-ARC 是中山大学参加 2026 年全国大学生计算机系统能力大赛操作系统设计赛
Proj59“内存受限环境的大语言模型推理优化”的作品。系统通过 mmap 按需加载、阶段感知
页建议、MoE 专家预测与回收、压力感知驻留、统一 I/O 预算和 KV cache 管理，让模型体积
远大于物理内存的 MoE 模型能够在 x86、RK3588、Raspberry Pi 和 macOS 等平台运行。

SLIM-ARC 不改变模型权重和 Router 语义，重点决定数据何时进入页缓存、哪些页面应当
保留，以及普通权重、专家和 KV cache 如何共享有限内存。完整设计、实现和实验边界见
[决赛技术报告](reports/Competition_Report_Finals/main.pdf) 与
[结果证据索引](docs/results/README.md)。

## 代表性结果

| 平台与约束 | 模型 | 同合同结果 |
|---|---|---|
| x86/WSL，8 GiB cgroup | Qwen3-Next-80B-A3B | Decode 0.08 → 0.43 token/s（+437.5%） |
| x86/WSL，32 GiB，warm cache | Qwen3-Next-80B-A3B IQ4_XS | FlashAttention 消融 3.01 → 5.16 token/s（+71.4%） |
| RK3588，3 GiB cgroup，swap 0 | Qwen3-Next-80B-A3B Q4_K_M | Decode 0.70 → 2.21 token/s（3.16×） |
| Mac/Colima，2 GiB，4 vCPU，no-swap | Qwen3-Next-80B-A3B Q4_K_M | Prefill 3.908、Decode 0.709 token/s |
| Raspberry Pi 5，4 GiB，no-swap | Qwen3-Next-80B-A3B Q4_K_M | shared/hot 驻留使 Decode 提升 14.16% |
| Raspberry Pi 5，16 MiB 预算 | 同上 | 投机 weight I/O 降低 98.44%，吞吐近似不变 |

不同设备、缓存状态和负载不可直接串联为单一加速比。表中的每一项都指向仓库内可追溯
实验记录，复现时必须使用相同模型、prompt、`pp/tg`、缓存状态和资源约束。

## 系统设计

- **阶段感知页访问**：区分模型加载、Prefill、Decode 和 MoE Decode，选择不同的
  readahead、预取窗口和页面建议。
- **专家反馈闭环**：以 generation token 关联预测与 Router 实际选择，统计命中、浪费、
  结算和回收。
- **安全页回收**：只回收完全位于专家切片内部的页面，避免破坏相邻专家共享边界页。
- **压力感知驻留**：依据 cgroup 压力、专家热度和浪费 EWMA 管理有限驻留集。
- **统一资源预算**：协调普通权重、专家和 KV cache，限制后台 I/O 和在途字节。
- **模型所有权运行时**：通过租约与有界队列管理异步任务，保证 mmap 生命周期安全。

## 一分钟进入开发

依赖：Git、CMake、C++17 编译器、Python 3.10+ 和
[`uv`](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/Nexa-Language/SLIM-ARC.git
cd SLIM-ARC
make bootstrap
make build
make test
```

`make bootstrap` 会把 llama.cpp 固定到提交
`360e1349f0009c5ad99d21e3c4546b707addc68a`，克隆到被忽略的
`src/llama-upstream`，幂等应用 SLIM-ARC patch 并生成 Release 构建配置。该过程不下载模型。

常用入口：

```bash
make check       # shell、Python 与公开树检查
make docs        # 重建决赛报告
make clean       # 仅清理可再生构建/缓存
bash tests/run-cpp-unit.sh list
```

模型准备、环境变量和受限内存实验方法见
[Getting Started](docs/guide/getting-started.md) 与
[Model Artifacts](docs/guide/model-artifacts.md)。

## 目录结构

```text
patches/llama-upstream/          独立的 SLIM-ARC C++ 运行时模块
scripts/apply-slim-arc.py        可重复应用的 llama.cpp 集成器
scripts/bootstrap-dev.sh         固定上游版本的一键开发入口
config/                          运行时和实验配置
tests/                           C++、Python 与平台测试
docs/results/                    结构化结果与原始证据入口
docs/wiki/                       GitHub Wiki 的权威来源
reports/Competition_Report_Finals/  决赛长版报告与 LaTeX 源码
site/                            GitHub Pages 项目主页
```

## 报告、答辩与视频

- [41 页决赛技术报告](reports/Competition_Report_Finals/main.pdf)
- [39 页最终答辩 PDF](reports/SLIM-ARC_FINAL.pdf)
- [最终答辩 PPTX](reports/SLIM-ARC_FINAL.pptx)
- [项目全景总结](reports/SLIM-ARC-project-overview.pdf)
- [项目简介视频](https://www.bilibili.com/video/BV1fXTF6HEAw/)
- [决赛答辩视频](https://www.bilibili.com/video/BV1iHbB6CEPb/)

更多媒体入口见 [docs/media.md](docs/media.md)。

## 参与贡献

项目比赛阶段已经结束，但仍接受复现修正、平台适配、论文补充和可验证的性能优化。
提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和
[SECURITY.md](SECURITY.md)。性能 PR 必须同时给出基线、实验合同、原始数据和结果分析，
不接受只报告最佳单次数字的结论。

## 团队与引用

- 成员：欧阳易芃、马福泉、刘昊
- 指导教师：赵帅、张献伟
- 学校：中山大学

引用格式见 [CITATION.cff](CITATION.cff) 和 [Citation Wiki](docs/wiki/Citation.md)。

## 许可证

代码采用 [Apache License 2.0](LICENSE)。比赛报告及其 LaTeX/图表材料按各报告目录中的
CC BY 4.0 声明发布；第三方论文、模型和上游项目保持各自许可证。详见
[许可证矩阵](docs/licensing.md) 与 [NOTICE](NOTICE)。模型权重不随仓库分发。
