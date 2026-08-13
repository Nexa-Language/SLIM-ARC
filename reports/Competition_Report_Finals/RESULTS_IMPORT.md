# 决赛结果导入与发布门

决赛报告的唯一性能输入是固定路径 `../../docs/macos_test_notes/2026-08-12/finals-results.json`。该 JSON 由仓库的证据聚合器从冻结镜像、campaign manifest 和原始运行 manifests 生成；报告目录不保存手写、部分或替代路径的结果 JSON。

## 完整性契约

导入器 `import_finals_results.py` 严格接受 schema version 1，且要求：

1. 恰好两轮，每轮 5 个配置（baseline、patched-control、patched-reclaim、patched-residency、patched-combined）各有 cold 和 warm 一次，共 20 次运行；
2. 所有 20 个运行都是 `success`，每个 `(round, configuration, cache_state)` 与 `run_id` 唯一；
3. `sample_counts` 对 10 个 configuration/cache 组合全部为 2；
4. `aggregated_metrics` 对 10 个组合全部具有 peak memory、fault、read、wall、decode 与 expert-waste 六项有限非负指标；
5. `decisions` 及 cold/warm `per_cache` 分类完整、取值受限；
6. JSON 原始字节 SHA-256 被写入生成的 TeX 宏与结果决策表。

任何缺失、非 schema-1、部分矩阵、非成功 outcome、非法数值、过期 TeX 或不安全路径都会失败。失败运行属于实验事实，必须由证据流程保留；只是它不能满足本终稿的“20 次成功运行”发布前置条件。

## 生成与验证

在仓库根目录先生成正式证据：

```sh
UV_CACHE_DIR=/tmp/slim-arc-uv-cache uv run python scripts/macos/build_finals_evidence.py \
  --result-root docs/macos_test_notes/2026-08-12 \
  --build-evidence docs/macos_test_notes/2026-08-12/build/build-evidence.json \
  --campaign-manifest docs/macos_test_notes/2026-08-12/campaign-manifest.json
```

然后从本目录运行：

```sh
python3 import_finals_results.py --write --verify
python3 build_finals_report.py
```

构建驱动会重新计算当前 JSON 的 SHA-256，并在写入后验证 `sections/generated_finals_results.tex` 与 JSON 逐字节推导结果一致。生成文件定义 `\FinalsResultsJsonSha`；driver 只在实际 XeLaTeX 入口注入同一 64 位 hex proof，`main.tex` 会拒绝 proof 缺失或与生成文件不完全相等的构建。因此不可直接运行 `xelatex main.tex`，即使生成文件留在目录中也会 fail-closed。若 JSON 已改变而旧生成文件仍在，driver 在重写前检测到 stale 内容并失败。

driver 只接受不存在或普通文件的 `main.pdf`，开始时清除旧 PDF；任一导入、XeLaTeX 或 BibTeX 失败都会在 `finally` 中删除普通 `main.pdf`。符号链接或非普通 PDF 路径被拒绝。`main.tex` 用 `\InputIfFileExists` fail-closed 导入生成文件；无文件时直接报错。

## 发布前审阅

除导入器检查外，维护者仍须确认每个 JSON 行可反查到 run ID 和 raw manifest，模型 SHA-256、llama.cpp `360e134`、镜像/variant linkage、commit、patched source hash、2 GiB/4 vCPU/no-swap、`pp64`/`tg16` 与 cold/warm 标签均保持一致。报告中的两张结果表只来自生成文件，不能手工转录或与其他设备、工作负载或历史行拼接。最终 PDF 生成后必须逐页渲染检查。
