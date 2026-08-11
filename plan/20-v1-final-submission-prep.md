# 最终提交准备计划 v1

## 目标
完成比赛最终提交前的 4 项内容更新，并同步到 GitLab。

## 任务拆解

### 任务 1：报告附录加 AI 使用声明
- **文件**：[`reports/Competition_Report/sections/07_appendix.tex`](reports/Competition_Report/sections/07_appendix.tex)
- **位置**：在 §F 比赛收获 之后，新增 §G AI 使用声明
- **内容**：委婉陈述 AI 使用情况，不需要很详细
- **关键**：诚实但不过度暴露，强调"辅助"而非"替代"

### 任务 2：摘要页加链接
- **文件**：[`reports/Competition_Report/sections/01_abstract.tex`](reports/Competition_Report/sections/01_abstract.tex)
- **位置**：关键字下面空一小段，插入链接列表
- **链接**：
  - 项目主页：https://slim.nexa-lang.com/
  - 项目仓库：https://gitlab.eduxiji.net/T2026105589911358/project3136859-389100
  - 项目介绍与Demo视频：https://www.bilibili.com/video/BV1fXTF6HEAw
  - 项目报告、实机运行Demo和PPT（百度网盘）：https://pan.baidu.com/s/1i83bdq-oiqOCvga3g05v8g?pwd=m8yy 提取码 m8yy

### 任务 3：site 关联 GitLab + B站视频
- **文件**：[`site/index.html`](site/index.html) 等所有页面
- **改动**：
  1. 所有 GitHub 链接改成 GitLab 链接
  2. 在首页某个 section 加一个 B站视频嵌入（iframe，自动静音播放）
- **B站嵌入**：用 `<iframe>` 引用 `https://www.bilibili.com/video/BV1fXTF6HEAw` 的 embed URL

### 任务 4：GitLab 清理 + PPT + README 链接

#### 4a：GitLab 的 reports/Competition_Report 清理
- **目标**：只保留 `main.pdf` 和 `figures/*.png`
- **删除**：`main.tex`, `main.aux`, `main.bbl`, `main.blg`, `main.out`, `main.toc`, `reference.bib`, `README.md`, `LICENSE`, `sections/`, `figures/*.py`, `figures/*.md`
- **方法**：更新 prepare-gitlab-v6.py 的排除规则，在 gitlab-clean 里删掉这些文件

#### 4b：PPT 放进 GitLab
- **文件**：`reports/SLIM-ARC展示PPT.pdf`
- **位置**：GitLab 根目录 `reports/SLIM-ARC展示PPT.pdf`（已存在于主仓库，确保 gitlab-clean 也有）

#### 4c：README 开头"项目概述"尾部加链接
- **文件**：[`README.md`](README.md)
- **位置**：项目概述 section 尾部
- **内容**：引用各链接 + 报告 PDF + PPT PDF，让评审一眼看见

#### 4d：同步到 GitLab
- 用 prepare-gitlab-v6.py 重新生成 gitlab-clean
- 分批 push（上次的经验：50MB pack 限制）

## 执行顺序

1. [ ] 任务 1：07_appendix.tex 加 AI 声明
2. [ ] 任务 2：01_abstract.tex 加链接
3. [ ] 任务 3：site/ 改 GitLab + B站视频
4. [ ] 任务 4a：更新 prepare-gitlab-v6.py 排除规则（reports/Competition_Report 只留 PDF+figures）
5. [ ] 任务 4b/c：README 加链接
6. [ ] 编译 PDF 验证
7. [ ] commit 主仓库
8. [ ] 重新生成 gitlab-clean（含 PPT、清理后的 reports、site 改动）
9. [ ] 分批 push GitLab

## 验收标准

- [ ] PDF 编译成功，附录有 AI 声明，摘要有链接
- [ ] site 所有 GitHub 链接改为 GitLab，首页有 B站视频嵌入
- [ ] GitLab 的 reports/Competition_Report 只有 main.pdf + figures/*.png
- [ ] GitLab 有 reports/SLIM-ARC展示PPT.pdf
- [ ] README 项目概述尾部有所有链接
- [ ] GitLab push 成功

## 风险

1. **B站 iframe 跨域**：B站 embed URL 可能被 CSP 拦截。对策：用 `<iframe>` 配合 `referrer-policy`
2. **GitLab 50MB 限制**：PPT PDF 可能较大。对策：分批 push
3. **prepare-gitlab-v6.py 排除规则**：需要精确匹配 reports/Competition_Report 下的文件类型
