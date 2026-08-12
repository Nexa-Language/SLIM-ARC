#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${script_dir}/common.sh"

profile="$(slim_arc_profile_name)"
docker_context="colima-${profile}"

bash "${script_dir}/preflight.sh"

if ! command -v colima >/dev/null 2>&1; then
    brew install colima
fi
if ! command -v docker >/dev/null 2>&1; then
    brew install docker
fi

original_docker_context="$(docker context show)"
restore_docker_context() {
    local current_context
    current_context="$(docker context show 2>/dev/null || true)"
    if [[ -n "${original_docker_context}" && "${current_context}" != "${original_docker_context}" ]]; then
        docker context use "${original_docker_context}" >/dev/null
    fi
}
trap restore_docker_context EXIT

if colima --profile "${profile}" status >/dev/null 2>&1; then
    printf 'COLIMA_PROFILE_STATE=running\n'
else
    colima start \
        --profile "${profile}" \
        --activate=false \
        --arch aarch64 \
        --cpu 8 \
        --memory 16 \
        --disk 100 \
        --runtime docker
fi

data_root="/mnt/lima-colima-${profile}/slim-arc"
colima --profile "${profile}" ssh -- sudo install -d -m 0755 \
    "${data_root}" \
    "${data_root}/models" \
    "${data_root}/cache"

link_state="$(colima --profile "${profile}" ssh -- sh -c '
    if test -L /var/lib/slim-arc; then
        printf symlink
    elif test -d /var/lib/slim-arc; then
        printf directory
    else
        printf absent
    fi
' | tr -d '\r')"
if [[ "${link_state}" == "symlink" ]]; then
    current_target="$(colima --profile "${profile}" ssh -- readlink /var/lib/slim-arc | tr -d '\r')"
    if [[ "${current_target}" != "${data_root}" ]]; then
        printf 'Refusing to replace unexpected /var/lib/slim-arc symlink: %s\n' "${current_target}" >&2
        exit 1
    fi
elif [[ "${link_state}" == "directory" ]]; then
    colima --profile "${profile}" ssh -- sudo rmdir \
        /var/lib/slim-arc/models \
        /var/lib/slim-arc/cache \
        /var/lib/slim-arc
    colima --profile "${profile}" ssh -- sudo ln -s "${data_root}" /var/lib/slim-arc
elif [[ "${link_state}" == "absent" ]]; then
    colima --profile "${profile}" ssh -- sudo ln -s "${data_root}" /var/lib/slim-arc
else
    printf 'Unable to classify /var/lib/slim-arc state: %s\n' "${link_state}" >&2
    exit 1
fi

if ! docker context inspect "${docker_context}" >/dev/null 2>&1; then
    printf 'Expected Docker context not found: %s\n' "${docker_context}" >&2
    exit 1
fi

printf 'COLIMA_PROFILE=%s\n' "${profile}"
printf 'DOCKER_CONTEXT=%s\n' "${docker_context}"
printf 'GUEST_DATA_ROOT=%s\n' "${data_root}"
colima --profile "${profile}" status --extended
