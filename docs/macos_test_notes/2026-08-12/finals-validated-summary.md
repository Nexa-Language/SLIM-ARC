# Finals validated evidence summary

Scope: the isolated 2026-08-12 campaign only. Its source is `dbec00e8d25af93219dc0d70079ea08603f0e860`; patched-source SHA-256 is `cef025d8d26fe9e357457ad787e7ca545442fc47f6c919d168202b272a94167c`; image is `sha256:508d51ad8576a00182edbdfd50680f650f4307d228a3daabd9ced6d2838187d6`; llama.cpp is `360e1349f0009c5ad99d21e3c4546b707addc68a`; model SHA-256 is `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`.

Contract: 2 GiB (`2147483648` bytes), 4 CPUs, no swap, `pp=64`, `tg=16`, exact two rounds per configuration/cache state. All 20/20 runs terminated `success`, and every recorded peak is exactly 2 GiB. The auditable per-run terminal index is in `finals-evidence.json`; cache-separated median metrics and deltas are in `finals-evidence.csv`.

The cold combined median wall time is 79.525 s versus 66.3 s for patched-control: `((79.525 / 66.3) - 1) * 100 = 19.947209653092%` regression. Therefore combined is rejected overall. Reclaim is retained only as opt-in mechanism correctness: across its eight enabled runs, `reclaim_calls=0`, `reclaim_candidates=0`, and `reclaimed_bytes=0`; performance differences cannot be attributed to reclamation. Residency is also opt-in: every enabled run records 768 critical samples, 13,929,971,712 skipped bytes, zero admitted bytes, and zero fallbacks. At 2 GiB it fails closed; it is not a promotion claim.

Historical pre-linkage rows are invalid for device comparison and are excluded. This record preserves the negative result and makes no superseded `64.5x` or `850%` claim.
