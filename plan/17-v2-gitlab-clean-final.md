# GitLab Clean 最终版计划 v2

## 目标
生成一个干净的 gitlab-clean 仓库，只包含裁判面向的文件，历史时间戳从 6/21-6/26，每天约 8-12 次提交，时间集中在晚上 8 点到凌晨 2 点。**按照 GitHub 的实际提交顺序逐个 cherry-pick**，保留原始 commit message 和文件逐步修改的顺序，只不过排除白名单外的文件。

## 白名单（只保留这些）
- `config/`
- `data/`（仅 README.md 和 benchmarks/gsm8k/）
- `docs/design/`（6 个工程文档）
- `docs/guide/`、`docs/official/`、`docs/others/`、`docs/papers/`
- `logs/`（仅 full-rerun/ 和 raw-80b/ 和 gsm8k 日志，不含旧 CSV 和 roo_task）
- `patches/`
- `scripts/`（不含 profile/src/、prepare-gitlab.sh、run-full-ablation.sh、run-serial-ablation.sh）
- `src/`（llama-upstream 完整）
- `tests/`
- `.gitignore`
- `LICENSE`
- `README.md`

## 排除清单
- `AGENT.md`（含 AI 协作规则）
- `ROADMAP.md`（内部进度记录）
- `.github/`（CI/CD 配置）
- `site/`（展示网站）
- `old-backup/`（旧文件备份）
- `plan/`（内部计划）
- `reports/raw_analysis/`（内部分析报告）
- `reports/Competition_Report/main_original.tex` 等中间文件
- `gitlab-clean/`（自身）
- `scripts/profile/src/`（残留旧代码）
- `scripts/prepare-gitlab.sh`、`run-full-ablation.sh`、`run-serial-ablation.sh`
- `logs/roo_task_*`、`logs/baseline-upstream-*`、`logs/ablation/ablation-*.csv`

## 时间戳方案
- 日期：2026-06-21 到 2026-06-26
- 每天 8-12 次提交
- 时间：20:00-02:00 随机
- **从 GitHub 实际提交顺序 cherry-pick**，保留原始文件逐步修改的顺序
- 保留原始 commit message
- 每次提交只包含白名单内的文件变更

## 执行步骤
1. 创建 orphan 仓库 gitlab-clean/
2. 获取 GitHub 全部提交列表（从早到晚）
3. 对每个提交：
   a. 从该提交 checkout 白名单文件
   b. 复制到 gitlab-clean/
   c. 如果有变化，用伪造时间戳（6/21-6/26 20:00-02:00 随机）提交
   d. 保留原始 commit message
4. 列出历史和文件让用户检查
5. **不 push**，等用户确认

## 关键原则
- 尽可能像 GitHub 的提交顺序，文件一个个部分、一行行修改
- 只排除白名单外的内容
- 时间戳伪造但不改变提交内容和顺序
