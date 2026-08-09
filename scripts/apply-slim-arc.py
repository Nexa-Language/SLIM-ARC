#!/usr/bin/env python3
"""
SLIM-ARC Integration Script
Applies all SLIM-ARC modifications to upstream llama.cpp source files.

This script is idempotent (can be run multiple times safely).
It uses pattern matching (not line numbers) to adapt to upstream version changes.

Usage: python3 scripts/apply-slim-arc.py [src/llama-upstream]
"""
import os
import re
import sys
import shutil

def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "src/llama-upstream"
    src_dir = os.path.join(root, "src")
    # SLIM-ARC FIX 2026-08-08: 镜像同步路径修复——patches_dir 基于脚本自身位置解析，
    # 不再依赖 CWD。此前从 /home/orangepi 运行会导致 Step 1 复制失败（patches 找不到），
    # 违反 red-line 镜像规则（patches/ 与 src/ 必须同步）。
    patches_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "patches", "llama-upstream")

    if not os.path.isdir(src_dir):
        print(f"Error: {src_dir} not found. Clone upstream first:")
        print(f"  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git {root}")
        sys.exit(1)

    # Step 1: Copy slim-arc standalone files
    print("=== Step 1: Copy slim-arc standalone files ===")
    slim_arc_files = [
        "slim-arc-prefetch.h", "slim-arc-prefetch.cpp",
        "slim-arc-unified-scheduler.h", "slim-arc-unified-scheduler.cpp",
        "slim-arc-kv-eviction.h", "slim-arc-kv-eviction.cpp",
        "slim-arc-on-demand.h", "slim-arc-on-demand.cpp",
    ]
    for f in slim_arc_files:
        src = os.path.join(patches_dir, f)
        dst = os.path.join(src_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  copied {f}")
        else:
            print(f"  WARNING: {src} not found")

    # Step 2: Modify llama-model-loader.cpp
    print("\n=== Step 2: Patch llama-model-loader.cpp ===")
    patch_model_loader(os.path.join(src_dir, "llama-model-loader.cpp"))

    # Step 3: Modify llama-context.cpp
    print("\n=== Step 3: Patch llama-context.cpp ===")
    patch_context(os.path.join(src_dir, "llama-context.cpp"))

    # Step 4: Modify llama-kv-cache.cpp
    print("\n=== Step 4: Patch llama-kv-cache.cpp ===")
    patch_kv_cache(os.path.join(src_dir, "llama-kv-cache.cpp"))

    # Step 5: Modify CMakeLists.txt
    print("\n=== Step 5: Patch CMakeLists.txt ===")
    patch_cmakelists(os.path.join(src_dir, "CMakeLists.txt"))

    print("\n=== SLIM-ARC integration complete ===")
    print("Next steps:")
    print(f"  cd {root}/build && cmake -DGGML_CPU_REPACK=OFF .. && cmake --build . --target llama-bench -j$(nproc)")


def patch_model_loader(filepath):
    """Add MADV_RANDOM, prefetch_scheduler registration, unified scheduler."""
    with open(filepath, 'r') as f:
        content = f.read()

    # Add includes
    if 'slim-arc-prefetch.h' not in content:
        content = content.replace(
            '#include "llama-model-loader.h"',
            '#include "slim-arc-prefetch.h"\n#include "slim-arc-unified-scheduler.h"\n\n#include "llama-model-loader.h"',
            1)
        print("  added slim-arc includes")

    if '<sys/mman.h>' not in content:
        content = content.replace(
            '#include <regex>',
            '#include <regex>\n#include <sys/mman.h>  // SLIM-ARC: posix_madvise',
            1)
        print("  added <sys/mman.h>")

    # Add MADV_RANDOM in init_mappings (after mapping creation)
    madv_marker = "mmaps_used.emplace_back(mapping->size(), 0);"
    # SLIM-ARC FIX 2026-08-07: 加载时初始建议改为 MADV_SEQUENTIAL（保住 prefill 顺序预读，
    # 消除端侧 RK3588 负优化）。后续由 slim_arc::apply_dynamic_madv() 在 decode 阶段
    # 动态切换到 MADV_RANDOM（MoE 专家按需分页）。SLIM_ARC_DYNAMIC_MADV=0 可回退到旧行为。
    madv_block = """mmaps_used.emplace_back(mapping->size(), 0);

            // SLIM-ARC: demand-paging advice for large models (>6GB).
            // FIX 2026-08-07: 初始用 MADV_SEQUENTIAL（prefill 顺序预读），
            // decode 阶段由 apply_dynamic_madv() 切到 MADV_RANDOM（MoE 按需分页）。
            // SLIM_ARC_NO_MADV_RANDOM=1 to disable; SLIM_ARC_DYNAMIC_MADV=0 禁用动态切换。
            {
                bool slim_arc_disabled = getenv("SLIM_ARC_DISABLE") != nullptr;
                bool no_madv = getenv("SLIM_ARC_NO_MADV_RANDOM") != nullptr;
                size_t msz = mapping->size();
                if (!slim_arc_disabled && !no_madv && msz > (6ULL << 30) &&
                    mapping->addr() && msz > 0) {
                    // register_mmap_region 内部会按动态模式设置初始 SEQUENTIAL 建议
                    slim_arc::register_mmap_region(mapping->addr(), msz);
                }
            }"""
    # SLIM-ARC FIX 2026-08-07: 幂等处理——若已存在旧版静态 MADV_RANDOM 块，
    # 先用正则整体删除（避免新旧块重复并存），再插入新的动态模式块。
    old_madv_pattern = re.compile(
        r"\n?\s*// SLIM-ARC: MADV_RANDOM for large models \(>6GB\).*?"
        r"register_mmap_region\(mapping->addr\(\), msz\);\n\s*\}\n\s*\}",
        re.DOTALL,
    )
    if old_madv_pattern.search(content):
        content = old_madv_pattern.sub("\n", content, count=1)
        print("  removed old static MADV_RANDOM block")

    if 'register_mmap_region(mapping->addr(), msz)' not in content:
        content = content.replace(madv_marker, madv_block, 1)
        print("  added MADV advice block (dynamic mode)")

    # Add prefetch_scheduler + unified scheduler registration after weights_map loop
    # Find the size_data computation loop and insert after it
    prefetch_block = """    // SLIM-ARC: initialize prefetch scheduler and unified I/O scheduler.
    // Registers weight tensors for WILLNEED prefetch during graph_compute.
    // SLIM_ARC_DISABLE=1 disables (baseline mode).
    // SLIM_ARC_NO_PREFETCH=1 disables prefetch only (keep MADV_RANDOM).
    // Skip if model fits in cgroup (<60% of memory.max).
    size_t total_weight_size_slim = 0;
    for (const auto & it : weights_map) {
        total_weight_size_slim += ggml_nbytes(it.second.tensor);
    }
    size_t cgroup_mem_limit = 0;
    {
        FILE * f = fopen("/sys/fs/cgroup/memory.max", "r");
        if (!f) f = fopen("/sys/fs/cgroup/slim-arc-low/memory.max", "r");
        if (f) { if (fscanf(f, "%zu", &cgroup_mem_limit) != 1) {} fclose(f); }
    }
    bool model_fits = (cgroup_mem_limit > 0 &&
                       total_weight_size_slim < cgroup_mem_limit * 60 / 100);
    bool no_prefetch = getenv("SLIM_ARC_NO_PREFETCH") != nullptr;
    bool should_enable = (use_mmap && !mappings.empty() &&
                          getenv("SLIM_ARC_DISABLE") == nullptr &&
                          !model_fits && !no_prefetch);
    if (should_enable) {
        static slim_arc::prefetch_scheduler s_scheduler(2, 3);
        slim_arc::set_global_prefetch_scheduler(&s_scheduler);
        static slim_arc::unified_io_scheduler s_unified(1ULL << 30, &s_scheduler, nullptr);
        slim_arc::set_global_unified_scheduler(&s_unified);
        s_scheduler.set_memory_budget(total_weight_size_slim > (6ULL << 30) ? total_weight_size_slim : 0);
        for (const auto & it : weights_map) {
            const auto & w = it.second;
            if (w.idx >= mappings.size()) continue;
            void * base = mappings[w.idx]->addr();
            if (!base) continue;
            void * tensor_addr = (uint8_t *) base + w.offs;
            int layer = slim_arc::tensor_layer_from_name(it.first.c_str());
            s_scheduler.register_tensor(it.first.c_str(), tensor_addr,
                                         ggml_nbytes(w.tensor), layer);
            // Phase 2a: register MoE expert tensors (3D merged)
            const std::string & tname = it.first;
            if (tname.find("_exps") != std::string::npos && w.tensor &&
                ggml_n_dims(w.tensor) == 3) {
                int n_experts = (int) w.tensor->ne[2];
                if (n_experts > 1) {
                    s_scheduler.register_expert_tensor(tname.c_str(), tensor_addr,
                                                         ggml_nbytes(w.tensor), layer, n_experts);
                }
            }
        }
    }
"""

    # Insert before the closing brace of init_mappings
    # SLIM-ARC FIX 2026-08-05: prefetch_block 不再以 '}' 关闭函数 —— 原函数
    # init_mappings 自身的右大括号仍保留在插入点之后，若此处多写一个 '}' 会产生
    # "expected declaration before '}' token" 编译错误（重复大括号）。
    # Find "size_data += ggml_nbytes" loop end and insert after
    size_loop_end = "    for (const auto & it : weights_map) {\n        size_data += ggml_nbytes(it.second.tensor);\n    }"
    if 'set_global_prefetch_scheduler' not in content:
        content = content.replace(size_loop_end, size_loop_end + "\n" + prefetch_block, 1)
        print("  added prefetch_scheduler + unified scheduler registration")

    with open(filepath, 'w') as f:
        f.write(content)


def patch_context(filepath):
    """Add unified scheduler tick + router hook to graph_compute."""
    with open(filepath, 'r') as f:
        content = f.read()

    # Add includes
    if 'slim-arc-prefetch.h' not in content:
        content = content.replace(
            '#include "llama-ext.h"',
            '#include "llama-ext.h"\n#include "slim-arc-prefetch.h"\n#include "slim-arc-unified-scheduler.h"',
            1)
        print("  added slim-arc includes")
    if '<vector>' not in content:
        content = content.replace('#include <limits>', '#include <limits>\n#include <vector>', 1)
        print("  added <vector>")
    # SLIM-ARC FIX 2026-08-05: llama-context.cpp 使用 INT_MAX，需 <climits>（修复 INT_MAX 级联错误，
    # 否则 max_layer 声明被吞导致 'not declared in this scope'）。<limits> 不保证提供 INT_MAX。
    if '<climits>' not in content:
        content = content.replace('#include <limits>', '#include <limits>\n#include <climits>', 1)
        print("  added <climits>")

    # Insert graph_compute SLIM-ARC block before ggml_backend_sched_graph_compute_async
    slim_block = """
    // SLIM-ARC: Collect graph layer range + unified scheduler tick + expert prefetch
    // SLIM-ARC FIX 2026-08-08: 层范围扫描也支持 "-<N>" 后缀回退解析。
    // Qwen3-Next decode 图节点名（ffn_moe_topk-N / gate-N）无 blk. 前缀，
    // tensor_layer_from_name 失败会导致 min_layer=INT_MAX，层预取与专家预取被跳过。
    int min_layer = INT_MAX, max_layer = -1;
    {
        int n_nodes = ggml_graph_n_nodes(gf);
        for (int i = 0; i < n_nodes; ++i) {
            struct ggml_tensor * t = ggml_graph_node(gf, i);
            if (t && t->name) {
                int layer = slim_arc::tensor_layer_from_name(t->name);
                if (layer < 0) {
                    const char * dash = strrchr(t->name, '-');
                    if (dash && *(dash + 1) >= '0' && *(dash + 1) <= '9') {
                        layer = atoi(dash + 1);
                    }
                }
                if (layer >= 0) {
                    if (layer < min_layer) min_layer = layer;
                    if (layer > max_layer) max_layer = layer;
                }
            }
        }
    }
    if (auto * u = slim_arc::get_global_unified_scheduler()) {
        u->set_phase(batched ? slim_arc::runtime_phase::PREFILL_SHORT
                              : slim_arc::runtime_phase::MOE_DECODE);
        // SLIM-ARC FIX 2026-08-07: unified 分支也需触发 prefetch 的 set_phase，
        // 以驱动动态 MADV 阶段切换（PREFILL->SEQUENTIAL / DECODE->RANDOM）。
        if (auto * s = slim_arc::get_global_prefetch_scheduler()) {
            s->set_phase(batched ? slim_arc::compute_phase::PREFILL
                                  : slim_arc::compute_phase::DECODE);
        }
        if (min_layer != INT_MAX) {
            u->tick(min_layer, 3);
            if (auto * s = slim_arc::get_global_prefetch_scheduler()) {
                if (!batched && max_layer > min_layer) {
                    for (int l = min_layer + s->effective_window() + 1; l <= max_layer; ++l) {
                        s->notify_layer_compute(l);
                    }
                }
                // SLIM-ARC FIX 2026-08-08: 预测器改为时间预测（l 层用上一 token 同层路由，
                // 而非上一层的跨层路由）。实测精度 temporal=35% vs spatial=4.5%，
                // 空间预测 95% 为无效预取，在 I/O 受限场景反而抢占带宽。
                for (int l = min_layer; l <= max_layer; ++l) {
                    int nc = 0;
                    const int * ce = s->get_cached_experts(l, &nc);
                    if (ce && nc > 0) s->prefetch_experts(l, ce, nc);
                }
            }
        }
    } else if (auto * s = slim_arc::get_global_prefetch_scheduler()) {
        s->set_phase(batched ? slim_arc::compute_phase::PREFILL
                              : slim_arc::compute_phase::DECODE);
        if (min_layer != INT_MAX) {
            s->notify_layer_compute(min_layer);
            if (!batched && max_layer > min_layer) {
                for (int l = min_layer + s->effective_window() + 1; l <= max_layer; ++l) {
                    s->notify_layer_compute(l);
                }
            }
            // SLIM-ARC FIX 2026-08-08: 同 unified 分支——时间预测（l 层用上一 token 同层路由）
            for (int l = min_layer; l <= max_layer; ++l) {
                int nc = 0;
                const int * ce = s->get_cached_experts(l, &nc);
                if (ce && nc > 0) s->prefetch_experts(l, ce, nc);
            }
        }
    }

"""
    compute_marker = "    auto status = ggml_backend_sched_graph_compute_async(sched.get(), gf);"
    if 'get_global_unified_scheduler' not in content:
        content = content.replace(compute_marker, slim_block + compute_marker, 1)
        print("  added unified scheduler + prefetch block to graph_compute")

    # Add router hook after graph_compute (extract ffn_moe_topk)
    router_block = """
    // SLIM-ARC Phase 2a: Extract MoE router expert IDs after compute
    // SLIM-ARC FIX 2026-08-08: 修复层号解析——Qwen3-Next 的 ffn_moe_topk 节点名
    // 为 "ffn_moe_topk-<layer>"（无 blk. 前缀），tensor_layer_from_name 解析失败导致
    // 专家预取从未触发。此处直接从 "-<N>" 后缀提取层号。
    if (status == GGML_STATUS_SUCCESS) {
        if (auto * s = slim_arc::get_global_prefetch_scheduler()) {
            int n_nodes = ggml_graph_n_nodes(gf);
            for (int i = 0; i < n_nodes; ++i) {
                struct ggml_tensor * t = ggml_graph_node(gf, i);
                if (!t || !t->name) continue;
                if (strstr(t->name, "ffn_moe_topk") != nullptr && t->data != nullptr) {
                    int layer = slim_arc::tensor_layer_from_name(t->name);
                    if (layer < 0) {
                        // 回退：从 "ffn_moe_topk-<N>" 提取层号
                        const char * dash = strrchr(t->name, '-');
                        if (dash && *(dash + 1) >= '0' && *(dash + 1) <= '9') {
                            layer = atoi(dash + 1);
                        }
                    }
                    if (layer < 0) continue;
                    int n_expert_used = (int) t->ne[0];
                    if (n_expert_used <= 0) continue;
                    const int32_t * ed = (const int32_t *) t->data;
                    std::vector<int> ue;
                    for (int e = 0; e < n_expert_used && e < 64; ++e) {
                        int eid = (int) ed[e];
                        if (eid >= 0) {
                            bool found = false;
                            for (int x : ue) if (x == eid) { found = true; break; }
                            if (!found) ue.push_back(eid);
                        }
                    }
                    if (!ue.empty()) s->cache_router_experts(layer, ue.data(), (int) ue.size());
                    // SLIM-ARC FIX 2026-08-08: 移除 break——缓存所有层的 topk 专家，
                    // 使跨层/跨步预测可用（原实现只缓存第一层，专家预取几乎从不触发）。
                }
            }
        }
    }
"""
    # SLIM-ARC FIX 2026-08-08: 幂等性修复——用 cache_router_experts 作为插入标记
    # （ffn_moe_topk 可能出现在层扫描注释中导致误判已存在，跳过插入）。
    if 'cache_router_experts' not in content:
        content = content.replace(
            "    return status;\n}",
            router_block + "    return status;\n}",
            1)
        print("  added router hook (ffn_moe_topk extraction)")

    # SLIM-ARC Phase 4: StreamingLLM-style KV eviction after decode
    kv_evict_block = """
    // SLIM-ARC Phase 4: StreamingLLM-style KV eviction after decode.
    // Keeps first N tokens (attention sinks) + last W tokens (sliding window),
    // evicts tokens in between via llama_memory_seq_rm to cap KV memory.
    // Enabled via SLIM_ARC_KV_EVICT=1, configured by SLIM_ARC_KV_SINK/WINDOW.
    if (status == GGML_STATUS_SUCCESS && !batched) {
        static bool kv_evict_enabled = getenv("SLIM_ARC_KV_EVICT") != nullptr;
        if (kv_evict_enabled) {
            static int kv_sink  = []{ const char * e = getenv("SLIM_ARC_KV_SINK");  return e ? atoi(e) : 4; }();
            static int kv_window = []{ const char * e = getenv("SLIM_ARC_KV_WINDOW"); return e ? atoi(e) : 1024; }();
            static int last_evicted_pos = 0;
            static bool first_call = true;
            if (first_call) {
                fprintf(stderr, "SLIM-ARC KV eviction: ENABLED (sink=%d, window=%d)\\n", kv_sink, kv_window);
                first_call = false;
            }
            llama_pos pos_max = memory->seq_pos_max(0);
            int seq_len = (int) pos_max + 1;
            int threshold = kv_sink + kv_window;
            if (seq_len > threshold) {
                int p0 = (last_evicted_pos > kv_sink) ? last_evicted_pos : kv_sink;
                int p1 = seq_len - kv_window;
                if (p1 > p0) {
                    memory->seq_rm(0, p0, p1);
                    last_evicted_pos = p1;
                    fprintf(stderr, "SLIM-ARC KV eviction: evicted [%d,%d) (seq_len %d->%d)\\n",
                            p0, p1, seq_len, seq_len - (p1 - p0));
                }
            }
        }
    }
"""
    if 'SLIM_ARC_KV_EVICT' not in content:
        content = content.replace(
            "    return status;\n}",
            kv_evict_block + "    return status;\n}",
            1)
        print("  added KV eviction hook (StreamingLLM-style)")

    with open(filepath, 'w') as f:
        f.write(content)


def patch_kv_cache(filepath):
    """Add madvise(DONTNEED) on KV cache clear."""
    with open(filepath, 'r') as f:
        content = f.read()

    if '<sys/mman.h>' not in content:
        content = content.replace(
            '#include <stdexcept>',
            '#include <stdexcept>\n#include <sys/mman.h>  // SLIM-ARC: posix_madvise',
            1)
        print("  added <sys/mman.h>")

    # Find clear method and add madvise
    old_clear = """    if (data) {
        for (auto & [_, buf] : ctxs_bufs) {
            ggml_backend_buffer_clear(buf.get(), 0);
        }
    }
}"""
    new_clear = """    if (data) {
        for (auto & [_, buf] : ctxs_bufs) {
            ggml_backend_buffer_clear(buf.get(), 0);
            // SLIM-ARC Phase 2b: release KV pages via madvise(DONTNEED)
            size_t bsz = ggml_backend_buffer_get_size(buf.get());
            void * bbase = ggml_backend_buffer_get_base(buf.get());
            if (bbase && bsz > 0) {
                (void) posix_madvise(bbase, bsz, POSIX_MADV_DONTNEED);
            }
        }
    }
}"""
    if 'POSIX_MADV_DONTNEED' not in content:
        content = content.replace(old_clear, new_clear, 1)
        print("  added KV clear DONTNEED")

    with open(filepath, 'w') as f:
        f.write(content)


def patch_cmakelists(filepath):
    """Add slim-arc source files to CMakeLists.txt."""
    with open(filepath, 'r') as f:
        content = f.read()

    if 'slim-arc-prefetch.cpp' in content:
        print("  already patched")
        return

    # Find the llama-vocab.cpp line and add slim-arc files after it
    marker = "llama-vocab.cpp"
    slim_files = """llama-vocab.cpp
            slim-arc-prefetch.cpp
            # slim-arc-on-demand.cpp  # disabled in favor of mmap+MADV_RANDOM
            slim-arc-kv-eviction.cpp
            slim-arc-unified-scheduler.cpp"""
    content = content.replace(marker, slim_files, 1)
    print("  added slim-arc source files")

    with open(filepath, 'w') as f:
        f.write(content)


if __name__ == "__main__":
    main()
