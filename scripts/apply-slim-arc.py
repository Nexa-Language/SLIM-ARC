#!/usr/bin/env python3
"""Idempotently install SLIM-ARC sources into a pinned llama.cpp checkout."""

import os
import re
import shutil
import sys


SLIM_ARC_FILES = (
    "slim-arc-prefetch.h", "slim-arc-prefetch.cpp",
    "slim-arc-page-range.h", "slim-arc-page-range.cpp",
    "slim-arc-expert-reclaim.h", "slim-arc-expert-reclaim.cpp",
    "slim-arc-expert-residency.h", "slim-arc-expert-residency.cpp",
    "slim-arc-runtime.h", "slim-arc-runtime.cpp",
    "slim-arc-unified-scheduler.h", "slim-arc-unified-scheduler.cpp",
    "slim-arc-kv-eviction.h", "slim-arc-kv-eviction.cpp",
    "slim-arc-cgroup-memory.h", "slim-arc-cgroup-memory.cpp",
    "slim-arc-pressure-budget.h", "slim-arc-pressure-budget.cpp",
)


def replace_required(content: str, old: str, new: str, description: str) -> str:
    if old not in content:
        raise RuntimeError(f"required {description} anchor not found")
    return content.replace(old, new, 1)


def patch_model_loader(filepath: str) -> None:
    """Remove legacy loader-owned address and scheduler blocks only."""
    with open(filepath, encoding="utf-8") as source:
        content = source.read()
    original = content
    content = content.replace('#include "slim-arc-prefetch.h"\n', "")
    content = content.replace('#include "slim-arc-unified-scheduler.h"\n\n', "")
    content = content.replace('#include <sys/mman.h>  // SLIM-ARC: posix_madvise\n', "")
    content = re.sub(
        r'\n\s*// SLIM-ARC: demand-paging advice for large models \(>6GB\).*?\n\s*\}\n\s*\}',
        "", content, count=1, flags=re.DOTALL,
    )
    content = re.sub(
        r'\n\s*// SLIM-ARC: initialize prefetch scheduler and unified I/O scheduler\..*?(?=\n\})',
        "", content, count=1, flags=re.DOTALL,
    )
    if content != original:
        with open(filepath, "w", encoding="utf-8") as destination:
            destination.write(content)


