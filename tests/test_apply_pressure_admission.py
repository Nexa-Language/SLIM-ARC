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
    (src / "CMakeLists.txt").write_text(
        "set(LLAMA_SOURCES llama-vocab.cpp)\n", encoding="utf-8"
    )
    return src


def snapshot_tree(src: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(src)): path.read_bytes()
        for path in sorted(src.rglob("*"))
        if path.is_file()
    }


def run_apply(root: Path) -> None:
    subprocess.run(
        [sys.executable, str(APPLY_SCRIPT), str(root)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_pressure_modules_are_copied_and_cmake_is_idempotent(tmp_path: Path) -> None:
    src = write_fixture(tmp_path / "llama")

    run_apply(src.parent)
    first = snapshot_tree(src)
    run_apply(src.parent)
    second = snapshot_tree(src)

    assert first == second
    for filename in (
        "slim-arc-cgroup-memory.h",
        "slim-arc-cgroup-memory.cpp",
        "slim-arc-pressure-budget.h",
        "slim-arc-pressure-budget.cpp",
    ):
        assert filename in first
    cmake = first["CMakeLists.txt"].decode()
    assert cmake.count("slim-arc-cgroup-memory.cpp") == 1
    assert cmake.count("slim-arc-pressure-budget.cpp") == 1
