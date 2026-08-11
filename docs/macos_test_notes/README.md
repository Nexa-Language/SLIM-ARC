# macOS 受限资源实验记录

本目录保存 macOS 主机上的 SLIM-ARC 可复现实验元数据、原始日志和汇总结果。正式物理内存与 CPU 限制由名为 `slim-arc` 的 Colima ARM64 Linux VM 和 Docker cgroups v2 提供。

## 边界

- 80B GGUF、Docker image、llama.cpp build 和下载缓存只保存在 VM `/var/lib/slim-arc/`，不进入 Git。Colima 0.10 的该路径指向 profile 的 100 GiB 独立数据盘，不使用 20 GiB guest root filesystem。
- 结果目录必须位于本目录的日期子目录下。
- 正式无 swap 结果要求容器 `memory.swap.max=0`。
- Linux CPU-only 数据不代表 macOS Metal 性能。
- 不使用 macOS `memory_pressure`，不修改主机 swap 或全局内存策略。

## 入口

```bash
bash scripts/macos/preflight.sh
uv run python scripts/macos/campaign.py start \
  --hours 12 \
  --state docs/macos_test_notes/2026-08-11/campaign.json
bash scripts/macos/setup-colima.sh
bash scripts/macos/probe-guest.sh \
  docs/macos_test_notes/2026-08-11/preflight
```

重复执行 `campaign.py start` 会读取原有 deadline，不会延长 12 小时窗口。
