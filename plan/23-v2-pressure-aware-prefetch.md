# Plan 23 v2: Finish Pressure-Aware Prefetch and Run the 80B Gate

## 目标

- 完成 pressure admission 集成提交，并在线性同步队友最新 `origin/main` 时保留双方实现。
- 在 2 GiB、4 vCPU、no-swap 的 Qwen3-Next-80B-A3B `pp64 + tg16` 负载上，以可重复 A/B 数据决定该功能是否进入最终展示配置。

## 前置条件

- llama.cpp 固定为 `360e1349f0009c5ad99d21e3c4546b707addc68a`，模型 SHA-256 固定为 `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`。
- plan 22 已证明 2 GiB 是当前控制器允许的最低稳定档；1 GiB 被安全边界拒绝，因此本轮不伪造“首个更低失败档”。
- pressure admission 仍为显式 opt-in，读取失败和 unlimited cgroup 必须回退 static budget。

## 调整原因

- `build-llama-image.sh` 实际不接受 `--rebuild-patched`，正确调用为无参数执行；Dockerfile 将 baseline 编译移动到补丁 COPY 之前，使后续补丁迭代复用 baseline 层。
- 2 GiB 下默认 reserve 已等于 512 MiB，因而“默认 pressure”和“显式 512 MiB”是同一策略，不重复运行伪 A/B。
- plan 22 的全局 warm 最佳 `SLIM_ARC_NO_PREFETCH=1` 会让 pressure admission 无对象可调，不能作为功能 A/B。改用当时最佳的 prefetch-enabled 组合 `SLIM_ARC_EXPERT_BUDGET=1 + SLIM_ARC_EXPERT_CONF=1`，off/on 两侧保持完全相同的基础配置。
- 最新 `origin/main` 因 merge 同时保留两套 expert prefetch 方法定义；rebase 必须保留本地单一完整实现，并纳入队友 Pi5 文档和报告数据。

## 步骤拆解

1. 提交已通过 normal、ASan/UBSan、patch idempotence 和完整 ARM64 upstream 构建的 Task 4 改动。
2. `git fetch --prune origin` 后执行 `git rebase origin/main`，对 `slim-arc-prefetch.cpp` 做语义级冲突解决；禁止 merge commit。
3. rebase 后重新运行 focused tests，并利用 Docker cache 重建/验证 patched 镜像，确保合并后的源码仍可编译。
4. 在 2 GiB、4 vCPU、no-swap 下运行基础配置 pressure-off 与 pressure-on/default-512 两行，每行 1 次 cold、2 次 warm。
5. 只有 pressure-on 的 throttled samples 超过 80%、仍 OOM，或 512 MiB reserve 无法形成可比较数据时，才增加 1024 MiB reserve 行。
6. 校验输出非空、prompt/token 数一致、swap 为零、模型/llama hash 一致、pressure metrics 可解析；用 warm median 比较墙钟，cold 单独报告。
7. 若 `memory.peak` 至少下降 10% 且 warm wall regression 不超过 15%，设为 `enabled_for_final_demo`；否则保留为 `kept_opt_in`。由于无可测更低档，不以未观测的 OOM 改善作为晋级证据。
8. 生成 `pressure-admission-results.json`、`pressure-admission-summary.md`，更新 ROADMAP，并在最终 push 前再次 fetch/rebase。

## 验收标准

- Task 4 源码在 pinned upstream 上构建成功，manifest 显示 `PATCH_IDEMPOTENT=1`，四组 C++ 单测及 sanitizer、Python/macOS 测试全部通过。
- 本地历史线性位于最新 `origin/main` 之上，远端 Pi5/报告内容存在，expert prefetch 只有一套定义。
- 每个 A/B run 都有 controller result、run manifest、stdout/stderr、cgroup memory/swap/cpu/I/O 证据和明确 outcome。
- promotion decision 直接引用 run ID、memory peak、warm median、cold wall time和 pressure counters，不用单次波动替代结论。

## 风险

- 2 GiB 上 `memory.peak` 可能持续触顶，动态限流可能只改变 reclaim/I/O 而不满足 10% 晋级阈值。
- Colima page cache 与主机存储状态会影响 cold/warm 绝对时间；固定 cache 操作和多次 warm median 只能降低、不能消除该噪声。
- 远端重复定义属于已发布 main 的编译回归；冲突解决后必须重新做真实 upstream 构建，不能只依赖文本 diff。
