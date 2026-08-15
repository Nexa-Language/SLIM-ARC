# Routed expert top-k screening

## Goal

The Qwen3-Next 80B model routes each token to ten experts. On a 4 GiB Raspberry Pi, expert weights are
faulted from a 48 GB GGUF over NTFS-3G/FUSE and USB Bulk-Only transport, so every additional selected expert
adds both storage traffic and CPU work. Further quantizing the only model copy would require another tens-of-GB
artifact, which is outside the current disk contract.

## Experimental switch

`SLIM_ARC_EXPERT_TOP_K=N` replaces Qwen3-Next's configured routed-expert count only when `N` is a strict
decimal integer in `[1, configured_top_k)`. Missing, malformed, zero, negative, equal, or larger values preserve
the model default. Both the trunk and the MTP MoE calls use the same selected value. Other model families are
unchanged.

The switch is deliberately opt-in because it changes model semantics: fewer routed experts can reduce quality
and alter all later router decisions. It is a performance/quality screening mechanism, not a default runtime
optimization. Promotion requires an adjacent same-binary flag-off performance control and a fixed-prompt output
or task-quality comparison.

## Raspberry Pi screen

Start with top-8 versus the default top-10 using one existing GGUF and the same 4-thread, no-swap, hot-cache
policy. A short pp4/tg1 run rejects candidates that do not materially improve throughput. A candidate that passes
the speed screen advances to pp16/tg16 and fixed-prompt quality checks. No model conversion or copy is needed.