def transform_model(content: str) -> str:
    """Validate the complete pinned state, then return the installed source."""
    final_member = "    std::vector<float> tensor_split_owned;"
    runtime_member = "    std::unique_ptr<slim_arc::runtime_owner> slim_arc_runtime;"
    unpatched_members = final_member + "\n};"
    patched_members = final_member + "\n\n" + runtime_member + "\n};"
    if runtime_member in content:
        member_state = "generated" if content.count(runtime_member) == 1 and patched_members in content else "corrupt"
    else:
        member_state = "pristine" if unpatched_members in content else "corrupt"

    transfer = """    if (use_mmap_buffer) {
        for (auto & mapping : ml.mappings) {
            pimpl->mappings.emplace_back(std::move(mapping));
        }
    }"""
    marker = "// SLIM-ARC: model-owned runtime begins after mmap ownership transfer."
    setup = r'''

    // SLIM-ARC: model-owned runtime begins after mmap ownership transfer.
    const char * disabled = std::getenv("SLIM_ARC_DISABLE");
    const char * no_prefetch = std::getenv("SLIM_ARC_NO_PREFETCH");
    const bool slim_arc_enabled = (disabled == nullptr || std::strcmp(disabled, "1") != 0) &&
                                  (no_prefetch == nullptr || std::strcmp(no_prefetch, "1") != 0);
    if (slim_arc::model_runtime_admitted(use_mmap_buffer, pimpl->mappings.size(), ml.size_data, slim_arc_enabled)) {
        uint64_t slim_arc_weight_bytes = 0;
        bool slim_arc_weights_valid = true;
        for (const auto & item : ml.weights_map) {
            if (item.second.tensor == nullptr) {
                slim_arc_weights_valid = false;
                break;
            }
            const size_t bytes = ggml_nbytes(item.second.tensor);
            if (bytes > std::numeric_limits<uint64_t>::max() - slim_arc_weight_bytes) {
                slim_arc_weights_valid = false;
                break;
            }
            slim_arc_weight_bytes += bytes;
        }
        if (slim_arc_weights_valid && slim_arc_weight_bytes > (6ULL << 30)) {
            auto runtime = std::make_unique<slim_arc::runtime_owner>(1ULL << 30);
            for (const auto & mapping : pimpl->mappings) {
                if (mapping == nullptr || !runtime->register_mapping(mapping->addr(), mapping->size())) {
                    slim_arc_weights_valid = false;
                    break;
                }
            }
            for (const auto & item : ml.weights_map) {
                const auto & weight = item.second;
                if (!slim_arc_weights_valid || weight.idx >= pimpl->mappings.size() || weight.tensor == nullptr) {
                    slim_arc_weights_valid = false;
                    break;
                }
                const auto & mapping = pimpl->mappings[weight.idx];
                const size_t mapping_size = mapping->size();
                const size_t tensor_size = ggml_nbytes(weight.tensor);
                const uintptr_t base = reinterpret_cast<uintptr_t>(mapping->addr());
                if (base == 0 || weight.offs > mapping_size || tensor_size > mapping_size - weight.offs ||
                    weight.offs > std::numeric_limits<uintptr_t>::max() - base) {
                    slim_arc_weights_valid = false;
                    break;
                }
                const uintptr_t start = base + weight.offs;
                if (tensor_size > std::numeric_limits<uintptr_t>::max() - start) {
                    slim_arc_weights_valid = false;
                    break;
                }
                void * const tensor_addr = reinterpret_cast<void *>(start);
                const int layer = slim_arc::tensor_layer_from_name(item.first.c_str());
                runtime->prefetch().register_tensor(item.first.c_str(), tensor_addr, tensor_size, layer);
                if (item.first.find("_exps") != std::string::npos && ggml_n_dims(weight.tensor) == 3 &&
                    weight.tensor->ne[2] > 1 && weight.tensor->ne[2] <= std::numeric_limits<int>::max()) {
                    runtime->prefetch().register_expert_tensor(
                        item.first.c_str(), tensor_addr, tensor_size, layer, static_cast<int>(weight.tensor->ne[2]));
                }
            }
            if (slim_arc_weights_valid) {
                runtime->activate();
                pimpl->slim_arc_runtime = std::move(runtime);
            }
        }
    }'''
    if marker in content:
        setup_state = "generated" if content.count(marker) == 1 and transfer + setup in content else "corrupt"
    else:
        setup_state = "pristine" if transfer in content else "corrupt"

    if member_state == "corrupt":
        raise RuntimeError("required llama_model::impl final member anchor is incomplete")
    if setup_state == "corrupt":
        raise RuntimeError("required mmap transfer runtime block is incomplete")
    if member_state != setup_state:
        raise RuntimeError("hybrid runtime patch state: member and setup must be paired")

    if '#include "slim-arc-runtime.h"' not in content:
        content = replace_required(
            content, '#include "llama-model-loader.h"',
            '#include "llama-model-loader.h"\n#include "slim-arc-runtime.h"', "llama-model include")
    for header in ("<limits>", "<cstdlib>", "<cstring>"):
        if f"#include {header}" not in content:
            content = replace_required(content, '#include "slim-arc-runtime.h"',
                                       f'#include "slim-arc-runtime.h"\n#include {header}', f"{header} include")

    if runtime_member not in content:
        content = replace_required(content, final_member, final_member + "\n\n" + runtime_member,
                                   "llama_model::impl final member")
    if marker not in content:
        content = replace_required(content, transfer, transfer + setup, "mmap transfer")
    return content


def patch_model(filepath: str) -> None:
    """Install the final model-owned runtime after mmap ownership transfer."""
    with open(filepath, encoding="utf-8") as source:
        content = source.read()
    content = transform_model(content)
    with open(filepath, "w", encoding="utf-8") as destination:
        destination.write(content)


