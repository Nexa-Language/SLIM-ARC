# Exact expert file advice

## Problem

On the Raspberry Pi 5, speculative expert `madvise(WILLNEED)` reduced pp16
prefill throughput by 54.46%. The model resides on an NTFS-3G/FUSE filesystem
behind a USB Bulk-Only bridge, so wrong virtual-memory prefetches directly
compete with demand faults on the only I/O queue.

## Design

`SLIM_ARC_EXPERT_FADVISE=1` enables an opt-in commit-path experiment:

1. The model keeps the already-open GGUF `llama_file` objects alive for the
   lifetime of its mmap and SLIM-ARC runtime.
2. Each mmap is registered with its borrowed file descriptor.
3. Expert tensor virtual addresses are translated once to GGUF file offsets.
4. After the router exposes the actual selected expert IDs, SLIM-ARC issues
   `posix_fadvise(POSIX_FADV_WILLNEED)` only for those exact expert slices.

The file advice runs after releasing the expert-state mutex. The runtime is
destroyed before the retained files, so borrowed descriptors cannot outlive
their owner. macOS and other non-Linux builds retain the same API and default
behavior; the production syscall is Linux-only and the feature is disabled
unless the environment value is exactly `1`.

## Experiment boundary

The first deployment keeps the A36 Raspberry Pi candidate unchanged except
for this flag: FUSE, swap off, 512 MiB hot-expert LRU, pp16/tg16, four threads,
and both speculative weight/expert prefetch paths disabled. A single cold run
is enough to reject a large regression; a positive result requires a complete
run before promotion.
