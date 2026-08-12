#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
source "${repo_root}/scripts/macos/common.sh"

test "$(slim_arc_profile_name)" = "slim-arc"
test "$(slim_arc_repo_root)" = "${repo_root}"

if assert_safe_result_dir "/"; then
    echo "root must be rejected" >&2
    exit 1
fi

if assert_safe_result_dir "${repo_root}"; then
    echo "repository root must be rejected" >&2
    exit 1
fi

if assert_safe_result_dir "${repo_root}/docs/macos_test_notes/../papers"; then
    echo "unresolved parent path must be rejected" >&2
    exit 1
fi

assert_safe_result_dir "${repo_root}/docs/macos_test_notes/2026-08-11"
assert_safe_result_dir "docs/macos_test_notes/2026-08-11"

if assert_safe_result_dir "docs/macos_test_notes/../../outside"; then
    echo "relative escape must be rejected" >&2
    exit 1
fi
