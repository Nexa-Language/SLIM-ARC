# 报告修订 v2 计划

## 9 项新要求

### ① 用户态预取开销 → 操作系统底层绕开
在 06_conclusion.tex 的"prefetch\_scheduler 冗余"段落，补充操作系统层面的解决方案：
- 用 `userfaultfd` 替代 `madvise` 系统调用，在内核态批量处理缺页
- 用 `mlock`/`mmap(MAP_POPULATE)` 预填充
- 修改内核的 `readahead` 系统调用直接控制预读窗口
- 或自定义内核模块拦截 page fault

### ② 标题字号调小 + 断行
main.tex 封面：`\fontsize{36pt}{40pt}` 调小到 `\fontsize{28pt}{32pt}`，断行在 "Memory-Aware" 后面：
`SLIM-ARC: Synergistic LLM Integration with Memory-Aware` // `Runtime Co-Optimization for On-Device Agents`

### ③ 封面信息栏修复
- 恢复 `\makebox[5em][s]{队名}:` 格式（不是 6em）
- "芃"字用 `\CJKfontspec{Noto Serif CJK SC}芃` 单独指定字体
- 检查为什么只有最左边一个字显示

### ④ dumbbell 图彻底重做
问题：对数轴压缩了小值差异，三行看起来还是水平的。
方案：改为**3 个分面子图**（8GB/16GB/32GB 各一个），每个子图独立线性 y 轴，x 轴为优化阶段（baseline→slim→full），用柱状图+连线展示提升。或者改为**分组柱状图**（3 组，每组 3 根柱子）。

### ⑤ 引用信息精确性
对照原论文检查所有 reference.bib 条目的作者名、标题、书名、年份，用 tavily 搜索验证，确保零字母错误。

### ⑥ 双引号改中文全角
全文搜索 `""` 和 `''`，改为中文全角 `""` `''`（或 LaTeX 的 `` `` '' 对中文场景）。

### ⑦ 图片字号调大 + 示意图 prompt 文件
- 所有 generate_*.py 的 fontsize 从 9-10 调大到 12-14
- 创建 `reports/Competition_Report/figures/figure_prompts.md`，为每个示意图写详细的 NeurIPS/AAAI 标准设计描述（少文字多图、不规整普通）
- 用 draw.io 或 TikZ 风格描述，供后续绘制

### ⑧ 实验环境表加三档受限环境
05_evaluation.tex 的环境配置表，增加三档 cgroup 的具体配置行（8GB+4核/12GB+6核/16GB+8核）。

### ⑨ docs/design 重写为代码文档
当前 docs/design/*.md 是 plan 风格，改为工程级代码文档：
- 每个模块的 API、参数、返回值
- 代码结构、调用关系
- 配置项说明
- 示例用法
参考 Google/工程文档标准。

## 执行顺序
1. ②③ 封面修复（main.tex）
2. ⑥ 全文双引号修复
3. ⑦ 图片字号调大 + 创建 figure_prompts.md
4. ④ dumbbell 图重做（分组柱状图方案）
5. ⑧ 环境表加三档
6. ① conclusion 补充 OS 底层方案
7. ⑤ 引用精确性校验（tavily）
8. ⑨ docs/design 重写
9. 编译 + 推送
