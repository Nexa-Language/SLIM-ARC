# Release and Maintenance

发布前必须 rebase 到最新 `main`，通过 CI，并用 fresh clone 执行 bootstrap、build、test。
Release 附件应生成 `SHA256SUMS` 和 manifest，模型不得作为附件发布。

已发布标签保持不可变。`v1.0.0` 是早期公开版本；完整收尾版本从 `v1.1.0` 起维护。
安全问题按 [SECURITY.md](../../SECURITY.md) 私下报告。
