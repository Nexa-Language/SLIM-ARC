# 团队分支主线集成计划

## 目标

将 `haoma` 与 `agent/upload-local-sources-and-papers` 中适合最终展示的成果以线性历史集成到 `main`，形成单一、可演示、可追溯的决赛主线。

## 前置条件

- 仓库所有者已授权按推荐方式集成并直接提交。
- `haoma` 相对 `main` 为 6 个提交 ahead、0 behind，可作为实现基线。
- 归档分支相对 `main` 为 13 个提交 ahead、0 behind，但包含大量构建产物、`node_modules` 与完整第三方源码快照。
- 集成过程禁止产生 merge commit；通过 feature branch、PR 与 rebase merge 保持线性历史。

## 步骤拆解

- [ ] 从 `haoma@51888799d006ac53475aa1d51cadfd348c42a021` 创建 `feat/integrate-team-branches`。
- [ ] 保留 `haoma` 的 RK3588 实验、prefetch 修复、动态策略与 demo UI 改动。
- [ ] 从归档分支选择项目计划、论文资料和归档说明。
- [ ] 排除 `build/`、`build-host/`、`node_modules/`、编译产物及完整第三方仓库镜像。
- [ ] 补充归档清单，记录来源分支、固定 SHA、纳入范围与排除原因。
- [ ] 核验分支 ancestry、文件差异、关键接口一致性和可用测试。
- [ ] 创建 ready PR，使用 rebase merge 合入 `main`。
- [ ] 核验远端 `main` 最终 SHA 与分支状态。

## 验收标准

- `main` 线性包含 `haoma` 的全部 6 个提交及选定归档资料。
- 主仓库不新增构建目录、依赖目录或第三方源码镜像。
- `scripts/apply-slim-arc.py` 使用的 prefetch 接口在补丁头文件中均有定义。
- 可用自动化检查通过；未能执行的硬件/模型测试被明确记录。
- PR 以 rebase 方式成功合入，远端默认分支保持 `main`。

## 风险

- 当前本机无法通过普通 Git/HTTPS 访问 GitHub，需要使用 GitHub 仓库连接器完成远端对象操作；因此以远端差异和 Actions 为主要验证证据。
- RK3588 与 x86 对 `MADV_RANDOM` 的收益方向可能不同，集成只保留现有平台自适应结论，不宣称跨平台统一收益。
- 论文 PDF 会增加仓库体积；若超过 GitHub 内容接口限制，则保留论文索引、固定来源 SHA 与外部引用，不复制超限二进制。
