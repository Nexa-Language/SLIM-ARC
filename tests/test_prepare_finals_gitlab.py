"""Behavioral tests for atomic offline finals release-tree construction."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "release" / "prepare-finals-gitlab.py"
SPEC = importlib.util.spec_from_file_location("prepare_finals_gitlab", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare
SPEC.loader.exec_module(prepare)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {item.relative_to(root).as_posix(): item.read_bytes() for item in root.rglob("*") if item.is_file()}


def test_stage_builds_complete_new_tree_atomically_and_verify_is_read_only(tmp_path: Path) -> None:
    source, parent, output = tmp_path / "source", tmp_path / "parent", tmp_path / "parent" / "release"
    _write(source / "README.md", "finals\n")
    _write(source / "docs" / "design" / "architecture.md", "design\n")
    _write(source / "scripts" / "run.py", "print('ok')\n")
    _write(source / "docs" / "raw" / "raw-output.txt", "not selected\n")
    _write(parent / "neighbor.txt", "preserve\n")

    manifest = prepare.stage(source, output, max_file_bytes=1024)

    assert (output / "README.md").read_text(encoding="utf-8") == "finals\n"
    assert not (output / "docs" / "raw" / "raw-output.txt").exists()
    assert json.loads((output / prepare.DEFAULT_MANIFEST_NAME).read_text(encoding="utf-8")) == manifest
    before = _tree_bytes(output)
    assert prepare.verify(source, output, max_file_bytes=1024) == manifest
    assert _tree_bytes(output) == before
    assert (parent / "neighbor.txt").read_text(encoding="utf-8") == "preserve\n"


@pytest.mark.parametrize("failure", ["copy", "manifest", "verify"])
def test_any_private_build_failure_leaves_no_output_or_neighbor_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    source, parent, output = tmp_path / "source", tmp_path / "parent", tmp_path / "parent" / "release"
    _write(source / "README.md", "one\n")
    _write(source / "scripts" / "two.py", "two\n")
    _write(parent / "neighbor.txt", "unchanged\n")
    before = _tree_bytes(parent)
    if failure == "copy":
        original = prepare._copy_checked
        calls = 0

        def fail_second(*args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second copy failure")
            original(*args, **kwargs)

        monkeypatch.setattr(prepare, "_copy_checked", fail_second)
    elif failure == "manifest":
        monkeypatch.setattr(prepare, "_write_manifest", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("simulated manifest failure")))
    else:
        monkeypatch.setattr(prepare, "verify", lambda *args, **kwargs: (_ for _ in ()).throw(prepare.ReleaseError("simulated verification failure")))

    with pytest.raises((OSError, prepare.ReleaseError)):
        prepare.stage(source, output, max_file_bytes=1024)

    assert not output.exists()
    assert _tree_bytes(parent) == before


def test_output_must_not_exist_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    source, parent, output = tmp_path / "source", tmp_path / "parent", tmp_path / "parent" / "release"
    _write(source / "README.md", "safe\n")
    parent.mkdir()
    planned = prepare.stage(source, output, max_file_bytes=1024, dry_run=True)
    assert planned["files"] == [{"path": "README.md", "sha256": hashlib.sha256(b"safe\n").hexdigest(), "size": 5}]
    assert not output.exists()
    output.mkdir()
    with pytest.raises(prepare.ReleaseError, match="must not exist"):
        prepare.stage(source, output, max_file_bytes=1024)


@pytest.mark.parametrize("raw", ["../README.md", "docs//design.md", "docs/./design.md", "docs\\design.md", "/README.md"])
def test_rejects_noncanonical_paths(raw: str) -> None:
    with pytest.raises(prepare.ReleaseError, match="unsafe relative path"):
        prepare._safe_relative(raw)


@pytest.mark.parametrize("relative", [".env", "docs/design/model.gguf", "docs/design/build/object.o", "docs/design/node_modules/pkg/index.js"])
def test_rejects_denied_reachable_artifacts(tmp_path: Path, relative: str) -> None:
    source = tmp_path / "source"
    _write(source / "README.md", "safe\n")
    _write(source / relative, "denied\n")
    with pytest.raises(prepare.ReleaseError, match="denied"):
        prepare.build_source_manifest(source, 1024)


@pytest.mark.parametrize("payload, match", [(b"\x7fELFfake", "ELF"), (b"\xcf\xfa\xed\xfe", "Mach-O")])
def test_rejects_native_binary_magic(tmp_path: Path, payload: bytes, match: str) -> None:
    source, file = tmp_path / "source", tmp_path / "source" / "scripts" / "tool.cpp"
    _write(source / "README.md", "safe\n")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(payload)
    with pytest.raises(prepare.ReleaseError, match=match):
        prepare.build_source_manifest(source, 1024)


@pytest.mark.parametrize("content", ["token" + " = \"fake-token-value-12345\"\n", "-----BEGIN " + "PRIVATE KEY-----\n", "ghp_" + "abcdefghijklmnopqrstuvwxyz123456\n", "glpat-" + "abcdefghijklmnopqrstuvwxyz123456\n", "hf_" + "abcdefghijklmnopqrstuvwxyz123456\n", "AKIA" + "ABCDEFGHIJKLMNOP\n"])
def test_secret_content_is_rejected(tmp_path: Path, content: str) -> None:
    source = tmp_path / "source"
    _write(source / "README.md", "safe\n")
    _write(source / "config" / "release.toml", content)
    with pytest.raises(prepare.ReleaseError, match="secret-like content"):
        prepare.build_source_manifest(source, 1024)


def test_publisher_environment_lookup_is_not_a_secret_assignment(tmp_path: Path) -> None:
    source = tmp_path / "source"
    publisher = source / "scripts" / "release" / "publish-finals-gitlab.py"
    publisher.parent.mkdir(parents=True, exist_ok=True)
    publisher.write_bytes(
        (
            Path(__file__).parents[1]
            / "scripts"
            / "release"
            / "publish-finals-gitlab.py"
        ).read_bytes()
    )

    manifest = prepare.build_source_manifest(source, 1024 * 1024)

    assert [item["path"] for item in manifest["files"]] == [
        "scripts/release/publish-finals-gitlab.py"
    ]


@pytest.mark.parametrize(
    "content",
    [
        "token = get_" + "secret(\"fake-" + "token-value-12345\")\n",
        "token = (\n  \"fake-" + "token-value-12345\"\n)\n",
        "# token = \"fake-" + "token-value-12345\"\n",
    ],
)
def test_python_secret_literal_forms_are_rejected(
    tmp_path: Path, content: str
) -> None:
    source = tmp_path / "source"
    _write(source / "scripts" / "release.py", content)

    with pytest.raises(prepare.ReleaseError, match="secret-like content"):
        prepare.build_source_manifest(source, 1024)


@pytest.mark.parametrize(
    "content",
    [
        "token = os.getenv(\"TOKEN_ENV\", \"fake-" + "token-value-12345\")\n",
        "token = os.environ.get(\"TOKEN_ENV\", \"fake-" + "token-value-12345\")\n",
    ],
)
def test_environment_lookup_with_secret_fallback_is_rejected(
    tmp_path: Path, content: str
) -> None:
    source = tmp_path / "source"
    _write(source / "scripts" / "release.py", "import os\n" + content)

    with pytest.raises(prepare.ReleaseError, match="secret-like content"):
        prepare.build_source_manifest(source, 1024)


def test_pptx_zip_bomb_and_embedded_payload_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source / "README.md", "safe\n")
    pptx = source / "reports" / "SLIM-ARC展示PPT.pptx"
    pptx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pptx, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/embeddings/object.bin", b"unsafe")
    with pytest.raises(prepare.ReleaseError, match="executable, macro, or OLE"):
        prepare.build_source_manifest(source, 1024)
    with zipfile.ZipFile(pptx, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", b"x" * (prepare.MAX_PPTX_COMPRESSION_RATIO * 1000))
    with pytest.raises(prepare.ReleaseError, match="decompression policy"):
        prepare.build_source_manifest(source, 1024)


def test_valid_explicit_pptx_and_pdf_are_selected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source / "README.md", "safe\n")
    pptx = source / "reports" / "SLIM-ARC展示PPT.pptx"
    pptx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pptx, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/slides/slide1.xml", "<slide/>")
    paper = source / "docs" / "moe_cpu_memory_limited_survey.pdf"
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_bytes(b"%PDF-1.4\nfinals\n")
    assert [item["path"] for item in prepare.build_source_manifest(source, 1024)["files"]] == ["README.md", "docs/moe_cpu_memory_limited_survey.pdf", "reports/SLIM-ARC展示PPT.pptx"]
