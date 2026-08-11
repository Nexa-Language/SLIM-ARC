#!/usr/bin/env bash

slim_arc_repo_root() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
    cd "${script_dir}/../.." && pwd -P
}
slim_arc_profile_name() {
    printf '%s\n' "slim-arc"
}

require_command() {
    local command_name="${1:?command name is required}"
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "${command_name}" >&2
        return 1
    fi
}

slim_arc_free_disk_gib() {
    local target="${1:?target path is required}"
    df -Pk "${target}" | awk 'NR == 2 { print int($4 / 1024 / 1024) }'
}

require_free_disk_gib() {
    local minimum="${1:?minimum GiB is required}"
    local available
    available="$(slim_arc_free_disk_gib "$(slim_arc_repo_root)")"
    if [[ ! "${available}" =~ ^[0-9]+$ ]]; then
        printf 'Unable to determine available disk space\n' >&2
        return 1
    fi
    if (( available < minimum )); then
        printf 'Insufficient disk: need %s GiB, have %s GiB\n' "${minimum}" "${available}" >&2
        return 1
    fi
}

assert_safe_result_dir() {
    local candidate="${1:-}"
    local repo_root
    local result_root
    repo_root="$(slim_arc_repo_root)"
    result_root="${repo_root}/docs/macos_test_notes"

    if [[ -z "${candidate}" ]]; then
        return 1
    fi
    case "${candidate}" in
        *"/../"*|*"/.."|"../"*|"..") return 1 ;;
    esac
    if [[ "${candidate}" != /* ]]; then
        candidate="${repo_root}/${candidate#./}"
    fi
    if [[ "${candidate}" == "/" || "${candidate}" == "${HOME:-}" || "${candidate}" == "${repo_root}" || "${candidate}" == "${result_root}" ]]; then
        return 1
    fi
    [[ "${candidate}" == "${result_root}/"* ]]
}
