#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
source "${repo_root}/scripts/macos/download-model-segmented-guest.sh"

actual="$(compute_ranges 10 20 3)"
expected=$'0 10 13\n1 14 16\n2 17 19'
[[ "${actual}" == "${expected}" ]]

actual="$(compute_ranges 0 2 8)"
expected=$'0 0 0\n1 1 1'
[[ "${actual}" == "${expected}" ]]
