# Security Policy

## Supported versions

安全修复只面向最新 `main` 和最新 GitHub Release。比赛阶段历史版本保留用于研究追溯，
不再单独维护。

## Reporting a vulnerability

请使用 GitHub 仓库的 **Security → Report a vulnerability** 私下报告。报告应包含受影响提交、
复现步骤、影响范围和建议修复。不要在公开 Issue、日志或模型输出中发布密钥、个人数据或
可直接利用的细节。

SLIM-ARC 的实验脚本可能调用 shell、cgroup 和页缓存接口。运行前请审阅命令；项目不会要求
关闭系统安全机制或使用 `chmod 777`。
