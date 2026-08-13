# A14 sustained-decode validation

A14 lengthens generation from `tg16` to `tg64` to reduce short-run decode
variance and validate the A13 small-tensor resident set on a more sustained
workload. Both cold runs use the same A13 image and model, 2 GiB cgroup-v2
memory, zero swap, shared-expert residency, eight/six phase threads, poll 50,
and 128 KB readahead.

| Configuration | Prefill | Sustained decode | Wall | Major faults | Input blocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shared only | 4.609123 t/s | 1.024886 t/s | 96.36 s | 1,387,876 | 418,189,296 |
| Shared + small | 4.361220 t/s | 1.017529 t/s | 96.82 s | 1,380,515 | 422,386,208 |

Small residency reduced major faults by 0.53%, but reduced prefill by 5.38%,
reduced sustained decode by 0.72%, increased wall time by 0.48%, and increased
input blocks by 1.00%. This longer run outweighs the tiny `tg16` median gains.

The finalist therefore does not enable `SLIM_ARC_SMALL_MLOCK`. The mechanism
remains strict opt-in for workload-specific experiments, while eager
shared-expert residency remains the promoted resident path at 2/4 GiB.
