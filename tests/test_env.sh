#!/usr/bin/env bash
# Test: verify cgroups v2 tiers are correctly configured.
set -euo pipefail

echo "=== SLIM-ARC Environment Test ==="

if ! mountpoint -q /sys/fs/cgroup; then
    echo "FAIL: cgroups v2 not mounted at /sys/fs/cgroup"
    exit 1
fi
echo "PASS: cgroups v2 mounted"

for tier in low mid high; do
    path="/sys/fs/cgroup/slim-arc-$tier"
    if [ ! -d "$path" ]; then
        echo "FAIL: cgroup slim-arc-$tier not found"
        exit 1
    fi
    mem=$(cat "$path/memory.max")
    cpus=$(cat "$path/cpuset.cpus")
    echo "PASS: slim-arc-$tier (memory.max=$mem, cpus=$cpus)"
done

echo ""
echo "All environment tests passed."
