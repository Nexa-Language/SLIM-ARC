#!/usr/bin/env bash
set -euo pipefail

probe="${1:-$(mktemp /tmp/slim-arc-guest-probe.XXXXXX)}"
cleanup_probe=0
if [[ $# -eq 0 ]]; then
    cleanup_probe=1
fi
trap 'if (( cleanup_probe )); then rm -f "${probe}"; fi' EXIT

cat >"${probe}" <<'EOF'
CGROUP_VERSION=2
MEMORY_CONTROLLER=1
SWAP_CONTROLLER=1
ARCH=aarch64
DOCKER_CGROUP_VERSION=2
DOCKER_ARCH=aarch64
TEST_CONTAINER_MEMORY_MAX=67108864
TEST_CONTAINER_SWAP_MAX=0
EOF

grep -qx 'CGROUP_VERSION=2' "${probe}"
grep -qx 'MEMORY_CONTROLLER=1' "${probe}"
grep -qx 'SWAP_CONTROLLER=1' "${probe}"
grep -qx 'ARCH=aarch64' "${probe}"
grep -qx 'DOCKER_CGROUP_VERSION=2' "${probe}"
grep -qx 'DOCKER_ARCH=aarch64' "${probe}"
grep -qx 'TEST_CONTAINER_MEMORY_MAX=67108864' "${probe}"
grep -qx 'TEST_CONTAINER_SWAP_MAX=0' "${probe}"
