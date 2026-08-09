/*
 * madvise-trace.c - LD_PRELOAD 拦截库（验证工具，测试后删除）
 * 拦截 posix_madvise / madvise，记录 advice 类型、长度与地址
 * 用途：观测 MoE 专家预取（小范围 WILLNEED）是否触发
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/syscall.h>

static const char * advice_name(int a) {
    switch (a) {
        case 0: return "NORMAL";
        case 1: return "RANDOM";
        case 2: return "SEQUENTIAL";
        case 3: return "WILLNEED";
        case 4: return "DONTNEED";
        default: return "OTHER";
    }
}
static void trace(int advice, size_t len, const char * func) {
    fprintf(stderr, "[%s] advice=%s len=%zu bytes (%.2f MiB)\n",
            func, advice_name(advice), len, len / 1048576.0);
}
int posix_madvise(void * addr, size_t len, int advice) {
    trace(advice, len, "posix_madvise");
    return syscall(SYS_madvise, addr, len, advice);
}
int madvise(void * addr, size_t len, int advice) {
    trace(advice, len, "madvise");
    return syscall(SYS_madvise, addr, len, advice);
}
