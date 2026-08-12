#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${script_dir}/common.sh"

result_dir="${1:?usage: probe-guest.sh <result-dir>}"
assert_safe_result_dir "${result_dir}"
mkdir -p "${result_dir}"

profile="$(slim_arc_profile_name)"
docker_context="colima-${profile}"
probe_path="${result_dir}/guest-probe.env"
raw_path="${result_dir}/guest-probe-raw.txt"

if ! colima --profile "${profile}" status >/dev/null 2>&1; then
    printf 'Colima profile is not running: %s\n' "${profile}" >&2
    exit 1
fi

cgroup_fs="$(colima --profile "${profile}" ssh -- stat -fc %T /sys/fs/cgroup | tr -d '\r')"
controllers="$(colima --profile "${profile}" ssh -- cat /sys/fs/cgroup/cgroup.controllers | tr -d '\r')"
guest_arch="$(colima --profile "${profile}" ssh -- uname -m | tr -d '\r')"
docker_cgroup_version="$(DOCKER_CONTEXT="${docker_context}" docker info --format '{{.CgroupVersion}}')"
docker_cgroup_driver="$(DOCKER_CONTEXT="${docker_context}" docker info --format '{{.CgroupDriver}}')"
docker_arch="$(DOCKER_CONTEXT="${docker_context}" docker info --format '{{.Architecture}}')"
disk_kib="$(colima --profile "${profile}" ssh -- df -Pk /var/lib/slim-arc | awk 'NR == 2 { print $2 }')"
guest_memory_kib="$(colima --profile "${profile}" ssh -- awk '/^MemTotal:/ { print $2 }' /proc/meminfo)"
guest_cpus="$(colima --profile "${profile}" ssh -- getconf _NPROCESSORS_ONLN)"
container_limits="$(DOCKER_CONTEXT="${docker_context}" docker run --rm --memory 64m --memory-swap 64m alpine:3.22 sh -c '
    printf "memory.max="
    cat /sys/fs/cgroup/memory.max
    printf "memory.swap.max="
    cat /sys/fs/cgroup/memory.swap.max
')"
container_memory_max="$(awk -F= '/^memory.max=/ { print $2 }' <<<"${container_limits}")"
container_swap_max="$(awk -F= '/^memory.swap.max=/ { print $2 }' <<<"${container_limits}")"

cgroup_version=0
if [[ "${cgroup_fs}" == "cgroup2fs" ]]; then
    cgroup_version=2
fi
memory_controller=0
if grep -qw memory <<<"${controllers}"; then
    memory_controller=1
fi
swap_controller=0
if [[ "${container_swap_max}" == "0" ]]; then
    swap_controller=1
fi

{
    printf 'CGROUP_VERSION=%s\n' "${cgroup_version}"
    printf 'MEMORY_CONTROLLER=%s\n' "${memory_controller}"
    printf 'SWAP_CONTROLLER=%s\n' "${swap_controller}"
    printf 'ARCH=%s\n' "${guest_arch}"
    printf 'DOCKER_CGROUP_VERSION=%s\n' "${docker_cgroup_version}"
    printf 'DOCKER_CGROUP_DRIVER=%s\n' "${docker_cgroup_driver}"
    printf 'DOCKER_ARCH=%s\n' "${docker_arch}"
    printf 'GUEST_DISK_KIB=%s\n' "${disk_kib}"
    printf 'GUEST_MEMORY_KIB=%s\n' "${guest_memory_kib}"
    printf 'GUEST_CPUS=%s\n' "${guest_cpus}"
    printf 'TEST_CONTAINER_MEMORY_MAX=%s\n' "${container_memory_max}"
    printf 'TEST_CONTAINER_SWAP_MAX=%s\n' "${container_swap_max}"
} >"${probe_path}"

{
    colima --profile "${profile}" status --extended
    DOCKER_CONTEXT="${docker_context}" docker info
    colima --profile "${profile}" ssh -- df -h /var/lib/slim-arc
    colima --profile "${profile}" ssh -- cat /sys/fs/cgroup/cgroup.controllers
    printf '%s\n' "${container_limits}"
} | sed "s#${HOME}#<HOME>#g" >"${raw_path}"

if [[ "${cgroup_version}" != "2" || "${memory_controller}" != "1" || "${swap_controller}" != "1" || "${guest_arch}" != "aarch64" || "${docker_cgroup_version}" != "2" || "${docker_arch}" != "aarch64" ]]; then
    printf 'Guest resource isolation probe failed; see %s\n' "${probe_path}" >&2
    exit 1
fi

if (( disk_kib < 90 * 1024 * 1024 )); then
    printf 'Guest data filesystem has less than 90 GiB usable capacity: %s KiB\n' "${disk_kib}" >&2
    exit 1
fi

cat "${probe_path}"
