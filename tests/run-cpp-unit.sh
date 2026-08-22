#!/usr/bin/env bash

set -euo pipefail

readonly repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly source_root="$repo_root/patches/llama-upstream"
readonly test_root="$repo_root/tests/cpp"
readonly test_targets=(
    test-slim-arc-cgroup-memory
    test-slim-arc-pressure-budget
    test-slim-arc-prefetch-budget
    test-slim-arc-runtime
    test-slim-arc-kv-eviction
    test-slim-arc-page-range
    test-slim-arc-expert-reclaim
    test-slim-arc-expert-residency
    test-slim-arc-expert-transition
    test-slim-arc-unified-pressure
)

usage() {
    echo "Usage: $0 list|all|<allowlisted-test-target>" >&2
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

readonly target=$1
if [[ "$target" == "list" ]]; then
    printf '%s\n' "${test_targets[@]}"
    exit 0
fi
if [[ "$target" == "all" ]]; then
    for test_target in "${test_targets[@]}"; do
        echo "==> $test_target"
        "$0" "$test_target"
    done
    exit 0
fi

case "$target" in
    test-slim-arc-cgroup-memory)
        readonly test_source="$test_root/test-slim-arc-cgroup-memory.cpp"
        readonly module_sources=("$source_root/slim-arc-cgroup-memory.cpp")
        ;;
    test-slim-arc-pressure-budget)
        readonly test_source="$test_root/test-slim-arc-pressure-budget.cpp"
        readonly module_sources=(
            "$source_root/slim-arc-cgroup-memory.cpp"
            "$source_root/slim-arc-pressure-budget.cpp"
        )
        ;;
    test-slim-arc-prefetch-budget)
        readonly test_source="$test_root/test-slim-arc-prefetch-budget.cpp"
        readonly module_sources=(
            "$source_root/slim-arc-prefetch.cpp"
            "$source_root/slim-arc-page-range.cpp"
            "$source_root/slim-arc-expert-reclaim.cpp"
            "$source_root/slim-arc-expert-residency.cpp"
            "$source_root/slim-arc-expert-transition.cpp"
        )
        ;;
    test-slim-arc-runtime)
        readonly test_source="$test_root/test-slim-arc-runtime.cpp"
        readonly module_sources=(
            "$source_root/slim-arc-cgroup-memory.cpp"
            "$source_root/slim-arc-prefetch.cpp"
            "$source_root/slim-arc-page-range.cpp"
            "$source_root/slim-arc-expert-reclaim.cpp"
            "$source_root/slim-arc-expert-residency.cpp"
            "$source_root/slim-arc-expert-transition.cpp"
            "$source_root/slim-arc-pressure-budget.cpp"
            "$source_root/slim-arc-unified-scheduler.cpp"
            "$source_root/slim-arc-runtime.cpp"
        )
        ;;
    test-slim-arc-kv-eviction)
        readonly test_source="$test_root/test-slim-arc-kv-eviction.cpp"
        readonly module_sources=("$source_root/slim-arc-kv-eviction.cpp")
        ;;
    test-slim-arc-page-range)
        readonly test_source="$test_root/test-slim-arc-page-range.cpp"
        readonly module_sources=("$source_root/slim-arc-page-range.cpp")
        ;;
    test-slim-arc-expert-reclaim)
        readonly test_source="$test_root/test-slim-arc-expert-reclaim.cpp"
        readonly module_sources=(
            "$source_root/slim-arc-page-range.cpp"
            "$source_root/slim-arc-expert-reclaim.cpp"
        )
        ;;
    test-slim-arc-expert-residency)
        readonly test_source="$test_root/test-slim-arc-expert-residency.cpp"
        readonly module_sources=("$source_root/slim-arc-expert-residency.cpp")
        ;;
    test-slim-arc-expert-transition)
        readonly test_source="$test_root/test-slim-arc-expert-transition.cpp"
        readonly module_sources=("$source_root/slim-arc-expert-transition.cpp")
        ;;
    test-slim-arc-unified-pressure)
        readonly test_source="$test_root/test-slim-arc-unified-pressure.cpp"
        readonly module_sources=(
            "$source_root/slim-arc-cgroup-memory.cpp"
            "$source_root/slim-arc-prefetch.cpp"
            "$source_root/slim-arc-page-range.cpp"
            "$source_root/slim-arc-expert-reclaim.cpp"
            "$source_root/slim-arc-expert-residency.cpp"
            "$source_root/slim-arc-expert-transition.cpp"
            "$source_root/slim-arc-pressure-budget.cpp"
            "$source_root/slim-arc-unified-scheduler.cpp"
        )
        ;;
    *)
        echo "Unsupported C++ test target: $target" >&2
        usage
        exit 2
        ;;
esac

readonly build_root=$(mktemp -d "${TMPDIR:-/tmp}/slim-arc-cpp-test.XXXXXX")
cleanup() {
    case "$build_root" in
        "${TMPDIR:-/tmp}"/slim-arc-cpp-test.*) rm -rf -- "$build_root" ;;
        *) echo "Refusing to remove unexpected test path: $build_root" >&2 ;;
    esac
}
trap cleanup EXIT

compiler_flags=(-std=c++17 -Wall -Wextra -Werror -I "$source_root")
if [[ "${SLIM_ARC_TEST_SANITIZE:-0}" == "1" ]]; then
    compiler_flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

readonly output="$build_root/$target"
c++ "${compiler_flags[@]}" "$test_source" "${module_sources[@]}" -o "$output"
"$output"
