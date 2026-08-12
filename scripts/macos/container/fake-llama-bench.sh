#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
    printf 'fake llama-bench\n'
    exit 0
fi
printf '{"build_commit":"360e134","model_type":"fixture","n_prompt":4,"n_gen":1,"avg_ts":1.0}\n'
if [[ "${VARIANT:-}" == "patched" ]]; then
    printf '%s\n' '[SLIM-ARC-RUNTIME] schema=1 expert_samples=0 expert_issued_bytes=0 expert_hit_bytes=0 expert_waste_bytes=0 reclaim_candidates=0 reclaim_calls=0 reclaimed_bytes=0 reclaim_skipped_bytes=0 reclaim_failures=0 residency_samples=0 residency_admitted_experts=0 residency_admitted_bytes=0 residency_skipped_bytes=0 residency_fallbacks=0 pressure_normal=0 pressure_high=0 pressure_critical=0' >&2
fi
