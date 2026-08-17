# SLIM-ARC 决赛报告

本目录保存决赛阶段的独立 LaTeX 报告，初赛原稿继续保存在
`reports/Competition_Report/`。正文按 Introduction、Background and Related
Work、Design、Implementation、Evaluation、Conclusion 和 Appendix 组织。

Mac 正式矩阵来自
`docs/macos_test_notes/2026-08-12/finals-results.json`，包含五个配置、cold/warm
两种缓存状态和两轮重复，共 20 次成功运行。构建脚本会从该 JSON 生成结果表与两轮
区间图，避免手工复制数字。

构建命令：

```bash
python3 build_finals_report.py \
  --results-path ../../docs/macos_test_notes/2026-08-12/finals-results.json
```

其他设备的数据来源、实验合同和原始记录入口见附录及
`docs/results/README.md`。结构化结果的导入格式见
[RESULTS_IMPORT.md](RESULTS_IMPORT.md)。
