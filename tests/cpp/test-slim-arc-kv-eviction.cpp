#include "slim-arc-kv-eviction.h"

#include <cassert>
#include <cstdint>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

int main() {
    char path[] = "/tmp/slim-arc-kv-resize.XXXXXX";
    const int fd = mkstemp(path);
    assert(fd >= 0);
    unlink(path);

    constexpr size_t old_size = 4096;
    constexpr size_t new_size = 8192;
    assert(ftruncate(fd, old_size) == 0);

    void * base = mmap(nullptr, old_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    assert(base != MAP_FAILED);
    static_cast<uint8_t *>(base)[0] = 0x5a;

    assert(slim_arc::detail::resize_file_mapping(fd, base, old_size, new_size));
    assert(base != MAP_FAILED);
    assert(static_cast<uint8_t *>(base)[0] == 0x5a);
    static_cast<uint8_t *>(base)[new_size - 1] = 0xa5;
    assert(msync(base, new_size, MS_SYNC) == 0);

    assert(munmap(base, new_size) == 0);
    assert(close(fd) == 0);
    return 0;
}
