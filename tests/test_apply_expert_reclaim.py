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


def run_apply(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(APPLY_SCRIPT), str(root)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def snapshot_tree(src: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(src)): path.read_bytes()
        for path in sorted(src.rglob("*"))
        if path.is_file()
    }


def run_apply_failure(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(APPLY_SCRIPT), str(root)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_expert_prefetch_uses_value_snapshots_and_remains_idempotent(tmp_path: Path) -> None:
    src = write_fixture(tmp_path / "llama")

    first_run = run_apply(src.parent)
    first = {path.name: path.read_bytes() for path in src.iterdir() if path.is_file()}
    second_run = run_apply(src.parent)
    second = {path.name: path.read_bytes() for path in src.iterdir() if path.is_file()}

    assert first == second
    assert first_run.stdout == "SLIM-ARC integration complete\n"
    assert second_run.stdout == first_run.stdout
    context = second["llama-context.cpp"].decode(encoding="utf-8")
    assert context.count("cached_experts_snapshot(layer)") == 1
    assert context.count("prefetch_experts(layer, experts.data(), static_cast<int>(experts.size()))") == 1
    assert context.count("expert_generation_tokens") >= 4
    assert context.count("cache_router_experts(layer, unique.data(), static_cast<int>(unique.size()), generation)") == 1
    assert "expert_generation_tokens[static_cast<size_t>(layer)] = 0;" in context
    assert "cancel_expert_prefetch" in context
    assert context.index("status == GGML_STATUS_SUCCESS") < context.index("cancel_expert_prefetch")
    assert "get_cached_experts" not in context
    assert "tensor->name == nullptr" not in context
    assert "auto slim_arc_runtime = slim_arc::acquire_runtime();" in context
    assert context.count('std::getenv("SLIM_ARC_SLOW_STORAGE")') == 1
    assert context.count('std::strcmp(slow_storage_raw, "1") == 0') == 1
    assert "if (!slow_storage && !batched && max_layer > min_layer)" in context
    assert context.index("if (slim_arc_runtime) {") < context.index("ggml_graph_n_nodes(gf)")
    assert "get_global_prefetch_scheduler" not in context
    assert "get_global_unified_scheduler" not in context

    model = second["llama-model.cpp"].decode(encoding="utf-8")
    impl = model[model.index("struct llama_model::impl"):model.index("};", model.index("struct llama_model::impl"))]
    assert impl.rstrip().endswith("std::unique_ptr<slim_arc::runtime_owner> slim_arc_runtime;")
    assert model.index("pimpl->mappings.emplace_back(std::move(mapping));") < model.index("std::make_unique<slim_arc::runtime_owner>")
    assert "runtime->activate();" in model
    assert '#include <cstring>' in model
    admission = "if (slim_arc::model_runtime_admitted(use_mmap_buffer, pimpl->mappings.size(), ml.size_data, slim_arc_enabled))"
    assert admission in model
    assert model.index(admission) < model.index("for (const auto & item : ml.weights_map)")
    assert model.index("for (const auto & item : ml.weights_map)") < model.index("std::make_unique<slim_arc::runtime_owner>")

    loader = second["llama-model-loader.cpp"].decode(encoding="utf-8")
    for forbidden in ("slim-arc-prefetch.h", "register_mmap_region", "set_global_prefetch_scheduler", "static slim_arc::"):
        assert forbidden not in loader

    cmake = second["CMakeLists.txt"].decode(encoding="utf-8")
    assert cmake.count("slim-arc-runtime.cpp") == 1
    assert cmake.count("slim-arc-page-range.cpp") == 1
    assert cmake.count("slim-arc-expert-reclaim.cpp") == 1
    assert cmake.count("slim-arc-expert-residency.cpp") == 1
    assert "slim-arc-runtime.h" in second
    assert "slim-arc-runtime.cpp" in second
    assert "slim-arc-page-range.h" in second
    assert "slim-arc-page-range.cpp" in second
    assert "slim-arc-expert-reclaim.h" in second
    assert "slim-arc-expert-reclaim.cpp" in second
    assert "slim-arc-expert-residency.h" in second
    assert "slim-arc-expert-residency.cpp" in second
    assert "slim-arc-on-demand.h" not in second
    assert "slim-arc-on-demand.cpp" not in second


def test_partial_runtime_member_state_fails_without_writing_any_fixture_file(tmp_path: Path) -> None:
    seed = write_fixture(tmp_path / "seed")
    run_apply(seed.parent)
    patched_model = (seed / "llama-model.cpp").read_text(encoding="utf-8")
    src = write_fixture(tmp_path / "llama")
    model_path = src / "llama-model.cpp"
    model_path.write_text(
        patched_model.replace("    std::vector<float> tensor_split_owned;", "    std::vector<float> renamed_tensor_split;", 1),
        encoding="utf-8",
    )
    before = snapshot_tree(src)

    result = run_apply_failure(src.parent)

    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert "final member" in result.stderr
    assert snapshot_tree(src) == before
    assert "slim-arc-runtime.cpp" not in before


def test_partial_runtime_setup_state_fails_without_writing_any_fixture_file(tmp_path: Path) -> None:
    seed = write_fixture(tmp_path / "seed")
    run_apply(seed.parent)
    patched_model = (seed / "llama-model.cpp").read_text(encoding="utf-8")
    src = write_fixture(tmp_path / "llama")
    model_path = src / "llama-model.cpp"
    model_path.write_text(
        patched_model.replace(
            "            pimpl->mappings.emplace_back(std::move(mapping));",
            "            pimpl->mappings.push_back(std::move(mapping));",
            1,
        ),
        encoding="utf-8",
    )
    before = snapshot_tree(src)

    result = run_apply_failure(src.parent)

    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert "mmap transfer" in result.stderr
    assert snapshot_tree(src) == before
    assert "slim-arc-runtime.cpp" not in before


def test_generated_member_with_pristine_transfer_is_rejected_as_hybrid(tmp_path: Path) -> None:
    seed = write_fixture(tmp_path / "seed")
    run_apply(seed.parent)
    generated = (seed / "llama-model.cpp").read_text(encoding="utf-8")
    runtime_member = "    std::unique_ptr<slim_arc::runtime_owner> slim_arc_runtime;"

    src = write_fixture(tmp_path / "llama")
    model_path = src / "llama-model.cpp"
    pristine = model_path.read_text(encoding="utf-8")
    model_path.write_text(
        pristine.replace(
            "    std::vector<float> tensor_split_owned;",
            "    std::vector<float> tensor_split_owned;\n\n" + runtime_member,
            1,
        ),
        encoding="utf-8",
    )
    assert runtime_member in generated
    before = snapshot_tree(src)

    result = run_apply_failure(src.parent)

    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert "hybrid" in result.stderr
    assert snapshot_tree(src) == before
    assert "slim-arc-runtime.cpp" not in before


def test_pristine_member_with_generated_setup_is_rejected_as_hybrid(tmp_path: Path) -> None:
    seed = write_fixture(tmp_path / "seed")
    run_apply(seed.parent)
    generated = (seed / "llama-model.cpp").read_text(encoding="utf-8")
    transfer = """    if (use_mmap_buffer) {
        for (auto & mapping : ml.mappings) {
            pimpl->mappings.emplace_back(std::move(mapping));
        }
    }"""
    setup_start = generated.index(transfer) + len(transfer)
    setup_end = generated.index("\n    return true;", setup_start)
    generated_setup = generated[setup_start:setup_end]

    src = write_fixture(tmp_path / "llama")
    model_path = src / "llama-model.cpp"
    pristine = model_path.read_text(encoding="utf-8")
    transfer_end = pristine.index("\n    return true;")
    model_path.write_text(pristine[:transfer_end] + generated_setup + pristine[transfer_end:], encoding="utf-8")
    before = snapshot_tree(src)

    result = run_apply_failure(src.parent)

    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert "hybrid" in result.stderr
    assert snapshot_tree(src) == before
    assert "slim-arc-runtime.cpp" not in before
