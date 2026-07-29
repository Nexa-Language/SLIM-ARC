# 报告补全官方大纲缺失章节计划 v1

## 目标

官方建议文档大纲包含 10 个部分，现有报告覆盖了 5 个（目标描述、题目分析、系统框架、测试情况、部分进展/问题），缺失 5 个（开发计划、完整进展历程、问题与解决、分工协作、仓库目录描述、比赛收获）。用户要求把缺失部分放在报告结尾，集中在一个专门的声明/附录里。

## 官方大纲 vs 现有报告对照

| # | 官方大纲 | 现有对应 | 状态 |
|---|---------|---------|------|
| 1 | 目标描述 | [`01_abstract.tex`](reports/Competition_Report/sections/01_abstract.tex) + [`01b_intro.tex`](reports/Competition_Report/sections/01b_intro.tex) | ✅ 完全覆盖 |
| 2 | 比赛题目分析和相关资料调研 | [`02_background.tex`](reports/Competition_Report/sections/02_background.tex) | ✅ 完全覆盖 |
| 3 | 系统框架设计 | [`03_core_design.tex`](reports/Competition_Report/sections/03_core_design.tex) | ✅ 完全覆盖 |
| 4 | 开发计划 | （散见于 ROADMAP，未进报告） | ❌ 缺失 |
| 5 | 比赛过程中的重要进展 | [`06_conclusion.tex`](reports/Competition_Report/sections/06_conclusion.tex) 工作总结 | ⚠️ 只有结论性总结，无历程 |
| 6 | 系统测试情况 | [`05_evaluation.tex`](reports/Competition_Report/sections/05_evaluation.tex) | ✅ 完全覆盖 |
| 7 | 遇到的主要问题和解决方法 | [`06_conclusion.tex`](reports/Competition_Report/sections/06_conclusion.tex) 局限性 | ⚠️ 只有局限性，无"问题→解决"叙事 |
| 8 | 分工和协作 | （README 有团队表，报告内无） | ❌ 缺失 |
| 9 | 提交仓库目录和文件描述 | [`README.md`](README.md) 项目结构 | ⚠️ README 有，报告内无 |
| 10 | 比赛收获 | （无） | ❌ 缺失 |

## 方案

在 [`06_conclusion.tex`](reports/Competition_Report/sections/06_conclusion.tex) 之后新增 [`07_appendix.tex`](reports/Competition_Report/sections/07_appendix.tex)，作为"附录：赛事声明"，包含 5 个 subsection，对应官方大纲缺失的 5 个部分。在 [`main.tex`](reports/Competition_Report/main.tex) 的 `\input{sections/06_conclusion}` 后加 `\input{sections/07_appendix}`。

### 新文件结构 `07_appendix.tex`

```
\newpage
\section{附录：赛事声明}           % 对应官方大纲 4/5/7/8/9/10

\subsection{开发计划}              % 官方大纲 4
  - Phase 0-5 里程碑表（源自 ROADMAP）
  - 实际执行时间线 6/21-6/26

\subsection{比赛过程中的重要进展}   % 官方大纲 5
  - 按日期叙事：6/21 环境搭建 → 6/22 mmap+MADV → 6/23 80B 成功 → 6/24 IQ4_XS 突破 → 6/25 FlashAttention+KV eviction → 6/26 审计修复
  - 关键转折点：OOM → 可运行 → 流畅

\subsection{遇到的主要问题与解决方法} % 官方大纲 7
  - 问题1: Qwen3 架构不兼容 → backport
  - 问题2: GGML_CPU_REPACK 内存翻倍 → 禁用
  - 问题3: 数据波动 → 串行冷启动
  - 问题4: FlexInfer 不支持 Qwen3 → 转 llama.cpp
  - 问题5: prefetch_scheduler 冗余 → 诚实记录
  - 问题6: Speculative decoding 负收益 → 记录负面结果

\subsection{分工与协作}             % 官方大纲 8
  - 三人分工表（欧阳易芃/马福泉/刘昊）
  - 协作方式（Git + AI Agent + 定期会议）

\subsection{提交仓库目录与文件描述}  % 官方大纲 9
  - 目录树（源自 README）
  - 关键文件说明表

\subsection{比赛收获}              % 官方大纲 10
  - 技术收获：OS 虚拟内存 + MoE 稀疏性协同
  - 方法论收获：ABC 分类法、诚实负面结果
  - 团队收获：AI Agent 协作模式
```

## 步骤拆解

1. [ ] 创建 [`reports/Competition_Report/sections/07_appendix.tex`](reports/Competition_Report/sections/07_appendix.tex)，写入 6 个 subsection
2. [ ] 在 [`main.tex`](reports/Competition_Report/main.tex) 第 174 行后加 `\input{sections/07_appendix}`
3. [ ] 编译验证 PDF
4. [ ] commit + 更新 gitlab-clean

## 验收标准

- [ ] PDF 生成成功，无 LaTeX 错误
- [ ] 新增章节目录出现在 TOC
- [ ] 覆盖官方大纲全部 10 个部分
- [ ] 内容与现有章节不重复（appendix 聚焦"过程性"信息，不重复"技术性"内容）
- [ ] 数据与报告其他章节一致（如 64.5×、5.16 t/s 等）

## 风险

1. **内容重复**：06_conclusion 已有"局限性"和"未来展望"，07_appendix 的"问题与解决"可能与之重叠。对策：07 聚焦"工程过程中的具体问题"（Qwen3 兼容、REPACK OOM），06 聚焦"科学层面的局限"（prefetch 冗余、数据波动）。
2. **篇幅过长**：appendix 6 个 subsection 可能让报告超过 40 页。对策：每个 subsection 控制在半页内，用 itemize/table 压缩。
3. **开发计划数据来源**：ROADMAP 不在 gitlab-clean 里（被排除），需要从 ROADMAP 提炼到报告内。对策：直接在 07_appendix 写 Phase 表，不引用外部文件。
