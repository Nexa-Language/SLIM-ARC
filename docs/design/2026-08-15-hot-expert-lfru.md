# Hot-expert LFRU replacement

## Goal

Reduce repeated USB-storage reads during memory-constrained Qwen3-Next
80B-A3B decode on Raspberry Pi 5. The next experiment changes only the
hot-expert victim selection policy so its effect can be isolated from expert
admission and prefetching.

## Scope

The implementation adds the strict opt-in flag
`SLIM_ARC_EXPERT_HOT_LFRU=1`. It is effective only when the existing hot cache
and LRU retention are also enabled. With the new flag absent or set to any
other value, current LRU behavior remains unchanged.

This round does not:

- enlarge the admission history window;
- issue `WILLNEED` for candidate experts;
- read non-resident pages merely to populate the cache;
- change the hot-cache byte budget;
- add a trained replacement model.

## Policy

Each admitted `expert_hot_entry` stores a saturating `frequency` initialized to
one. A cache hit increments `frequency` and advances the existing logical touch
clock. When space is required, entries selected by the current router
observation remain protected. Every other entry receives this retention score:

```text
frequency / (current_clock - last_touch + 1)
```

The entry with the lowest score is evicted. Scores are compared by integer
cross multiplication, avoiding floating-point work in the decode path. Exact
score ties evict the older entry; a final `(layer, expert_id)` ordering makes the
choice deterministic. Clock and frequency saturation retain deterministic
behavior rather than wrapping.

The policy deliberately uses entry access frequency rather than the existing
global popularity counters. Entry-local frequency starts when an expert enters
the bounded cache, so stale history from earlier prompts cannot make an entry
permanently resident. Age in the denominator eventually makes an inactive hot
entry evictable.

## Data flow

1. The router observation produces the same stable-expert admission set as the
   current implementation.
2. An admitted-entry hit updates `frequency` and `last_touch`.
3. A miss still calls `mincore` and keeps only page ranges already resident.
4. If the byte budget is full, LFRU chooses victims until the resident ranges
   fit.
5. Existing `mlock`, `munlock`, byte accounting, and metrics remain the source
   of truth.

The hot-cache mutex continues to cover entry metadata and replacement. No disk
advice or new background worker is introduced.

## Minimal verification

One focused C++ regression freezes four behaviors:

1. exact opt-in parsing;
2. a frequently hit but temporarily idle entry survives over a recently
   admitted one with a lower LFRU score;
3. current stable experts are never chosen as victims;
4. flag-off eviction remains the existing LRU order.

Only the existing `test-slim-arc-prefetch-budget` target and `git diff --check`
are required before deployment.

## Raspberry Pi experiment

The existing model, source tree, build directory, USB storage, and no-swap
runner are reused. No model copy or new container image is created.

- A36: 512 MiB hot cache, LRU enabled, LFRU disabled.
- A37: 512 MiB hot cache, LRU and LFRU enabled.
- Common contract: cold page cache, swap disabled, four CPU threads,
  `pp16/tg16`, expert and weight prefetch disabled.
- Order: A36, A37, A37, A36 when time and device availability permit.

Primary metrics are wall time and decode tokens per second. Prefill tokens per
second, major faults, file input bytes, admissions, hits, evictions, locked
bytes, and non-resident bytes explain the result but cannot promote a policy by
themselves.

## Decision rule

Promote LFRU only if repeated real-device runs show a consistent wall-time or
decode-throughput improvement over same-build LRU. If it only changes cache
counters or increases churn without end-to-end improvement, revert the flag's
use on Raspberry Pi and move to temporal admission as the next experiment.

## Risks and containment

- A short `tg16` run may understate frequency-based benefits. A positive screen
  should be followed by a longer decode; a negative screen is not a universal
  rejection.
- Integer comparison must avoid overflow. The implementation will use widened
  multiplication supported by the pinned macOS and Linux C++ toolchains.
- Partial resident ranges make entry sizes variable. This first experiment
  intentionally keeps the paper/RFC frequency-age score unchanged; a later
  value-per-byte policy requires separate evidence.
