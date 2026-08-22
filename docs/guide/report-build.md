# Report Build

决赛报告需要 XeLaTeX、BibTeX 和报告使用的中文字体。构建脚本先验证结构化 Mac 结果的
SHA-256，再生成表格并运行完整 LaTeX 流水线：

```bash
make docs
```

权威源码位于 `reports/Competition_Report_Finals/`；生成的 `main.pdf` 纳入版本发布，
`.aux/.bbl/.blg/.log/.out/.toc` 均为可再生文件，不应提交。
