# macOS constrained 80B benchmark

All primary rows use cgroups v2 with swap disabled.

- Model SHA-256: `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`
- llama.cpp: `360e134`
- Lowest observed survival tier: 2 GiB
- Lowest stable tier: 2 GiB

## Evidence gate

- Best warm row: `ablation-patched-no-prefetch-warm-20260811t144607z-c7c87f` at 52.55s.
- `ablation-patched-no-prefetch-warm-20260811t144607z-c7c87f` is 4.59% faster than `ablation-patched-default-warm-20260811t144357z-383272` (52.55s / 55.08s).
- `ablation-patched-no-prefetch-warm-20260811t144607z-c7c87f` is 5.02% faster than `ablation-baseline-warm-20260811t144146z-b4ee53` (52.55s / 55.33s).
- Best cold row: `ablation-baseline-cold-20260811t144037z-0949a9` at 68.29s.
- Start plan 23 pressure admission: yes.
- Each ablation cache row has one repetition; promotion still requires the plan 23 A/B gate.
- CPU curve: 2 CPU `cpu-2c-20260811t143036z-65a51a` 75.06s, 4 CPU `cpu-4c-20260811t143308z-2ca815` 68.56s, 6 CPU `cpu-6c-20260811t143527z-7d5545` 66.28s, 8 CPU `cpu-8c-20260811t143741z-81c163` 66.72s.
- No OOM boundary was observed down to the 2 GiB controller floor.

## Runs

