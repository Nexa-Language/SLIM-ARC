from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "write_build_evidence.py"
SPEC = importlib.util.spec_from_file_location("write_build_evidence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    build = tmp_path / "build-manifest.env"
    build.write_text(
        "LLAMA_COMMIT=360e134\n"
        f"SLIM_ARC_GIT_COMMIT={'a' * 40}\n"
        f"SLIM_ARC_BUILD_CONTEXT_SHA256={'b' * 64}\n"
        f"PATCHED_SOURCE_SHA256={'c' * 64}\n"
        "PATCH_IDEMPOTENT=1\n",
        encoding="utf-8",
    )
    model = tmp_path / "model-manifest.json"
    model.write_text(
        json.dumps({"expected_sha256": "d" * 64, "actual_sha256": "d" * 64}),
        encoding="utf-8",
    )
    return result_dir, build, model


def test_writes_exact_schema_and_same_runtime_image_for_both_variants(tmp_path: Path) -> None:
    result_dir, build, model = _fixtures(tmp_path)
    output = tool.write_build_evidence(
        result_dir, build, model, "sha256:" + "e" * 64
    )
    assert output == result_dir / "build-evidence.json"
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "git_commit": "a" * 40,
        "build_context_sha256": "b" * 64,
        "patched_source_sha256": "c" * 64,
        "model_sha256": "d" * 64,
        "llama_commit": "360e134",
        "image_ids": {"baseline": "sha256:" + "e" * 64, "patched": "sha256:" + "e" * 64},
        "variant_linkage": {"baseline": "verified", "patched": "verified"},
    }


@pytest.mark.parametrize(
    "replacement",
    [
        "SLIM_ARC_GIT_COMMIT=" + "a" * 40 + "\nSLIM_ARC_GIT_COMMIT=" + "b" * 40,
        "SLIM_ARC_GIT_COMMIT=" + "A" * 40,
        "SLIM_ARC_BUILD_CONTEXT_SHA256=" + "b" * 63 + "x",
        "PATCHED_SOURCE_SHA256=",
        "LLAMA_COMMIT=other",
    ],
)
def test_rejects_duplicate_missing_or_malformed_build_fields(
    tmp_path: Path, replacement: str
) -> None:
    result_dir, build, model = _fixtures(tmp_path)
    lines = build.read_text(encoding="utf-8").splitlines()
    if replacement.startswith("SLIM_ARC_GIT_COMMIT=") and replacement.count("\n"):
        lines = [line for line in lines if not line.startswith("SLIM_ARC_GIT_COMMIT=")]
    else:
        field = replacement.split("=", 1)[0]
        lines = [line for line in lines if not line.startswith(f"{field}=")]
    build.write_text("\n".join(lines) + "\n" + replacement + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        tool.write_build_evidence(result_dir, build, model, "sha256:" + "e" * 64)


def test_rejects_model_hash_mismatch(tmp_path: Path) -> None:
    result_dir, build, model = _fixtures(tmp_path)
    model.write_text(json.dumps({"expected_sha256": "d" * 64, "actual_sha256": "e" * 64}), encoding="utf-8")
    with pytest.raises(ValueError, match="mismatched"):
        tool.write_build_evidence(result_dir, build, model, "sha256:" + "f" * 64)


def test_rejects_missing_required_build_field(tmp_path: Path) -> None:
    result_dir, build, model = _fixtures(tmp_path)
    build.write_text(
        "\n".join(
            line
            for line in build.read_text(encoding="utf-8").splitlines()
            if not line.startswith("PATCHED_SOURCE_SHA256=")
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing fields"):
        tool.write_build_evidence(result_dir, build, model, "sha256:" + "f" * 64)


def test_rejects_bad_image_id_and_output_parent(tmp_path: Path) -> None:
    result_dir, build, model = _fixtures(tmp_path)
    with pytest.raises(ValueError, match="image"):
        tool.write_build_evidence(result_dir, build, model, "sha256:" + "f" * 63)
    with pytest.raises(ValueError, match="directory"):
        tool.write_build_evidence(tmp_path / "missing", build, model, "sha256:" + "f" * 64)


def test_rejects_existing_output_symlink(tmp_path: Path) -> None:
    result_dir, build, model = _fixtures(tmp_path)
    (result_dir / "build-evidence.json").symlink_to(model)
    with pytest.raises(ValueError, match="regular file"):
        tool.write_build_evidence(result_dir, build, model, "sha256:" + "f" * 64)
