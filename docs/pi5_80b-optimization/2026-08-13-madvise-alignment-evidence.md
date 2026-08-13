# posix_madvise 页对齐实证：80B 新二进制 issued=0 回归根因（2026-08-13）

## 1. 现象

Pi5 4GB 上用新二进制（finals-runtime，b106 源码树重建编译）跑 Qwen3-Next-80B-A3B（默认配置）：

```
[SLIM-ARC-METRICS] expert prefetch: samples=1680 issued=0.0MB hit=0.0MB waste=0.0MB hit_rate=0.00%
```

对比 08-13 旧二进制默认配置：`issued=8718.8MB hit_rate=31.38%`。

后果：所有专家访问退化为 demand-fault（majflt≈465k，read_bytes=42.5GB > 模型 38GB，即反复缺页重读），
单轮 tg32 从 457s 退化到 ~700s（14min+）。

## 2. 根因

`src/llama-upstream/src/slim-arc-prefetch.cpp`（= patches/llama-upstream 同名文件）
`issue_expert_willneed` 中：

```cpp
const size_t off = static_cast<size_t>(eid) * per_expert;
const uintptr_t base = reinterpret_cast<uintptr_t>(e.addr);
const uintptr_t address = base + off;                       // <-- 未做页对齐
void * const addr = reinterpret_cast<void *>(address);
if (advice_(addr, per_expert, POSIX_MADV_WILLNEED) == 0) {  // <-- 恒返回 EINVAL
    ...
}
```

POSIX/glibc 要求 `posix_madvise(addr, len, ...)` 的 addr 页对齐，否则返回 EINVAL。
GGUF 张量 offs 通常 2048 mod 4096（本模型 `blk.N.ffn_*_exps.weight` offs 如 430299136），
专家切片首地址必然不对齐 → 每次 advice 失败 → `issued` 恒为 0。

reclaim 路径（slim-arc-expert-reclaim.cpp:105）用了 `interior_page_range`，
但 issue 路径没有用 —— 不对称。

## 3. 实证（WSL，本机复现）

/tmp/madvtest.c：mmap 16MB 临时文件后分别测对齐/未对齐/interior-aligned 三种调用。

```
page_size=16384 base=0x7fff93b00000
aligned: posix_madvise=0 errno=0
unaligned(+2048): posix_madvise=22 errno=0 (Success)   <- EINVAL
unaligned(+40): posix_madvise=22 errno=0 (Success)     <- EINVAL
interior-aligned: posix_madvise=0 errno=0
```

结论：未对齐地址 posix_madvise 返回 22(EINVAL)；按页取整（interior range）后成功。

## 4. 为什么单元测试没发现

tests/run-cpp-unit.sh 的 prefetch 测试注入 fake advice_fn（恒返回 0），
屏蔽了真实 posix_madvise 的对齐校验。`issued=0.9MB hit_rate=32.14%` 的 PASS
仅证明调度逻辑正确，不证明 advice 真实生效。

## 5. 修复方案

在 issue 路径对每个专家切片计算 `interior_page_range`（页对齐 + 长度按页截断），
对对齐后的 interior range 下发 WILLNEED。这是 finals 补丁引入的功能回归修复，
不属于核心机制变更：

- 不改变调度策略、预算、命中/浪费核算语义
- 核算字节改为 interior 实际下发字节（略小于原始切片，差值 ≤ 2 页）
- 用现有模块 `slim_arc::interior_page_range`，无新依赖
- 三线通用（x86 WSL 4K 页 / Pi5、RK3588 可能 16K 页，均用运行时 sysconf）

注意：本机实测 page_size=16384（WSL aarch64? 实为 WSL2 x86 返回 4K 的环境待复核；
测试输出 16384 表明该 WSL 内核页大小 16K，Pi5 亦可能 16K），
因此必须运行时取 sysconf(_SC_PAGESIZE)，不可硬编码 4096。
