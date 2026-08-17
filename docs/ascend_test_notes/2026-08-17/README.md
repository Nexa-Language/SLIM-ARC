# Ascend 910B4 最小兼容性验证

本次通过 HiDevlab 跳板 SSH 连接备用 Ascend 节点，只在 `/workspace/slim-arc-ouyang-20260817` 创建隔离目录。没有读取或修改另一个比赛的源码、模型与结果，没有安装软件、下载模型、修改驱动或停止任何进程。

## 结果

- 主机为 `aarch64` Linux，设备为 Ascend 910B4，HBM 32 GiB。
- `npu-smi 25.2.0` 报告 Health `OK`；初始快照 AICore 0%，无 NPU 进程。
- 系统 Python 为 3.11.6，但没有系统级 PyTorch、`torch_npu`、CANN toolkit 或 `libascendcl.so`。
- 只读复用既有 Python 环境时，`torch_npu` 因缺少 `libhccl.so` 无法导入，未执行任何算子。
- 探测后另一个比赛的 NPU 进程开始运行并占用 313 MiB HBM；SLIM-ARC 随即停止，不终止、不附着也不竞争该进程。

因此，这份数据只证明 HiDevlab SSH、驱动和 910B4 硬件枚举正常，不能作为 LLM TPS、算子吞吐或 SLIM-ARC 加速证据。完整验证必须使用含匹配 CANN toolkit 的独立镜像或等待 Merlin Job 获得 Pod。

## HiDevLab 中的 OLMoE 系统 A/B

随后在用户新建的 HiDevLab 独立环境 `/workspace/SLIM-ARC` 中完成了真正的模型 A/B。该环境可以编译并运行 `aarch64` 版 llama.cpp，但 SLIM-ARC 当前没有 CANN/NPU backend，因此本组数据走 CPU-only POSIX/mmap 路径；它验证的是“华为开发环境中的跨架构可移植性和系统开/关差异”，不是 910B NPU 加速。

模型采用官方 `allenai/OLMoE-1B-7B-0924-Instruct-GGUF` 的 Q2_K 文件，大小 2,562,763,232 B，SHA-256 为 `30a594dcb82aedfa10af714cdd218717dc00de71b980e7bf35d18055f82ea525`。为了让小于 6 GiB 的模型确实进入 SLIM-ARC runtime，本次只在隔离实验构建中把 admission guard 从 6 GiB 降到 2 GiB；仓库默认行为没有被改写。baseline 和 patched 使用相同模型、16 线程、`pp64/tg16`、三次重复、CPU-only、mmap、offline。

| 配置 | Prefill t/s | Decode t/s | Wall s | Max RSS KiB | Runtime |
|---|---:|---:|---:|---:|---:|
| baseline | 100.724597 | 51.340323 | 3.254600 | 2,575,956 | 0 |
| patched-default | 101.175889 | 45.254024 | 3.415535 | 2,577,888 | 1 |
| patched-A24 | 100.602680 | 48.184150 | 3.373611 | 2,577,380 | 1 |

A24 是已测 patched 配置中最快的 Decode 路径，相对 patched-default 提升 6.474841%，并把 wall time 降低 1.227450%；但相对 baseline 仍为 Decode `-6.147552%`、wall `+3.656701%`。这说明小模型、内存充足、热页缓存不是 SLIM-ARC 的优势区间。runtime 行确认系统确实运行：`expert_samples=785`，权重页 advice 覆盖 243,200,667,648 B；但 `expert_issued_bytes=0`，因此本组不能宣称专家预取带来加速。

完整机器可读数据和另外四组调参结果见 `olmoe-q2-runtime-ab.json`。损坏的 7.36 GB Q8 镜像文件、拼接副本和分片目录已经从远端删除，仅保留有效 Q2 模型、日志和结果。
