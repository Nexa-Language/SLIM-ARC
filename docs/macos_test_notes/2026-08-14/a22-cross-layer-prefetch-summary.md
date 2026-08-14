# A22 跨层 Router 预测预取实测

## 结论

- Mac 2 GiB/no-swap/冷缓存条件下，A22 的最优点是 Top2。两次重复中位数为
  `prefill 4.275860 tok/s`、`decode 1.007538 tok/s`、`wall 98.66 s`；相对同镜像、
  同合同且关闭 A22 的 control，分别为 `+12.50%`、`+9.96%`、`-7.77%`。
- Top2 的 expert byte hit rate 为 `88.56%`，明显高于 control 的同层历史预测路径；
  Top4/Top8 扩大预取后没有继续提升 TPS，说明 2 GiB 下带宽和 page-fault 竞争已经主导。
- A22 仍未超过历史 A20 最佳中位数：A20 为 `decode 1.136075 tok/s`、`wall 85.12 s`。
  因此 A22 保留为 opt-in 研究路径，不替换当前总体性能最佳配置。
- 树莓派 5 4GB 的无交换单次筛选中，Top10 为最好一档：`decode 0.056144 tok/s`，
  相对 control 的 `0.055324 tok/s` 为 `+1.48%`。该数值只有一次样本，必须重复后才能
  写成稳定性能结论。

## Mac 实验合同

- 模型：Qwen3-Next-80B-A3B-Instruct Q4_K_M，文件 SHA-256
  `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`。
- 资源：2 GiB cgroup、swap 0、8 CPU、CPU-only、冷缓存、`pp64/tg64`。
- 基础配置：slow-storage、inline Router、32 MiB/layer pipeline、512 MiB hot cache、
  prefill 8 threads、decode 6 threads、confidence gating 关闭。
- 代码：SLIM-ARC `d972c75a9f09558940e15233f1446292cc19793f`，llama.cpp
  `360e1349f0009c5ad99d21e3c4546b707addc68a`。

| 配置 | Prefill tok/s | Decode tok/s | Wall s | Expert issued GiB | Hit rate |
|---|---:|---:|---:|---:|---:|
| control | 3.800736 | 0.916271 | 106.97 | 53.98 | 41.23% |
| Top1 | 4.323694 | 0.932913 | 104.02 | 6.57 | 81.91% |
| Top2 R1 | 4.458174 | 1.032245 | 95.90 | 11.93 | 88.56% |
| Top2 R2 | 4.093546 | 0.982831 | 101.42 | 11.93 | 88.56% |
| Top4 | 3.517707 | 0.898789 | 111.33 | 22.65 | 90.97% |
| Top8 | 4.160491 | 0.780640 | 118.44 | 44.10 | 87.27% |
| Top2 + confidence | 3.898304 | 0.785045 | 118.07 | 5.94 | 98.43% |
| Top2 + decode8 | 3.955517 | 0.878923 | 109.82 | 11.93 | 88.56% |

`Top2 + confidence` 虽把误取降至约 95 MiB，但 decode 明显下降，说明过度过滤把 I/O
重新推回 demand-fault 关键路径。decode 从 6 threads 增至 8 threads 同样退化，说明额外
CPU 并行会与 page fault/回收路径竞争。

## Raspberry Pi 5 4GB 无交换筛选

- 4 CPU、冷缓存、`pp16/tg4`、Q4 KV、每档运行前清缓存。
- benchmark 期间 `/proc/swaps` 只有表头；整个筛选结束后 `/dev/zram0` 已恢复 active。
- 五档退出码均为 0，expert advice failure/invalid range 均为 0，温度为 42.8--49.4 C。

| 配置 | Prefill tok/s | Decode tok/s | 相对 control | Wall s | Expert hit rate |
|---|---:|---:|---:|---:|---:|
| control | 0.201365 | 0.0553243 | 0.00% | 331 | 11.68% |
| Top2 | 0.200645 | 0.0549788 | -0.62% | 332 | 91.45% |
| Top8 | 0.200411 | 0.0554293 | +0.19% | 331 | 88.08% |
| Top10 | 0.199279 | 0.0561438 | +1.48% | 330 | 82.74% |
| Top16 | 0.200572 | 0.0545688 | -1.37% | 332 | 58.84% |

Top2 证明跨层 Router 的选择精度很高，但覆盖不足以改善端到端速度；Top16 则因额外 I/O
退化。Top10 暂时是容量与覆盖的折中点，但当前差值小于常见单次运行波动，后续必须做
同合同重复实验。

## 后续方向

A22 的价值主要是证明“真实 Router 预测可以显著提高 expert byte precision”。它的主要成本
是额外执行一次下一层 Router matmul。下一步应保留这一精度收益，同时用在线层间 expert
transition predictor 替代额外 matmul，再用 Mac Top2 与 Pi Top10 作为对照。

全部原始值及路径见
[`a22-cross-layer-prefetch-summary.json`](a22-cross-layer-prefetch-summary.json)。
