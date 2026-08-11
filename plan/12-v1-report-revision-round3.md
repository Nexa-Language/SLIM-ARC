# 第三轮修订计划

## 5 项新要求

### ① figure_prompts.md 去除 ASCII 字符画，改自然语言描述
删除所有 ` ``` ` 包裹的布局描述，用流畅的自然语言描述设计意图、视觉元素、配色、箭头语义等，不限制实现方式。

### ② core_design 突出新颖性 + 逻辑对应
- design 的叙述逻辑：发现问题 → 用 design 解决 → 实验测量 → 得出结论
- design 的 subsection 应与 background 的 problem 定义、evaluation 的实验组、conclusion 的贡献对应
- 当前 03_core_design 的结构基本对应，但需在开头补充"设计思路总述"段落，显式映射 problem→design→eval→conclusion 的对应关系
- 突出新颖性：每个设计点强调"为什么这是新的"（与现有工作的差异）

### ③ 创建 site/ 目录，GitHub Pages 展示网站
- 多个子页面（index, architecture, benchmark, team 等）
- 动画设计感（CSS 动画、滚动效果、粒子背景等）
- 顶级科技公司审美（配色高级、简洁有信息度、fancy）
- HTML+CSS+JS
- logo: docs/others/logo/logo_nobg.png
- 发布到 slim.nexa-lang.com（CNAME 已映射）

### ④ 伪代码改用 algorithm + algorithmic 环境
当前用 lstlisting 高亮代码块，改为标准学术 algorithm 环境：
```latex
\usepackage{algorithm}
\usepackage{algorithmic}
\begin{algorithm}[!h]
    \caption{...}
    \label{...}
    \begin{algorithmic}[1]
        \STATE ...
        \WHILE ...
    \end{algorithmic}
\end{algorithm}
```
修改 main.tex 加载宏包，03_core_design.tex 的 2 段伪代码改写。

### ⑤ plan 目录重编号
当前编号重叠（04v1/v2, 05两个v1, 06两个v1）。按时间顺序重新编号：
- 00-v1-slim-arc-overview → 保留
- 01-v1-qwen3-backport → 保留
- 02-v1-approach-a-upstream-prefetch → 保留
- 03-v1-prefetch-design → 保留
- 04-v1-survey-inspired-optimization → 保留
- 04-v2-mainline-redirection → 重命名为 05-v1-mainline-redirection
- 05-v1-mmap-on-demand-redesign → 重命名为 06-v1-mmap-on-demand-redesign
- 05-v1-report-comprehensive-revision → 重命名为 07-v1-report-revision
- 06-v1-mainline-priority-rebalance → 重命名为 08-v1-mainline-priority
- 06-v1-report-revision-round2 → 重命名为 09-v1-report-revision-round2
- 07-v1-audit-remediation → 重命名为 10-v1-audit-remediation
- 08-v1-deep-optimization → 重命名为 11-v1-deep-optimization

## 执行顺序
1. ① figure_prompts.md 自然语言重写
2. ④ main.tex 加载 algorithm 宏包 + 03_core_design 伪代码改写
3. ② 03_core_design 补充设计思路总述 + 新颖性强调
4. ⑤ plan 目录重编号
5. ③ 创建 site/ 网站（多页面 + 动画 + logo）
6. 编译验证 + 推送 GitHub
