# 报告全面修订计划 v1

## 目标
按照用户 9 条要求，对 `reports/Competition_Report/` 进行全面修订，提升学术规范性和内容深度。

## 修改清单

### ① 封面标题修改（main.tex）
- 小标题（`\projname`）改为：`OS挑战赛 Proj59`
- 正标题（`\reporttitle`）改为：`SLIM-ARC: Synergistic LLM Integration with Memory-Aware Runtime Co-Optimization for On-Device Agents`

### ② 信息栏修改（main.tex 封面）
替换学号/姓名/专业/指导教师/实验日期为：
```
队名：依托Agent答辩OS
组员：欧阳易芃 马福泉 刘昊
指导教师：赵帅 张献伟
学校：中山大学
赛道：操作系统功能挑战赛
选题：Proj 59
```

### ③ 2.3 相关工作的 subsubsection 改为 paragraph
将 `02_background.tex` 中 2.3.1~2.3.10 的 `\subsubsection{...}` 改为 `\paragraph{...}`，使其不编号、紧凑排版。

### ④ 核心设计 section 大幅扩充（03_core_design.tex）
当前仅 124 行，需扩充到 300+ 行：
- 每个设计点补充：**设计思路来源**（引用哪篇论文/综述哪个 section）+ **原理分析**
- 新增 **FlashAttention 设计**（综述 Sec 4.1，IO-aware tiling）
- 新增 **StreamingLLM KV Eviction 设计**（综述 Sec 4.3，sink+window）
- 涉及算法的部分补上 **伪代码 block**（用 listings/algorithm 环境）：
  - MoE Router Hook 算法伪代码
  - prefetch_scheduler 调度循环伪代码
  - KV eviction maybe_evict 伪代码
  - unified_io_scheduler tick 伪代码
- 所有 design 示意图用 **方框占位** + **详细图注**（自包含自解释）
  - 整体架构图
  - mmap+MADV_RANDOM 机制图
  - MoE Router Hook 流程图
  - KV Eviction sink+window 示意图
  - 统一 I/O 调度器时序图

### ⑤ 实验评估图表讲解补充（05_evaluation.tex）
- **环境配置表**：补充自然段讲解（为什么选这 3 档、cgroup 隔离原理）
- **模型规格表**：补充讲解（为什么选 Qwen3-Next-80B/OLMoE/Qwen3-4B，Dense vs MoE 对比意义）
- **每个表格/图片后**：紧跟 2-3 段自然段，多维度分析（为什么快/慢、与预期是否一致、与 baseline 差距、insight）
- **5.3 核心实验**重点补充：每个表格后加深度分析段落
- 所有图片写**详细图注**（自包含自解释）

### ⑥ dumbbell 图修复
`fig_optimization_dumbbell.png` 当前三根横线水平（红蓝紫在同一水平线），修复为正确的 dumbbell 形态（左 baseline 点 → 右优化点，中间连线，体现提升）。

### ⑦ evaluation 分节重组为 4 组
当前 11 个 subsection 太多，重组为：
1. **5.1 实验设置**（环境、模型、配置、数据集、benchmark、对比维度与基线）
2. **5.2 核心实验**（80B 三档性能 + FlashAttention + 端到端生成）
3. **5.3 附属实验**（小模型、KV 量化对比、StreamingLLM eviction、GSM8K 精度）
4. **5.4 消融实验**（四组单点消融 + 6GB 验证 + Speculative Decoding 负面结果 + 数据波动分析）

### ⑧ conclusion 末尾三张图移除
`06_conclusion.tex` 末尾的 3 张图（radar、dumbbell、small_models）移到 evaluation 对应位置，conclusion 不放图。

### ⑨ 未来展望改为单自然段
删除当前的"短期/中长期"分点，改为**一个自然段**：
- 说明初赛时间紧迫，部分工作未完成
- 决赛阶段将做什么（参考 `docs/others/赛题与学习路径.pdf` 和 `docs/others/INIT_PROMPT.md` 的规划）

### ⑩ 背景与相关工作大幅扩充 + 引用增加
当前 104 行，扩充到 200+ 行，按 NeurIPS 论文写法分 3-4 组：
- **2.1 端侧 LLM 推理的内存墙挑战**（补充背景数据、行业趋势）
- **2.2 MoE 模型的稀疏性机遇**（补充 MoE 发展脉络、Qwen3-Next 架构细节）
- **2.3 相关工作**（分 4 组，每组带自然段引导 + 引用）：
  - 2.3.1 权重卸载与按需加载（FlexInfer, llama.cpp, PowerInfer-2）
  - 2.3.2 KV Cache 管理与量化（DUAL-BLADE, HillInfer, ScoutAttention, KVQuant, KIVI, ThinK）
  - 2.3.3 MoE 稀疏性利用（MobileMoE, MoE-Prism, eMoE, ProMoE）
  - 2.3.4 Attention 优化与 KV Eviction（FlashAttention, StreamingLLM, SolidAttention, PagedAttention）
- **2.4 问题定义**
- 引用从当前 ~16 条增加到 **30+ 条**（从综述提取）

## 执行顺序
1. main.tex 封面修改（①②）
2. 02_background.tex 扩充+引用（⑩）+ subsubsection→paragraph（③）
3. 03_core_design.tex 大幅扩充+伪代码+方框图（④）
4. 05_evaluation.tex 重组 4 组+讲解补充（⑦⑤）
5. 06_conclusion.tex 移除图+未来展望改自然段（⑧⑨）
6. 修复 dumbbell 图（⑥）
7. reference.bib 补充引用
8. 编译验证 + 推送 GitHub

## 验收标准
- [ ] 封面标题和信息栏正确
- [ ] 2.3 用 paragraph 不编号
- [ ] 核心设计 300+ 行，含伪代码和方框图
- [ ] 每个图表后有自然段讲解
- [ ] dumbbell 图正确显示
- [ ] evaluation 4 个 subsection
- [ ] conclusion 无图，未来展望单自然段
- [ ] 背景 200+ 行，30+ 引用
- [ ] PDF 编译成功
