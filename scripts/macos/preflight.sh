#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${script_dir}/common.sh"

require_command brew
require_command python3
require_command uv
require_command git
require_free_disk_gib 120

os_name="$(uname -s)"
architecture="$(uname -m)"
if [[ "${os_name}" != "Darwin" ]]; then
    printf 'This host preflight requires macOS, found %s\n' "${os_name}" >&2
    exit 1
fi
if [[ "${architecture}" != "arm64" ]]; then
    printf 'This benchmark requires Apple Silicon arm64, found %s\n' "${architecture}" >&2
    exit 1
fi

memory_bytes="$(sysctl -n hw.memsize)"
logical_cpus="$(sysctl -n hw.logicalcpu)"
free_disk_gib="$(slim_arc_free_disk_gib "$(slim_arc_repo_root)")"

printf 'HOST_OS=%s\n' "${os_name}"
printf 'HOST_ARCH=%s\n' "${architecture}"
printf 'HOST_MEMORY_BYTES=%s\n' "${memory_bytes}"
printf 'HOST_LOGICAL_CPUS=%s\n' "${logical_cpus}"
printf 'HOST_FREE_DISK_GIB=%s\n' "${free_disk_gib}"
