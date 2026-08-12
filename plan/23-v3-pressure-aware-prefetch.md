# Plan 23 v3: Re-run the 80B Gate after Variant Linkage Repair

## 目标

- 修复 patched executable 错载 baseline shared libraries 的基准完整性问题。
- 只使用通过 linkage gate 与补丁专属指标门禁的新 run，重新完成 2 GiB pressure admission A/B。

## 前置条件

- 固定 llama.cpp、模型 hash、2 GiB、4 vCPU、no-swap、`pp64 + tg16` 与 plan 23 v2 一致。
- `tests/macos/test-variant-linkage.sh` 必须证明两个 variant 分别解析到自身 `libllama.so`。
- patched pressure smoke 必须同时出现 `[SLIM-ARC-PRESSURE]`、完整 pressure 环境和零 swap/OOM。

## 步骤拆解

1. 移除全局混合 `LD_LIBRARY_PATH`，wrapper 按 variant 设置唯一 library directory；manifest allowlist 加入 pressure 变量。
2. 重建并运行 linkage gate、48 个 macOS/Python 测试及相关 C++ 测试。
3. 将旧 patched rows 标为 invalid historical evidence，保留原始文件用于审计，不删除或改写原始输出。
4. 用 `SLIM_ARC_EXPERT_BUDGET=1 + SLIM_ARC_EXPERT_CONF=1` 重跑 corrected pressure-off 与 pressure-on/default-512，各 1 cold + 2 warm。
5. 因 default-512 smoke throttled ratio 为 100%，补跑 reserve-1024；若两者 effective budget 都为 0，则明确记录策略等价，不用噪声宣称 1024 更优。
6. 从 raw manifests 生成结构化 results/summary，按 warm median、cold、memory peak、cgroup events 和 pressure counters 作 promotion decision。
7. 最终 fetch/rebase 最新 `origin/main`，重跑快速门禁后推送 `main`。

## 验收标准

- baseline/patched linkage 各自唯一且可重复验证；patched run 出现补丁专属 metrics。
- 有效 A/B 所有 repetition 输出 64/16 token、commit/model hash 一致，swap current/max 为 0/0，OOM 为 0。
- 结论不引用任何修复前 patched wall time；JSON/Markdown 明确列出 invalidated run IDs 与原因。
- 满足 v2 的 10% memory / 15% wall promotion threshold 才启用最终展示，否则保持 opt-in。

## 风险

- 正确加载 patched library 后，真实性能可能显著不同于旧报告，甚至暴露新的 OOM/超时问题。
- default-512 已将 effective prefetch budget 压至零，1024 可能完全等价；必须报告负结果而非挑选随机波动。
- 修复改变基准基础设施，最终提交前必须重新 fetch 队友代码并验证没有新的镜像/补丁冲突。
