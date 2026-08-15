# Hot expert budget extension

## Motivation

The Pi 5 A36 LRU candidate filled nearly all of its 512 MiB hot-expert budget and still recorded a
median 624 evictions over pp16/tg16. The existing parser rejected every value above 512 MiB, so the
runtime could not test whether spending part of the remaining 4 GiB device memory on a larger
resident expert set reduces SSD traffic.

## Change

`SLIM_ARC_EXPERT_HOT_MB` now accepts the inclusive range `1..1024`. The feature remains opt-in and
the unset/default behavior is unchanged. The Mac controller, container runner and run-manifest
validator use the same boundary so Pi and Mac evidence cannot silently describe different policies.

The boundary is deliberately capped at 1 GiB. It is large enough to screen 768 MiB and 1024 MiB on
the Pi without turning the environment variable into an unbounded `mlock` request.

## Experiment order

1. Finish the A43 512 MiB expert-prefetch attribution on the current NTFS-3G/FUSE path.
2. Deploy the extended parser with expert prefetch still disabled.
3. Screen 768 MiB against the A36 512 MiB contract: cold cache, no swap, 4 threads, pp16/tg16.
4. Run 1024 MiB only if 768 MiB neither OOMs nor loses prefill throughput.
5. Promote only an end-to-end TPS/wall improvement; lower evictions alone are not sufficient.

The screen stops early on OOM, failure to restore zram, or a clear prefill regression. The 48 GB
model remains a single file on the existing SSD; changing this limit creates no model copy.
