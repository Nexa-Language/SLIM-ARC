from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
APPLY_SCRIPT = REPO_ROOT / "scripts" / "apply-slim-arc.py"


def write_fixture(root: Path) -> Path:
    src = root / "src"
    src.mkdir(parents=True)
    (src / "llama-model-loader.cpp").write_text(
        '#include "llama-model-loader.h"\n#include <regex>\n'
        "void init_mappings() {\n"
        "            mmaps_used.emplace_back(mapping->size(), 0);\n"
        "    for (const auto & it : weights_map) {\n"
        "        size_data += ggml_nbytes(it.second.tensor);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "llama-model.cpp").write_text(
        '#include "llama-model.h"\n#include "llama-model-loader.h"\n'
        "struct llama_model::impl {\n"
        "    llama_mmaps mappings;\n"
        "    std::vector<float> tensor_split_owned;\n"
        "};\n"
        "bool llama_model_base::load_tensors(llama_model_loader & ml) {\n"
        "    const bool use_mmap_buffer = true;\n"
        "    if (use_mmap_buffer) {\n"
        "        for (auto & mapping : ml.mappings) {\n"
        "            pimpl->mappings.emplace_back(std::move(mapping));\n"
        "        }\n"
        "    }\n"
        "    return true;\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "llama-context.cpp").write_text(
        '#include "llama-ext.h"\n#include <limits>\n'
        "int graph_compute() {\n"
        "    auto status = ggml_backend_sched_graph_compute_async(sched.get(), gf);\n"
        "    return status;\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "llama-kv-cache.cpp").write_text(
        "#include <stdexcept>\n"
        "void clear(bool data) {\n"
        "    if (data) {\n"
        "        for (auto & [_, buf] : ctxs_bufs) {\n"
        "            ggml_backend_buffer_clear(buf.get(), 0);\n"
        "        }\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "CMakeLists.txt").write_text("set(LLAMA_SOURCES llama-vocab.cpp)\n", encoding="utf-8")
    return src


def run_apply(root: Path) -> None:
    subprocess.run(
        [sys.executable, str(APPLY_SCRIPT), str(root)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_expert_prefetch_uses_value_snapshots_and_remains_idempotent(tmp_path: Path) -> None:
    src = write_fixture(tmp_path / "llama")

    run_apply(src.parent)
    first = {path.name: path.read_bytes() for path in src.iterdir() if path.is_file()}
    run_apply(src.parent)
    second = {path.name: path.read_bytes() for path in src.iterdir() if path.is_file()}

    assert first == second
    context = second["llama-context.cpp"].decode(encoding="utf-8")
    assert context.count("cached_experts_snapshot(layer)") == 1
    assert context.count("prefetch_experts(layer, experts.data(), static_cast<int>(experts.size()))") == 1
    assert context.count("expert_generation_tokens") >= 4
    assert context.count("cache_router_experts(layer, unique.data(), static_cast<int>(unique.size()), generation)") == 1
    assert "expert_generation_tokens[static_cast<size_t>(layer)] = 0;" in context
    assert "cancel_expert_prefetch" in context
    assert context.index("status == GGML_STATUS_SUCCESS") < context.index("cancel_expert_prefetch")
    assert "get_cached_experts" not in context
    assert "auto slim_arc_runtime = slim_arc::acquire_runtime();" in context
    assert context.index("if (slim_arc_runtime) {") < context.index("ggml_graph_n_nodes(gf)")
    assert "get_global_prefetch_scheduler" not in context
    assert "get_global_unified_scheduler" not in context

    model = second["llama-model.cpp"].decode(encoding="utf-8")
    impl = model[model.index("struct llama_model::impl"):model.index("};", model.index("struct llama_model::impl"))]
    assert impl.rstrip().endswith("std::unique_ptr<slim_arc::runtime_owner> slim_arc_runtime;")
    assert model.index("pimpl->mappings.emplace_back(std::move(mapping));") < model.index("std::make_unique<slim_arc::runtime_owner>")
    assert "runtime->activate();" in model

    loader = second["llama-model-loader.cpp"].decode(encoding="utf-8")
    for forbidden in ("slim-arc-prefetch.h", "register_mmap_region", "set_global_prefetch_scheduler", "static slim_arc::"):
        assert forbidden not in loader

    cmake = second["CMakeLists.txt"].decode(encoding="utf-8")
    assert cmake.count("slim-arc-runtime.cpp") == 1
    assert "slim-arc-runtime.h" in second
    assert "slim-arc-runtime.cpp" in second
