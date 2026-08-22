# Architecture

SLIM-ARC 由阶段感知页访问、专家反馈闭环、安全页回收、压力感知驻留、统一资源预算、
KV cache 管理和模型所有权运行时组成。独立模块保存在 `patches/llama-upstream/`，集成器
把它们安装到固定 llama.cpp revision。

详细设计见 `docs/design/` 和决赛技术报告第 3 章。
