# Ascend 910B4 最小兼容性验证

本次通过 HiDevlab 跳板 SSH 连接备用 Ascend 节点，只在 `/workspace/slim-arc-ouyang-20260817` 创建隔离目录。没有读取或修改另一个比赛的源码、模型与结果，没有安装软件、下载模型、修改驱动或停止任何进程。

## 结果

- 主机为 `aarch64` Linux，设备为 Ascend 910B4，HBM 32 GiB。
- `npu-smi 25.2.0` 报告 Health `OK`；初始快照 AICore 0%，无 NPU 进程。
- 系统 Python 为 3.11.6，但没有系统级 PyTorch、`torch_npu`、CANN toolkit 或 `libascendcl.so`。
- 只读复用既有 Python 环境时，`torch_npu` 因缺少 `libhccl.so` 无法导入，未执行任何算子。
- 探测后另一个比赛的 NPU 进程开始运行并占用 313 MiB HBM；SLIM-ARC 随即停止，不终止、不附着也不竞争该进程。

因此，这份数据只证明 HiDevlab SSH、驱动和 910B4 硬件枚举正常，不能作为 LLM TPS、算子吞吐或 SLIM-ARC 加速证据。完整验证必须使用含匹配 CANN toolkit 的独立镜像或等待 Merlin Job 获得 Pod。