def patch_context(filepath: str) -> None:
    """Acquire one lease spanning graph preparation, compute, and settlement."""
    with open(filepath, encoding="utf-8") as source:
        content = source.read()
    if '#include "slim-arc-runtime.h"' not in content:
        content = replace_required(content, '#include "llama-ext.h"',
                                   '#include "llama-ext.h"\n#include "slim-arc-runtime.h"', "context include")
    for header in ("<vector>", "<cstdint>", "<climits>", "<algorithm>", "<cstdlib>", "<cstring>", "<utility>"):
        if f"#include {header}" not in content:
            content = replace_required(content, "#include <limits>",
                                       f"#include <limits>\n#include {header}", f"context {header} include")

    thread_marker = "// SLIM-ARC: phase-specific CPU thread override."
    thread_anchor = "    int n_threads        = batched ? cparams.n_threads_batch : cparams.n_threads;"
    thread_override = r'''
    // SLIM-ARC: phase-specific CPU thread override.
    const auto slim_arc_phase_threads = [](const char * raw, int fallback) {
        if (raw == nullptr || *raw == '\0') return fallback;
        char * end = nullptr;
        const long parsed = std::strtol(raw, &end, 10);
        return end != raw && *end == '\0' && parsed > 0 && parsed <= 256
            ? static_cast<int>(parsed) : fallback;
    };
    n_threads = slim_arc_phase_threads(
        std::getenv(batched ? "SLIM_ARC_PREFILL_THREADS" : "SLIM_ARC_DECODE_THREADS"),
        n_threads);
'''
    if thread_marker not in content:
        content = replace_required(content, thread_anchor, thread_anchor + thread_override,
                                   "phase thread override")

    compute = "    auto status = ggml_backend_sched_graph_compute_async(sched.get(), gf);"
    precompute = r'''    auto slim_arc_runtime = slim_arc::acquire_runtime();
    std::vector<uint64_t> expert_generation_tokens;
    if (slim_arc_runtime) {
        int min_layer = INT_MAX;
        int max_layer = -1;
        const int n_nodes = ggml_graph_n_nodes(gf);
        for (int i = 0; i < n_nodes; ++i) {
            struct ggml_tensor * tensor = ggml_graph_node(gf, i);
            if (tensor == nullptr) continue;
            int layer = slim_arc::tensor_layer_from_name(tensor->name);
            if (layer < 0) {
                const char * dash = strrchr(tensor->name, '-');
                if (dash != nullptr && dash[1] >= '0' && dash[1] <= '9') layer = atoi(dash + 1);
            }
            if (layer >= 0) {
                min_layer = std::min(min_layer, layer);
                max_layer = std::max(max_layer, layer);
            }
        }
        if (min_layer != INT_MAX && max_layer >= 0) {
            expert_generation_tokens.resize(static_cast<size_t>(max_layer) + 1, 0);
            auto & scheduler = slim_arc_runtime.prefetch();
            auto & unified = slim_arc_runtime.unified();
            const char * slow_storage_raw = std::getenv("SLIM_ARC_SLOW_STORAGE");
            const bool slow_storage = slow_storage_raw != nullptr && std::strcmp(slow_storage_raw, "1") == 0;
            scheduler.set_phase(batched ? slim_arc::compute_phase::PREFILL : slim_arc::compute_phase::DECODE);
            unified.set_phase(batched ? slim_arc::runtime_phase::PREFILL_SHORT : slim_arc::runtime_phase::MOE_DECODE);
            unified.tick(min_layer, 3);
            if (!slow_storage && !batched && max_layer > min_layer) {
                for (int layer = min_layer + scheduler.effective_window() + 1; layer <= max_layer; ++layer) scheduler.notify_layer_compute(layer);
            }
            for (int layer = min_layer; layer <= max_layer; ++layer) {
                const std::vector<int> experts = scheduler.cached_experts_snapshot(layer);
                if (!experts.empty()) expert_generation_tokens[static_cast<size_t>(layer)] =
                    scheduler.prefetch_experts(layer, experts.data(), static_cast<int>(experts.size()));
            }
        }
    }
    const char * slim_arc_inline_router_raw = std::getenv("SLIM_ARC_INLINE_ROUTER");
    const bool slim_arc_inline_router = slim_arc_runtime && !batched && cparams.cb_eval == nullptr &&
        slim_arc_inline_router_raw != nullptr && std::strcmp(slim_arc_inline_router_raw, "1") == 0;
    struct slim_arc_inline_router_state {
        slim_arc::runtime_lease * runtime;
        std::vector<uint64_t> * generations;
        int pending_layer{-1};
        std::vector<int> pending_experts;

        void settle_pending() {
            if (runtime == nullptr || !*runtime || pending_layer < 0 || pending_experts.empty()) return;
            uint64_t generation = static_cast<size_t>(pending_layer) < generations->size() ?
                (*generations)[static_cast<size_t>(pending_layer)] : 0;
            runtime->prefetch().cache_router_experts(
                pending_layer, pending_experts.data(), static_cast<int>(pending_experts.size()), generation);
            if (generation != 0) (*generations)[static_cast<size_t>(pending_layer)] = 0;
            pending_layer = -1;
            pending_experts.clear();
        }
    } slim_arc_inline_state{&slim_arc_runtime, &expert_generation_tokens, -1, {}};
    if (slim_arc_inline_router) {
        ggml_backend_sched_set_eval_callback(
            sched.get(),
            [](struct ggml_tensor * tensor, bool ask, void * user_data) -> bool {
                if (tensor == nullptr || std::strstr(tensor->name, "ffn_moe_topk") == nullptr) return false;
                if (ask) return true;
                auto * state = static_cast<slim_arc_inline_router_state *>(user_data);
                state->settle_pending();
                if (tensor->data == nullptr || tensor->ne[0] <= 0) return true;
                int layer = slim_arc::tensor_layer_from_name(tensor->name);
                if (layer < 0) {
                    const char * dash = std::strrchr(tensor->name, '-');
                    if (dash != nullptr && dash[1] >= '0' && dash[1] <= '9') layer = std::atoi(dash + 1);
                }
                if (layer < 0) return true;
                const int32_t * selected = static_cast<const int32_t *>(tensor->data);
                std::vector<int> unique;
                for (int expert = 0; expert < tensor->ne[0] && expert < 64; ++expert) {
                    if (selected[expert] >= 0 &&
                        std::find(unique.begin(), unique.end(), selected[expert]) == unique.end()) {
                        unique.push_back(selected[expert]);
                    }
                }
                if (!unique.empty()) {
                    state->pending_layer = layer;
                    state->pending_experts = std::move(unique);
                }
                return true;
            },
            &slim_arc_inline_state);
    }
'''
    if "auto slim_arc_runtime = slim_arc::acquire_runtime();" not in content:
        content = replace_required(content, compute, precompute + compute, "graph compute")

    final_marker = "// SLIM-ARC: lease-guarded router finalization."
    finalization = r'''
    // SLIM-ARC: lease-guarded router finalization.
    if (slim_arc_inline_router) {
        ggml_backend_sched_set_eval_callback(sched.get(), cparams.cb_eval, cparams.cb_eval_user_data);
        if (status == GGML_STATUS_SUCCESS) slim_arc_inline_state.settle_pending();
    }
    if (slim_arc_runtime && status == GGML_STATUS_SUCCESS && !slim_arc_inline_router) {
        auto & scheduler = slim_arc_runtime.prefetch();
        const int n_nodes = ggml_graph_n_nodes(gf);
        for (int i = 0; i < n_nodes; ++i) {
            struct ggml_tensor * tensor = ggml_graph_node(gf, i);
            if (tensor == nullptr || tensor->data == nullptr ||
                strstr(tensor->name, "ffn_moe_topk") == nullptr) continue;
            int layer = slim_arc::tensor_layer_from_name(tensor->name);
            if (layer < 0) {
                const char * dash = strrchr(tensor->name, '-');
                if (dash != nullptr && dash[1] >= '0' && dash[1] <= '9') layer = atoi(dash + 1);
            }
            if (layer < 0 || tensor->ne[0] <= 0) continue;
            const int32_t * selected = static_cast<const int32_t *>(tensor->data);
            std::vector<int> unique;
            for (int expert = 0; expert < tensor->ne[0] && expert < 64; ++expert) {
                if (selected[expert] >= 0 && std::find(unique.begin(), unique.end(), selected[expert]) == unique.end()) unique.push_back(selected[expert]);
            }
            if (unique.empty()) continue;
            const uint64_t generation = static_cast<size_t>(layer) < expert_generation_tokens.size() ?
                expert_generation_tokens[static_cast<size_t>(layer)] : 0;
            scheduler.cache_router_experts(layer, unique.data(), static_cast<int>(unique.size()), generation);
            if (generation != 0) expert_generation_tokens[static_cast<size_t>(layer)] = 0;
        }
    }
    if (slim_arc_runtime) {
        auto & scheduler = slim_arc_runtime.prefetch();
        for (size_t layer = 0; layer < expert_generation_tokens.size(); ++layer) {
            if (expert_generation_tokens[layer] != 0) scheduler.cancel_expert_prefetch(static_cast<int>(layer), expert_generation_tokens[layer]);
        }
    }
'''
    if final_marker not in content:
        content = replace_required(content, "    return status;\n}", finalization + "    return status;\n}", "graph return")
    with open(filepath, "w", encoding="utf-8") as destination:
        destination.write(content)


