# Development Guide

SLIM-ARC 将独立模块放在 `patches/llama-upstream/`，由
`scripts/apply-slim-arc.py` 集成到固定 llama.cpp checkout。不要直接把上游源码树提交
到本仓库。

```bash
make bootstrap
make build
make test
make check
```

新增运行时行为时，应同时增加 `tests/cpp/` 中的单元测试和 `tests/run-cpp-unit.sh`
allowlist。修改集成 seam 时，必须验证 patch 首次应用和重复应用。提交规范与性能证据要求
见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。
