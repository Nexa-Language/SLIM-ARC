# 团队分支主线集成计划 v2

## 目标

将 `haoma` 的完整实现历史与归档分支中的有效比赛资料，以线性历史直接交付到远端 `main`，最终只使用一个展示主分支。

## 变更原因

仓库所有者进一步明确要求不创建远端集成分支或 PR，直接合入并推送 `main`。因此 v2 用直接 push 取代 v1 的 feature branch、PR 和 rebase merge 步骤，同时继续遵守“无 merge commit”的线性历史要求。

## 前置条件

- [x] 原远端 `main` 固定为 `12aaa96996c32502ff3054062073cde54e9983fa`。
- [x] `haoma` 固定为 `51888799d006ac53475aa1d51cadfd348c42a021`，相对原 `main` ahead 6、behind 0。
- [x] 归档分支固定为 `ca40272ff7f5a5a60ce8f7cbf71f2504fae8c326`，相对原 `main` ahead 13、behind 0。

## 步骤拆解

- [x] 使用 partial fetch 获取两个队友分支，避免无条件下载生成物。
- [x] 将本地集成记录 rebase 到 `haoma`，线性保留其全部 6 个提交。
- [x] 从归档分支导入 `b62cb0c` 中的 9 篇论文和 26 份计划/审计文档。
- [x] 排除第三方源码镜像、`build/`、`build-host/` 与 `node_modules/` 批次。
- [x] 添加固定 SHA、纳入范围与排除范围的集成清单。
- [x] 验证提交 ancestry、工作树、关键接口、脚本语法与可用测试。
- [x] 直接 push 本地 `main` 到远端 `main`。
- [x] 重新读取远端 `main`，确认推送 SHA 和工作区状态。

## 验收标准

- `main` 在线性历史中包含 `haoma` 的全部 6 个提交和选定归档资料。
- 不产生 merge commit，不创建额外远端集成分支。
- 主仓库不新增构建目录、依赖目录或完整第三方源码镜像。
- `scripts/apply-slim-arc.py` 所需 prefetch 接口在补丁实现中存在。
- 可用自动化检查通过；硬件/模型依赖测试的未执行范围明确记录。
- 远端 `main` 与本地 `main` 指向同一最终提交。

## 风险

- RK3588 与 x86/macOS 对 `MADV_RANDOM` 的性能方向可能不同，集成不扩大现有实验结论的适用范围。
- 9 篇参考论文使仓库增加约 24 MB，但它们属于已确认保留的比赛资料。
- 当前机器没有 RK3588、80B GGUF 模型或对应 Linux cgroup 环境，无法重放硬件性能实验。
