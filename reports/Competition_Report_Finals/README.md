# SLIM-ARC 决赛报告

本目录在 `reports/Competition_Report/` 的初赛 TeX 树基础上独立冻结；初赛目录不被本目录的编辑覆盖。决赛正文陈述已经实现并经机制测试覆盖的安全、生命周期和指标契约，并导入 2026-08-12 完成的两轮 20-run 正式矩阵。任何性能数字、速度比和推广结论都必须来自本目录所述的机器生成结果输入。

正式结果必须是**恰好两轮**的完整矩阵：每轮包含五个配置各一条 cold 与一条 warm，共 20 次成功运行。`main.tex` 只能通过 `\InputIfFileExists` 导入由 `import_finals_results.py` 从固定 JSON 路径生成的 TeX；正式 `build_finals_report.py` 在每次 XeLaTeX/BibTeX 构建前重新生成并逐字节核验该导入文件。

生成 TeX 内含 JSON 的 64 位 SHA-256；driver 将同一份当前 JSON 的 SHA-256 作为仅本次构建的 TeX proof 注入，`main.tex` 要求两者精确一致。因而直接执行 `xelatex main.tex`（即使存在旧的生成文件）一定失败；JSON 已更新而生成文件未更新时，带旧文件的 driver 也会失败而不是悄悄覆盖证据。driver 只接受不存在或普通文件的 `main.pdf`，开始前清除旧 PDF，任一导入/TeX/BibTeX 失败都会删除新旧普通 PDF。缺失、部分、失败或过期 JSON 会使构建失败，防止没有正式表格的草稿 PDF 被误认为最终提交物。

详见 [RESULTS_IMPORT.md](RESULTS_IMPORT.md)：它说明如何从固定矩阵的 build evidence、campaign manifest 和原始 run manifests 生成、审核和导入 `finals-results.json`。
