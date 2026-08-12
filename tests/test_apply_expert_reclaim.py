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
    first = (src / "llama-context.cpp").read_bytes()
    run_apply(src.parent)
    second = (src / "llama-context.cpp").read_bytes()

    assert first == second
    context = second.decode(encoding="utf-8")
    assert context.count("cached_experts_snapshot(l)") == 2
    assert context.count("prefetch_experts(l, experts.data(), static_cast<int>(experts.size()))") == 2
    assert context.count("expert_generation_tokens") >= 4
    assert context.count("cache_router_experts(layer, ue.data(), static_cast<int>(ue.size()), expert_generation)") == 1
    assert "expert_generation_tokens[static_cast<size_t>(layer)] = 0;" in context
    assert "cancel_expert_prefetch" in context
    assert context.index("if (status == GGML_STATUS_SUCCESS)") < context.index("cancel_expert_prefetch")
    assert "get_cached_experts" not in context
