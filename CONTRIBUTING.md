# Contributing to SLIM-ARC

感谢你帮助 SLIM-ARC 继续演进。项目优先接受可复现的性能优化、平台适配、正确性修复、
实验数据补充和论文/文档改进。

## 开发流程

1. 从最新 `main` 创建 `feat/<topic>`、`bug/<topic>` 或 `doc/<topic>` 分支。
2. 执行 `make bootstrap && make build && make test && make check`。
3. 在提交 PR 前 rebase 到最新 `main`，保持线性历史。
4. 填写 PR 模板；性能改动必须附上实验合同、基线、至少两次重复和原始证据路径。
5. 不得提交模型、构建目录、密钥、本机配置、PID、会话记录或绝对本机路径。

Commit Message 使用五段式格式：

```text
[feat/bug/doc/...] Do sth

Root cause: NA
Solution: Describe the change and design choice.
Risks: NA
Dependency: NA
Links: NA
```

`main` 只通过 PR 和 rebase 更新。请不要创建 merge commit 或 force push 共享分支。

## 性能证据要求

性能结果必须说明模型及 SHA-256、设备、操作系统、内存/CPU 约束、存储、缓存状态、
prompt、`pp/tg`、线程、量化、SLIM-ARC 配置和重复次数。不同实验合同的数据不得组合为
单一加速链。负结果同样有价值，请保留原始输出并说明边界。

## 许可证

提交代码即表示贡献按 Apache-2.0 授权。报告、图片或外部数据必须明确其来源和许可证。
