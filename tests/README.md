# 测试

## 环境测试

- `test_env.sh` — 验证 cgroups v2 三档环境配置是否正确

## 运行测试

```bash
bash tests/test_env.sh
```

`tests/test_env.sh` 依赖 Linux cgroups v2，不适用于 macOS 主机。

## macOS 受限资源测试

先运行只读 host preflight：

```bash
bash scripts/macos/preflight.sh
```

macOS 正式限额测试由专用 Colima Linux VM 提供 cgroups v2 隔离。测试不会使用 `memory_pressure` 挤压主机内存；12 小时 campaign 由 `scripts/macos/campaign.py` 持久化截止时间，重新运行命令不会延长时间窗口。

macOS 控制器、矩阵、消融配置和结果归一化的单元测试不需要启动 VM：

```bash
uv run --with pytest pytest -q tests/macos
```

正式运行由 `run_constrained.py` 强制使用 2–16 GiB、1–8 vCPU、固定模型挂载和 runner-owned 随机容器名。`run_matrix.py` 与 `run_ablation.py` 都会逐次原子保存状态，进程重启后跳过已经完成的行。
