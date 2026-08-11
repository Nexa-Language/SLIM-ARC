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
