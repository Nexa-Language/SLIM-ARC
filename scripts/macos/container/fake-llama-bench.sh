#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
    printf 'fake llama-bench\n'
    exit 0
fi
printf '{"build_commit":"360e134","model_type":"fixture","n_prompt":4,"n_gen":1,"avg_ts":1.0}\n'
if [[ "${VARIANT:-}" == "patched" ]]; then
    printf '%s\n' '[SLIM-ARC-RUNTIME] schema=3 expert_samples=0 expert_issued_bytes=0 expert_hit_bytes=0 expert_waste_bytes=0 expert_advice_requests=0 expert_coalesced_ranges=0 expert_covered_bytes=0 expert_advice_failures=0 expert_invalid_ranges=0 weight_requested_bytes=0 weight_covered_bytes=0 weight_issued_bytes=0 weight_skipped_bytes=0 weight_advice_requests=0 weight_coalesced_ranges=0 weight_invalid_ranges=0 weight_advice_failures=0 weight_rounds_throttled=0 weight_stale_requests=0 weight_stale_bytes=0 weight_inflight_peak_bytes=0 reclaim_candidates=0 reclaim_calls=0 reclaimed_bytes=0 reclaim_skipped_bytes=0 reclaim_failures=0 residency_samples=0 residency_admitted_experts=0 residency_admitted_bytes=0 residency_skipped_bytes=0 residency_fallbacks=0 pressure_normal=0 pressure_high=0 pressure_critical=0' >&2
fi
