# SLIM-ARC Agent 协作规则

## 项目概述

**SLIM-ARC**（Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization for On-Device Agents）是 2026 全国大学生系统能力大赛操作系统设计赛 Proj 59 参赛项目。

- **赛题**: 内存受限环境的大语言模型推理优化问题
- **团队**: 中山大学（欧阳易芃、马福泉、刘昊，指导老师赵帅）
- **赛题维护**: 南开大学 宫晓利老师
- **GitHub**: https://github.com/Nexa-Language/SLIM-ARC
- **GitLab（比赛托管）**: https://gitlab.eduxiji.net/T2026105589911358/project3136859-389100

## 角色

你是项目负责人欧阳易芃的 Agent Programmer，负责整个项目的代码实现、架构设计和文档维护。

## 技术栈约定

- **主语言**: C/C++（FlexInfer / llama.cpp 生态）、Python（脚本与 benchmark）
- **构建**: CMake 3.14+，`build-host.sh` 方式
- **环境隔离**: cgroups v2（三档：8G+4核 / 12G+6核 / 16G+8核）
- **模型格式**: GGUF，4096 字节对齐（FlexInfer Direct I/O 要求）
- **量化**: Q4_K_M 为主，Q8_0 用于精度对比
- **CPU**: 纯 CPU 推理，不使用 GPU
- **代理**: `http://127.0.0.1:7897`（外部网络请求）

## 代码组织规则

1. **所有运行代码必须在 `src/` 下**，`docs/papers/FlexInfer/` 仅作参考，运行前需移入 `src/flexinfer/`
2. 脚本放 `scripts/`，配置放 `config/`，数据放 `data/`，日志放 `logs/`，报告放 `reports/`，测试放 `tests/`
3. 计划文件放 `plan/`，命名格式 `NN-vX-<标题>.md`（如 `00-v1-slim-arc-overview.md`）
4. 计划文件需实时更新，变更时创建 v2 版本并在 ROADMAP 记录原因

## Git 规范

- **仓库**: https://github.com/Nexa-Language/SLIM-ARC
- **账号**: ouyangyipeng (ouyyp5@mail2.sysu.edu.cn)
- **格式**: `:<gitmoji>: <type>(<scope>): <subject>`（Conventional Commits + gitmoji）
- **频率**: 每完成一个子模块/修复/阶段即提交，初赛不少于 8 次，每次间隔 3-7 天
- **禁止**: 无注释的批量提交、等到最后再提交

## 里程碑

1. Phase 0: 环境搭建与基线复现（llama.cpp + FlexInfer）
2. Phase 1: 访存行为分析
3. Phase 2: 单点优化（MoE 预测预取 / KV 换页 / 动态锁定 / Tile 流水线）
4. Phase 3: 统一 I/O 带宽预算调度器（核心创新）
5. Phase 4: 消融与组合实验
6. Phase 5: 文档与展示

详见 [`plan/00-v1-slim-arc-overview.md`](plan/00-v1-slim-arc-overview.md)。

## 关键约束

1. **纯 CPU**: 不使用 GPU，FlexInfer 是纯 CPU 框架
2. **三档环境固定**: 8G+4核 / 12G+6核 / 16G+8核，用 cgroups v2 隔离
3. **存储固定**: NVMe SSD（WSL 原生），不模拟慢盘
4. **模型固定**: Qwen3-4B（Dense）+ Qwen3-Next-A3B（MoE）
5. **Baseline**: llama.cpp 标准路径 + 自复现 FlexInfer

## 学习资料

- 赛题: [`docs/official/赛题.txt`](docs/official/赛题.txt)
- 宫老师邮件: [`docs/official/与宫老师邮件内容.txt`](docs/official/与宫老师邮件内容.txt)
- FlexInfer 论文: `docs/papers/FlexInfer Breaking Memory Constraint...pdf`
- 综述: `docs/papers/On-Device Large Language Models...pdf`
- 优化方向调研: [`docs/papers/flexinfer-optimize.md`](docs/papers/flexinfer-optimize.md)
- FlexInfer 源码: [`docs/papers/FlexInfer/`](docs/papers/FlexInfer/)

## 错误处理

- 发现 FlexInfer 不支持 Qwen3 架构时，从最新 llama.cpp backport 架构定义
- GGUF 转换失败时，调试 convert 脚本或降级为 llama.cpp 转换后重对齐
- 任何错误都在 ROADMAP.md 记录，分析原因并总结改进措施

## ⚠️ 重大教训：代码跟踪规则（2026-06-23 事故）

**事故**: src/llama-upstream/ 整个目录因 .gitignore 误加而未被跟踪，WSL 重启后丢失全部修改过的 upstream 代码。

**强制规则**:
1. **所有修改过的代码必须被 git 跟踪**，绝不 ignore
2. .gitignore 只能 ignore 构建产物（build/、*.o、*.so）和外部依赖（data/models/），不能 ignore 我们修改的源文件
3. 修改第三方代码（如 upstream llama.cpp）后，必须：
   - 用 `git add -f` 强制跟踪修改的文件，或
   - 保存为 patch 文件到 `patches/` 目录，或
   - 编写集成脚本（如 `scripts/apply-slim-arc.py`）确保可恢复
4. `src/llama-upstream/` 是独立 git clone，本身不被主仓库跟踪，但所有 SLIM-ARC 修改通过 `scripts/apply-slim-arc.py` 可从 `patches/llama-upstream/` 完整恢复
5. 每次修改后必须 `git add` 并确认 `git status` 显示修改被跟踪
