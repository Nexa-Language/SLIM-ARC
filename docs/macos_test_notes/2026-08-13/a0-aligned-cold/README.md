# A0 aligned-prefetch cold diagnostic

This directory records one diagnostic run of the aligned and coalesced
prefetch implementation. It is not a performance-promotion result because it
contains one cold-cache repetition and has no interleaved baseline control.

## Fixed identity and resource contract

- SLIM-ARC commit: `b0240cbb932b1906325c92afe96f040b0a4f89cf`
- Runtime image: `sha256:e396dd9a61f36c467c8f02baaf4d5320ece993cf28cb1c7047c91fa2de7a7f28`
- llama.cpp: `360e1349f`
- Model SHA-256: `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`
- Workload: `pp64/tg16`, one repetition, no warmup, cold cache
- Limits: 2 GiB memory, 4 CPUs, cgroup v2, `memory.swap.max=0`

## Diagnostic result

- Outcome: success; no OOM and no swap
- Prefill: 3.519132 tokens/s
- Decode: 0.587988 tokens/s
- Wall time: 70.46 seconds
- Peak cgroup memory: 2,147,483,648 bytes
- Block-device reads: 115,562,573,824 bytes
- Major page faults: 397,366
- I/O pressure `avg10`: 34.70%

All aligned advice counters were valid: expert and weight invalid ranges and
advice failures were zero. Expert prefetch issued 13,800,984,576 bytes, of
which 4,239,310,848 bytes were later used and 9,561,673,728 bytes were waste.
Weight prefetch requested 2,051,590,098,432 bytes and issued
151,824,785,408 bytes after the current budget. These values validate the A0
page-correctness fix while identifying graph-wide over-prefetch as the A1
bottleneck.