def patch_kv_cache(filepath: str) -> None:
    with open(filepath, encoding="utf-8") as source:
        content = source.read()
    if "<sys/mman.h>" not in content:
        content = replace_required(content, "#include <stdexcept>",
                                   "#include <stdexcept>\n#include <sys/mman.h>  // SLIM-ARC: page advice", "KV include")
    old = """    if (data) {
        for (auto & [_, buf] : ctxs_bufs) {
            ggml_backend_buffer_clear(buf.get(), 0);
        }
    }
}"""
    new = """    if (data) {
        for (auto & [_, buf] : ctxs_bufs) {
            ggml_backend_buffer_clear(buf.get(), 0);
            size_t size = ggml_backend_buffer_get_size(buf.get());
            void * base = ggml_backend_buffer_get_base(buf.get());
            if (base != nullptr && size > 0) (void) posix_madvise(base, size, POSIX_MADV_DONTNEED);
        }
    }
}"""
    if "POSIX_MADV_DONTNEED" not in content:
        content = replace_required(content, old, new, "KV clear")
    with open(filepath, "w", encoding="utf-8") as destination:
        destination.write(content)


def patch_cmakelists(filepath: str) -> None:
    with open(filepath, encoding="utf-8") as source:
        content = source.read()
    required = (
        "slim-arc-prefetch.cpp", "slim-arc-runtime.cpp", "slim-arc-kv-eviction.cpp",
        "slim-arc-unified-scheduler.cpp", "slim-arc-cgroup-memory.cpp", "slim-arc-pressure-budget.cpp",
        "slim-arc-page-range.cpp", "slim-arc-expert-reclaim.cpp",
        "slim-arc-expert-residency.cpp",
    )
    if all(name in content for name in required):
        return
    files = """llama-vocab.cpp
            slim-arc-prefetch.cpp
            slim-arc-runtime.cpp
            slim-arc-kv-eviction.cpp
            slim-arc-unified-scheduler.cpp
            slim-arc-cgroup-memory.cpp
            slim-arc-pressure-budget.cpp
            slim-arc-page-range.cpp
            slim-arc-expert-reclaim.cpp
            slim-arc-expert-residency.cpp"""
    if "slim-arc-prefetch.cpp" not in content:
        content = replace_required(content, "llama-vocab.cpp", files, "CMake llama-vocab.cpp")
    else:
        anchor = "slim-arc-unified-scheduler.cpp"
        for name in (
            "slim-arc-runtime.cpp", "slim-arc-cgroup-memory.cpp", "slim-arc-pressure-budget.cpp",
            "slim-arc-page-range.cpp", "slim-arc-expert-reclaim.cpp",
            "slim-arc-expert-residency.cpp",
        ):
            if name not in content:
                content = replace_required(content, anchor, f"{anchor}\n            {name}", "CMake source")
                anchor = name
    with open(filepath, "w", encoding="utf-8") as destination:
        destination.write(content)


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else "src/llama-upstream"
    src_dir = os.path.join(root, "src")
    patches_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patches", "llama-upstream")
    if not os.path.isdir(src_dir):
        raise RuntimeError(f"upstream source directory not found: {src_dir}")
    model_path = os.path.join(src_dir, "llama-model.cpp")
    with open(model_path, encoding="utf-8") as model_source:
        transform_model(model_source.read())
    for filename in SLIM_ARC_FILES:
        source = os.path.join(patches_dir, filename)
        if not os.path.isfile(source):
            raise RuntimeError(f"required standalone source not found: {source}")
        shutil.copy2(source, os.path.join(src_dir, filename))
    patch_model_loader(os.path.join(src_dir, "llama-model-loader.cpp"))
    patch_model(model_path)
    patch_context(os.path.join(src_dir, "llama-context.cpp"))
    patch_kv_cache(os.path.join(src_dir, "llama-kv-cache.cpp"))
    patch_cmakelists(os.path.join(src_dir, "CMakeLists.txt"))
    print("SLIM-ARC integration complete")


if __name__ == "__main__":
    main()
