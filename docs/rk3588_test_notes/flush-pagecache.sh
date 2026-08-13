#!/bin/bash
# SLIM-ARC FIX 2026-08-13: 无 sudo 权限时的 page cache 冲刷替代方案。
# 原理: 在无限制 cgroup 中的 python 进程持续分配并写入匿名内存，
#       对系统施加全局内存压力，内核被迫回收全局 page cache（含模型文件缓存页）。
#       必须在无限制 cgroup 中执行——受限 cgroup 内匿名页不可换出且无法
#       驱逐其他 cgroup 的 page cache，只会触发本 cgroup OOM。
# 用法: flush-pagecache.sh <目标冲刷量 GB，默认 7>
set -u
TARGET_GB="${1:-7}"

ALLOC_PY=$(cat <<EOF
import sys
target = int("$TARGET_GB") * 1024 * 1024 * 1024
chunk = 4 * 1024 * 1024
total = 0
bufs = []
try:
    while total < target:
        b = bytearray(chunk)
        for i in range(0, chunk, 4096):
            b[i] = 1
        bufs.append(b)
        total += chunk
except MemoryError:
    pass
sys.stderr.write("flushed_bytes=%d (%d MB)\n" % (total, total // 1024 // 1024))
EOF
)

echo "[flush] $(date '+%H:%M:%S') 冲刷目标 ${TARGET_GB}GB（无限制 cgroup 匿名挤压）"
free -m | head -2
python3 -c "$ALLOC_PY" 2>&1
echo "[flush] 完成 rc=$? 时间 $(date '+%H:%M:%S')"
free -m | head -2
