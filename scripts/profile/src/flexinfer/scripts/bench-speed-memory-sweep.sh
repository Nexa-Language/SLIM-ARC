#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Run the same benchmark suite with multiple available-memory settings.
# Override from the command line, for example:
#   MEMORY_CONFIGS="0.5 1 2 4" TP=2 P=16 N=16 bash scripts/bench-speed-memory-sweep.sh
MEMORY_CONFIGS=${MEMORY_CONFIGS:-"2 4 8"}
COOLDOWN_SECONDS=${COOLDOWN_SECONDS:-600}
TP=${TP:-4}
SWEEP_FAILED=0

run_bench_speed() {
    local memory=$1

    COOLDOWN_SECONDS="$COOLDOWN_SECONDS" \
    DROP_CACHES="${DROP_CACHES:-0}" \
    DROP_CACHES_CMD="${DROP_CACHES_CMD:-}" \
    TASKSET_CPUS="${TASKSET_CPUS:-}" \
    NUMACTL_ARGS="${NUMACTL_ARGS:-}" \
    CGROUP_SPEC="${CGROUP_SPEC:-}" \
    RUN_PREFIX="${RUN_PREFIX:-}" \
    MODEL_LIST="${MODEL_LIST:-}" \
    T="${T:-}" \
    AM="$memory" TP="$TP" bash "$SCRIPT_DIR/bench-speed.sh" 2>&1 |
        while IFS= read -r line; do
            echo "$line"
        done

    return "${PIPESTATUS[0]}"
}

for MEMORY in $MEMORY_CONFIGS
do
    echo "===== Running memory config: AM=${MEMORY} ====="
    run_bench_speed "$MEMORY"
    bench_status=$?

    if [ "$bench_status" -ne 0 ]; then
        echo "Memory config failed: AM=${MEMORY}, exit_status=${bench_status}"
        SWEEP_FAILED=1
    fi
done

exit "$SWEEP_FAILED"
