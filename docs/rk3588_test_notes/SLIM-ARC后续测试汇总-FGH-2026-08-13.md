# SLIM-ARC 后续测试汇总（F/G/H 组）— 2026-08-13

## 环境
- 设备: RK3588（7.8GB RAM + 3.9GB swap, MemorySwapMax=0 禁用 swap）
- 二进制: `llama-bench`/`llama-cli` build b1-360e134（含 SLIM-ARC 补丁）
- 模型: Qwen3-Next-80B-A3B-Instruct-Q4_K_M (45.08 GiB, ssd/models/)、Qwen3-4B-Q4_K_M (2.4G, SLIM-ARC/data/models/)
- 内存限制: cgroup v2 `systemd-run --user --scope -p MemoryMax=... -p MemorySwapMax=0`
- 所有原始日志: `docs/rk3588_test_notes/adv-scenario-{F,G,H}*2026-08-13.txt`
- 每条命令 `timeout 600` 秒

## 测试 1：更紧内存限制（80B 模型，pp128/tg64，-t 4，-ctk/-ctv q4_0）

| 编号 | 配置 | MemMax | pp128 t/s | tg64 t/s | vs baseline | 等级 |
|------|------|--------|-----------|----------|-------------|------|
| F1 | Baseline (SLIM_ARC_DISABLE=1) | 3G | 3.85 | 0.70 | — | — |
| F2 | SLIM-ARC | 3G | 4.40 | 2.21 | tg +216% (3.16×), pp +14% | A |
| F3 | SLIM-ARC + KV_EVICT (sink=4, win=512) | 3G | 4.19 | 2.12 | tg +203% (3.03×), pp +9% | A |
| F4 | Baseline (SLIM_ARC_DISABLE=1) | 2500M | 3.97 | 1.91 | — | — |
| F5 | SLIM-ARC + KV_EVICT (sink=4, win=512) | 2500M | 4.26 | 2.21 | tg +16%, pp +7% | C |

观察：
- **无 OOM**：5 组均未触发 cgroup OOM kill（45GB mmap 模型在紧内存限制下靠 page cache 逐出维持运行）。
- 3G 限制下 baseline tg 仅 0.70 t/s（严重缺页抖动），SLIM-ARC prefetch 将其拉回 2.2 t/s 量级——这是本组最大增益场景。
- 2.5G 限制下 baseline tg 反而升至 1.91 t/s（缺页抖动程度对 page cache 驻留窗口高度敏感，单次 r=1 采样存在波动），SLIM-ARC 仍小幅领先（+16%）。

## 测试 2：超长上下文 KV eviction 防 OOM（80B 模型，-p 4096/8192 -n 128，MemMax=4G）

| 编号 | 配置 | -p | 结果 | 等级 |
|------|------|-----|------|------|
| G1 | Baseline | 4096 | TIMEOUT 600s（pp 阶段未完成，无输出） | D |
| G2 | SLIM-ARC + KV_EVICT (sink=4, win=1024) | 4096 | TIMEOUT 600s（pp 阶段未完成，无输出） | D |
| G3 | Baseline | 8192 | TIMEOUT 600s（pp 阶段未完成，无输出） | D |
| G4 | SLIM-ARC + KV_EVICT (sink=4, win=1024) | 8192 | TIMEOUT 600s（pp 阶段未完成，无输出） | D |

观察：
- **无 OOM**（均未触发 oom-killer，被 timeout 终止）。
- root-cause（已写入各日志 [TEST-NOTE]）：45GB 模型在 4GB cgroup 限制下处理 4096+ token 的 pp 阶段，mmap 缺页 + page cache 逐出 + 逐层 KV 写入导致耗时远超 600s 预算。对比 F 组 pp128 约 30s，pp4096 为 32 倍 token 量，线性外推远超 600s。
- KV eviction 不改变 pp 阶段耗时（bench 单 prompt 场景无法体现其长对话价值）。

## 测试 3：多轮对话端到端（4B 模型，-c 4096 -n 256，MemMax=3G，5 轮对话）

| 编号 | 配置 | Prompt t/s (5轮) | Generation t/s (5轮) | Gen 均值 vs H1 | 等级 |
|------|------|------------------|----------------------|----------------|------|
| H1 | Baseline (SLIM_ARC_DISABLE=1) | 7.9/8.1/8.0/7.7/7.6 | 6.2/4.7/4.1/3.9/3.7 | — (4.52) | — |
| H2 | SLIM-ARC + KV_EVICT (sink=4, win=512) | 7.9/8.3/8.0/7.8/7.4 | 6.7/5.9/5.2/4.2/4.0 | +15% (5.20) | C |

观察：
- 两组均完整跑完 5 轮对话，无 OOM、无崩溃。
- 进程在 stdin 耗尽后等待更多输入，被 600s timeout 正常终止（EXIT=124），非异常。
- H2 Generation 均值 5.20 vs H1 4.52 t/s（+15%）；Prompt 基本持平（7.88 vs 7.86）。
- H1 已知 artifact：shell `echo -e` 的 `-e` 字样混入首条输入（H2 改用 printf 已修复）。
- H1/H2 原始日志含模型加载进度帧（207MB/315MB），已精简为对话与性能行，原始大小记录在日志头部。

## S 级场景判定

**未找到 S 级场景（baseline OOM 但 SLIM-ARC 存活）**。
本轮 11 组测试中 baseline 从未触发 cgroup OOM kill：45GB 模型经 mmap 映射，cgroup 内存压力通过 page cache 逐出消化，表现为性能劣化而非 OOM。因此不存在 "baseline 死、SLIM-ARC 活" 的场景。

最佳场景仍为 **F2/F3（3G 限制 + 短 prompt）**：SLIM-ARC tg 达 baseline 的 3.0-3.2×（等级 A）。

## 备注
- 未修改任何核心代码；本轮为纯测试执行，无代码改动（红线规则 #1/#2 不适用）。
- 失败/超时均已留痕：G1-G4 各日志含 [TEST-NOTE] root-cause 分析（红线规则 #6）。
