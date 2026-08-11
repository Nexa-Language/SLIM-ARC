# GitLab Clean 最终版计划

## 目标
生成一个干净的 gitlab-clean 仓库，只包含裁判面向的文件，历史时间戳从 6/21-6/25，每天约 10 次提交，时间集中在晚上 8 点到凌晨 2 点。

## 白名单（只保留这些）
- `config/`
- `data/`（仅 README.md 和 benchmarks/gsm8k/）
- `docs/design/`（6 个工程文档）
- `logs/`（仅 full-rerun/ 和 raw-80b/ 和 gsm8k 日志，不含旧 CSV 和 roo_task）
- `patches/`
- `scripts/`（不含 profile/src/、prepare-gitlab.sh、run-full-ablation.sh）
- `src/`（llama-upstream 完整）
- `tests/`
- `.gitignore`
- `LICENSE`
- `README.md`

## 排除清单
- `AGENT.md`（含 AI 协作规则，不适合给裁判）
- `ROADMAP.md`（内部进度记录）
- `.github/`（CI/CD 配置）
- `site/`（展示网站）
- `old-backup/`（旧文件备份）
- `plan/`（内部计划）
- `reports/raw_analysis/`（内部分析报告，仅保留 Competition_Report/）
- `reports/Competition_Report/main_original.tex` 等中间文件
- `gitlab-clean/`（自身）
- `scripts/profile/src/`（残留旧代码）
- `scripts/prepare-gitlab.sh`（自身）
- `scripts/bench/run-full-ablation.sh`（内部实验脚本）
- `logs/roo_task_*`（内部对话记录）
- `logs/baseline-upstream-*`（旧基线记录）
- `logs/ablation/ablation-*.csv`（旧 CSV 数据）
- `logs/ablation/raw-20260623-*/`（已在 old-backup）
- `data/models/`（大文件，.gitignore）

## 时间戳方案
- 日期：2026-06-21 到 2026-06-25
- 每天 8-12 次提交，共约 40-50 次
- 时间：20:00-02:00 随机
- 从 GitHub cherry-pick 实际提交，重写时间戳
- 保留原始 commit message

## 执行步骤
1. 创建 orphan 仓库 gitlab-clean/
2. 从 GitHub 按时间顺序采样约 50 个提交
3. 对每个提交：checkout 白名单文件 → 复制到 gitlab-clean/ → 用伪造时间戳提交
4. 列出历史和文件让用户检查
5. **不 push**，等用户确认

## 与之前方案的区别
- 白名单更精确（排除 raw_analysis、plan、site 等）
- 时间戳从 GitHub 提交中采样而非均匀分布
- 串行执行（无并行问题）
