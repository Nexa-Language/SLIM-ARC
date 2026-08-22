# SLIM-ARC Maintenance Roadmap

本路线图记录比赛结束后的长期维护方向。比赛阶段的完整工程日志保存在
[docs/archive/ROADMAP-competition.md](docs/archive/ROADMAP-competition.md)。

## 2026-08-22 项目进入长期维护阶段

### 变更描述

- 以国家级一等奖最终成果为基线，整理开发入口、文档、Wiki、CI 和发布制品。
- 保留可复现实验、报告源码和完整 Git 历史，清除当前树中的模型、构建产物和内部协作资料。
- 后续工作聚焦论文补充、跨平台复现、正确性修复和有同合同证据的性能优化。

### 涉及文件

- `README.md`
- `docs/guide/`
- `docs/wiki/`
- `CONTRIBUTING.md`
- `.github/`

### 决策原因

- 比赛已经完成，仓库需要从短期交付状态切换到可长期维护和可在新设备恢复的公开项目。

## 后续优先级

1. 为完整系统论文补充更大规模质量评测和统一实验合同的跨设备重复实验。
2. 继续降低 Qwen3-Next 专家预测的额外 Router 计算与错误预取 I/O。
3. 完成 KV manager 与统一 Weight/KV/Expert 字节预算的端到端接线和消融。
4. 扩展 macOS Metal、Linux/aarch64 和原生 NVMe 平台的自动复现。
5. 对外 API、模型格式或实验 schema 发生变化时提供迁移说明并发布新版本。
