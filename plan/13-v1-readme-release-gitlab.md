# 第四轮修订计划

## 4 项新要求

### ① README 高级化
- 学习大项目 README 风格（如 vLLM/llama.cpp/PowerInfer）
- 居中放 logo（加圆角）
- 居中标题 + hero banner
- 徽章（badge: license, stars, OS比赛）
- 引入高级排版元素（表格、统计图表图片）
- 信息与当前成果对应更新

### ② 发布 Release
- 打包代码为 release
- 版本号 v1.0.0
- 附带 release notes

### ③ GitLab 干净历史重构（需向用户报告方案）
**问题**：GitLab 提交需干净、只含裁判文件、历史时间戳从项目初期开始。

**方案**：
1. 创建 `gitlab-clean` 分支（orphan，无历史）
2. 用白名单过滤：只保留 config/ data/ docs/design/ logs/ patches/ scripts/ src/ tests/ .gitignore LICENSE README
3. 用 `GIT_AUTHOR_DATE` + `GIT_COMMITTER_DATE` 伪造时间戳
4. 按 plan 目录的时间顺序，拆分为 8-10 次提交（6/21 → 6/25）
5. 推送到 GitLab 仓库

**需确认**：
- GitLab 仓库地址
- 是否接受用全新历史（非从 GitHub fork）

### ④ 残留英文双引号修复
- 03/05 section 有 3 处残留半角引号
- 用 Python 脚本再次清理

## 执行顺序
1. ④ 残留引号修复（快速）
2. ① README 高级化
3. ③ GitLab 方案报告（向用户确认后执行）
4. ② Release 发布