| Run | Config | Memory | CPUs | Cache | Outcome | Peak bytes | wall s | pp t/s | tg t/s |
|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| `12g-patched-smoke` | `patched-default` | 12 GiB | 4 | cold | success | 12884901888 | 44.78 | 0.6282 | 1.7935 |
| `ablation-baseline-cold-20260811t144037z-0949a9` | `baseline` | 2 GiB | 4 | cold | success | 2147483648 | 68.29 | 3.4443 | 0.5711 |
| `ablation-baseline-warm-20260811t144146z-b4ee53` | `baseline` | 2 GiB | 4 | warm | success | 2147483648 | 55.33 | 3.3064 | 1.1004 |
| `ablation-patched-decode-normal-cold-20260811t144911z-18e14c` | `patched-SLIM_ARC_DECODE_MADV=NORMAL` | 2 GiB | 4 | cold | success | 2147483648 | 72.28 | 3.2494 | 0.5683 |
| `ablation-patched-decode-normal-warm-20260811t145025z-7e3990` | `patched-SLIM_ARC_DECODE_MADV=NORMAL` | 2 GiB | 4 | warm | success | 2147483648 | 54.96 | 3.2917 | 1.1416 |
| `ablation-patched-decode-random-cold-20260811t145120z-ba9179` | `patched-SLIM_ARC_DECODE_MADV=RANDOM` | 2 GiB | 4 | cold | success | 2147483648 | 75.44 | 3.1701 | 0.4988 |
| `ablation-patched-decode-random-warm-20260811t145238z-bb51a2` | `patched-SLIM_ARC_DECODE_MADV=RANDOM` | 2 GiB | 4 | warm | success | 2147483648 | 56.41 | 3.3324 | 1.1091 |
| `ablation-patched-decode-sequential-cold-20260811t144701z-bf3d1a` | `patched-SLIM_ARC_DECODE_MADV=SEQUENTIAL` | 2 GiB | 4 | cold | success | 2147483648 | 71.92 | 3.3168 | 0.5465 |
| `ablation-patched-decode-sequential-warm-20260811t144814z-41a952` | `patched-SLIM_ARC_DECODE_MADV=SEQUENTIAL` | 2 GiB | 4 | warm | success | 2147483648 | 55.80 | 3.3063 | 1.1216 |
| `ablation-patched-default-cold-20260811t144242z-5b785d` | `patched-default` | 2 GiB | 4 | cold | success | 2147483648 | 73.66 | 3.3133 | 0.5242 |
| `ablation-patched-default-warm-20260811t144357z-383272` | `patched-default` | 2 GiB | 4 | warm | success | 2147483648 | 55.08 | 3.3205 | 1.1460 |
| `ablation-patched-expert-budget-confidence-cold-20260811t145545z-4b6735` | `patched-SLIM_ARC_EXPERT_BUDGET=1+SLIM_ARC_EXPERT_CONF=1` | 2 GiB | 4 | cold | success | 2147483648 | 70.77 | 3.2833 | 0.5530 |
| `ablation-patched-expert-budget-confidence-warm-20260811t145657z-c6e4ae` | `patched-SLIM_ARC_EXPERT_BUDGET=1+SLIM_ARC_EXPERT_CONF=1` | 2 GiB | 4 | warm | success | 2147483648 | 54.70 | 3.4441 | 1.1408 |
| `ablation-patched-expert-confidence-cold-20260811t145334z-b78d50` | `patched-SLIM_ARC_EXPERT_CONF=1` | 2 GiB | 4 | cold | success | 2147483648 | 72.27 | 3.1509 | 0.5715 |
| `ablation-patched-expert-confidence-warm-20260811t145448z-854206` | `patched-SLIM_ARC_EXPERT_CONF=1` | 2 GiB | 4 | warm | success | 2147483648 | 55.97 | 3.5029 | 1.1255 |
| `ablation-patched-no-prefetch-cold-20260811t144453z-3413a3` | `patched-SLIM_ARC_NO_PREFETCH=1` | 2 GiB | 4 | cold | success | 2147483648 | 72.52 | 3.3284 | 0.5276 |
| `ablation-patched-no-prefetch-warm-20260811t144607z-c7c87f` | `patched-SLIM_ARC_NO_PREFETCH=1` | 2 GiB | 4 | warm | success | 2147483648 | 52.55 | 3.6655 | 1.1993 |
| `cpu-2c-20260811t143036z-65a51a` | `patched-default` | 2 GiB | 2 | cold | success | 2147483648 | 75.06 | 3.0264 | 0.5565 |
| `cpu-4c-20260811t143308z-2ca815` | `patched-default` | 2 GiB | 4 | cold | success | 2147483648 | 68.56 | 3.4546 | 0.6123 |
| `cpu-6c-20260811t143527z-7d5545` | `patched-default` | 2 GiB | 6 | cold | success | 2147483648 | 66.28 | 3.5298 | 0.6481 |
| `cpu-8c-20260811t143741z-81c163` | `patched-default` | 2 GiB | 8 | cold | success | 2147483648 | 66.72 | 3.6558 | 0.6234 |
| `stable-2g-cold-20260811t142833z-fac323` | `patched-default` | 2 GiB | 4 | cold | success | 2147483648 | 68.48 | 3.5409 | 0.5615 |
| `stable-2g-warm-20260811t142943z-75ae5c` | `patched-default` | 2 GiB | 4 | warm | success | 2147483648 | 52.95 | 3.6336 | 1.2555 |
| `survival-12g-20260811t142148z-e6d577` | `patched-default` | 12 GiB | 4 | cold | success | 12884901888 | 40.11 | 0.5533 | 2.2117 |
| `survival-12g-20260811t142230z-4539c9` | `patched-default` | 12 GiB | 4 | cold | success | 12884901888 | 36.68 | 0.5772 | 2.1916 |
| `survival-2g-20260811t142733z-15ee2e` | `patched-default` | 2 GiB | 4 | cold | success | 2147483648 | 28.79 | 0.7981 | 0.5560 |
| `survival-2g-20260811t142803z-0b3d75` | `patched-default` | 2 GiB | 4 | cold | success | 2147483648 | 27.74 | 0.8136 | 0.4988 |
| `survival-3g-20260811t142634z-421400` | `patched-default` | 3 GiB | 4 | cold | success | 3221225472 | 27.56 | 0.8007 | 0.6330 |
| `survival-3g-20260811t142703z-f08a09` | `patched-default` | 3 GiB | 4 | cold | success | 3221225472 | 27.97 | 0.6813 | 0.5114 |
| `survival-4g-20260811t142538z-b845c5` | `patched-default` | 4 GiB | 4 | cold | success | 4294967296 | 26.60 | 0.7904 | 0.9174 |
| `survival-4g-20260811t142606z-747a42` | `patched-default` | 4 GiB | 4 | cold | success | 4294967296 | 26.75 | 0.7891 | 0.9323 |
| `survival-6g-20260811t142429z-d4ab83` | `patched-default` | 6 GiB | 4 | cold | success | 6442450944 | 32.97 | 0.6077 | 2.0330 |
| `survival-6g-20260811t142504z-151b37` | `patched-default` | 6 GiB | 4 | cold | success | 6442450944 | 31.66 | 0.6575 | 2.6993 |
| `survival-8g-20260811t142309z-4691d3` | `patched-default` | 8 GiB | 4 | cold | success | 8589934592 | 36.78 | 0.4904 | 1.8827 |
| `survival-8g-20260811t142348z-98a99f` | `patched-default` | 8 GiB | 4 | cold | success | 8589934592 | 38.47 | 0.5294 | 1.7681 |
