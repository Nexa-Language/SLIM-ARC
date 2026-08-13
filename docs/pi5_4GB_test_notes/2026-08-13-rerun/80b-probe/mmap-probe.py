import mmap, os, sys, time, resource
path = "/home/yituodabian/data/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
size = os.path.getsize(path)
print(f"file size = {size} bytes = {size/2**30:.2f} GiB")
fd = os.open(path, os.O_RDONLY)
# probe: mmap the whole file lazily (no populate)
t0 = time.time()
mm = mmap.mmap(fd, 0, prot=mmap.PROT_READ)
print(f"mmap() whole file took {time.time()-t0:.3f}s (lazy, no I/O yet)")
# touch first 64KB to confirm readability
mm.seek(0)
hdr = mm.read(65536)
print(f"first 64KB read ok, magic={hdr[:4]}")
# RSS after mmap should be tiny (no populate)
rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"peak RSS so far = {rss0} KB = {rss0/1024:.1f} MB")
# test madvise support on this mapping
for name in ["MADV_RANDOM","MADV_SEQUENTIAL","MADV_WILLNEED","MADV_DONTNEED"]:
    adv = getattr(mmap, name, None)
    try:
        mm.madvise(adv, 0, 4096)
        print(f"madvise {name}: OK")
    except Exception as e:
        print(f"madvise {name}: FAIL ({e})")
mm.close(); os.close(fd)
print("probe done")
