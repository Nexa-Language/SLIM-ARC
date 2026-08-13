"""Behavioral tests for the guarded official GitLab publisher."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "release" / "publish-finals-gitlab.py"
SPEC = importlib.util.spec_from_file_location("publish_finals_gitlab", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
publish = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publish
SPEC.loader.exec_module(publish)
SHA, NEW_SHA = "a" * 40, "b" * 40


def _completed(output: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], 0, stdout=output, stderr=b"")


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _tar_bytes(entries: list[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for member, payload in entries:
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
    return stream.getvalue()


def _regular(name: str, content: bytes) -> tuple[tarfile.TarInfo, bytes]:
    member = tarfile.TarInfo(name)
    member.size = len(content)
    return member, content


def test_real_host_python_extracts_valid_tar_without_tar_extractall(tmp_path: Path) -> None:
    destination = tmp_path / "frozen"
    destination.mkdir()
    directory = tarfile.TarInfo("docs/")
    directory.type = tarfile.DIRTYPE
    archive = _tar_bytes([(directory, None), _regular("README.md", b"finals\n"), _regular("docs/note.md", b"safe\n")])

    publish._extract_tar_bytes(archive, destination)

    assert (destination / "README.md").read_bytes() == b"finals\n"
    assert (destination / "docs" / "note.md").read_bytes() == b"safe\n"
    assert (destination / "README.md").stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize("name", ["../escape", "/absolute", "dir//repeat", "dir\\backslash", "./dot"])
def test_real_host_python_rejects_unsafe_tar_member_paths(tmp_path: Path, name: str) -> None:
    destination = tmp_path / "frozen"
    destination.mkdir()
    with pytest.raises(publish.PublishError, match="unsafe|noncanonical"):
        publish._extract_tar_bytes(_tar_bytes([_regular(name, b"no\n")]), destination)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_real_host_python_rejects_tar_link_members(tmp_path: Path, kind: bytes) -> None:
    destination = tmp_path / "frozen"
    destination.mkdir()
    member = tarfile.TarInfo("link")
    member.type = kind
    member.linkname = "README.md"
    with pytest.raises(publish.PublishError, match="unsupported member type"):
        publish._extract_tar_bytes(_tar_bytes([(member, None)]), destination)


def test_real_host_python_rejects_duplicate_and_case_colliding_tar_paths(tmp_path: Path) -> None:
    destination = tmp_path / "frozen"
    destination.mkdir()
    duplicate = _tar_bytes([_regular("README.md", b"a"), _regular("README.md", b"b")])
    with pytest.raises(publish.PublishError, match="duplicate"):
        publish._extract_tar_bytes(duplicate, destination)
    collision = _tar_bytes([_regular("README.md", b"a"), _regular("readme.md", b"b")])
    with pytest.raises(publish.PublishError, match="case-colliding"):
        publish._extract_tar_bytes(collision, destination)


def test_real_host_python_rejects_oversize_and_truncated_tar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "frozen"
    destination.mkdir()
    monkeypatch.setattr(publish, "MAX_ARCHIVE_MEMBER_BYTES", 3)
    with pytest.raises(publish.PublishError, match="size policy"):
        publish._extract_tar_bytes(_tar_bytes([_regular("README.md", b"four")]), destination)
    monkeypatch.setattr(publish, "MAX_ARCHIVE_MEMBER_BYTES", 1024)
    complete = _tar_bytes([_regular("README.md", b"a" * 512)])
    with pytest.raises(publish.PublishError, match="extraction failed|truncated"):
        publish._extract_tar_bytes(complete[:800], destination)


def _release_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    source, release, clone = tmp_path / "source", tmp_path / "release", tmp_path / "clone"
    (source / "docs" / "design").mkdir(parents=True)
    (source / "README.md").write_text("finals\n", encoding="utf-8")
    (source / ".gitignore").write_text("docs/design/ignored.md\n", encoding="utf-8")
    (source / "docs" / "design" / "ignored.md").write_text("force me\n", encoding="utf-8")
    publish.PREPARE.stage(source, release, max_file_bytes=1024)
    clone.mkdir()
    _git(["init"], clone)
    publish._copy_release_tree(release, clone)
    return release, clone


def test_index_gate_force_stages_ignored_manifest_path_and_requires_exact_blob_set(tmp_path: Path) -> None:
    release, clone = _release_and_clone(tmp_path)
    publish._stage_exact_release(clone, release)
    publish._index_projection_gate(clone, release)
    tracked = subprocess.run(["git", "ls-files"], cwd=clone, check=True, capture_output=True, text=True).stdout.splitlines()
    assert "docs/design/ignored.md" in tracked


@pytest.mark.parametrize("mutation", ["missing", "extra", "blob"])
def test_index_gate_rejects_missing_extra_or_mismatched_blob_before_commit(tmp_path: Path, mutation: str) -> None:
    release, clone = _release_and_clone(tmp_path)
    publish._stage_exact_release(clone, release)
    if mutation == "missing":
        _git(["rm", "--cached", "README.md"], clone)
    elif mutation == "extra":
        (clone / "extra.md").write_text("extra\n", encoding="utf-8")
        _git(["add", "-f", "--", "extra.md"], clone)
    else:
        (clone / "README.md").write_text("tampered\n", encoding="utf-8")
        _git(["add", "-f", "--", "README.md"], clone)
    with pytest.raises(publish.PublishError, match="Git index"):
        publish._index_projection_gate(clone, release)


def test_default_dry_run_does_not_clone_or_read_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, receipt = tmp_path / "source", tmp_path / "receipt.json"
    source.mkdir()
    calls: list[list[str]] = []
    monkeypatch.setattr(publish, "_clean_source", lambda _: (source, SHA))
    monkeypatch.setattr(publish, "_run", lambda args, **kwargs: calls.append(args) or _completed())
    monkeypatch.setattr(publish, "_extract_archive", lambda _, destination: (destination / "README.md").write_text("frozen\n", encoding="utf-8"))
    monkeypatch.delenv(publish.TOKEN_ENV, raising=False)
    result = publish.publish(source, receipt)
    assert result["mode"] == "dry-run" and result["source_sha"] == SHA and len(result["manifest_sha256"]) == 64
    assert calls == [] and not receipt.exists()


@pytest.mark.parametrize(
    ("symref", "expected"),
    [
        (f"ref: refs/heads/main\tHEAD\n{SHA}\tHEAD\n", "main"),
        (f"ref: refs/heads/master\tHEAD\n{SHA}\tHEAD\n", "master"),
    ],
)
def test_resolve_default_branch_accepts_only_canonical_remote_head(monkeypatch: pytest.MonkeyPatch, symref: str, expected: str) -> None:
    monkeypatch.setattr(publish, "_run", lambda *args, **kwargs: _completed(symref.encode()))
    assert publish._resolve_default_branch({}, "not-real") == expected


@pytest.mark.parametrize("symref", ["", "ref: refs/heads/feature\tHEAD\n", "ref: refs/heads/main\tHEAD\nref: refs/heads/master\tHEAD\n", "ref: refs/tags/v1\tHEAD\n"])
def test_resolve_default_branch_rejects_ambiguous_or_unapproved_remote_head(monkeypatch: pytest.MonkeyPatch, symref: str) -> None:
    monkeypatch.setattr(publish, "_run", lambda *args, **kwargs: _completed(symref.encode()))
    with pytest.raises(publish.PublishError):
        publish._resolve_default_branch({}, "not-real")


def _prepare_execute_mocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, remote_sha: str = NEW_SHA, branch: str = "main") -> tuple[list[list[str]], Path, Path]:
    source, receipt = tmp_path / "source", tmp_path / "receipt.json"
    source.mkdir()
    calls: list[list[str]] = []
    monkeypatch.setenv(publish.TOKEN_ENV, "test-token-not-real")
    monkeypatch.setattr(publish, "_clean_source", lambda _: (source, SHA))
    monkeypatch.setattr(publish, "_resolve_default_branch", lambda *_: branch)
    monkeypatch.setattr(publish, "_extract_archive", lambda _, destination: (destination / "README.md").write_text("frozen\n", encoding="utf-8"))
    monkeypatch.setattr(publish, "_require_clean_clone", lambda clone, branch, expected_head=None: expected_head or SHA)
    monkeypatch.setattr(publish, "_delete_tracked_files", lambda _: None)
    monkeypatch.setattr(publish, "_stage_exact_release", lambda *_: None)
    monkeypatch.setattr(publish, "_index_projection_gate", lambda *_: None)

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if args[:2] == ["git", "clone"]:
            clone = Path(args[-1])
            clone.mkdir(parents=True, exist_ok=True)
            release = clone.parent / "release"
            if clone.name == "post" and release.exists():
                shutil.copytree(release, clone, dirs_exist_ok=True)
        if args[-2:] == ["rev-parse", "HEAD"]:
            return _completed((NEW_SHA + "\n").encode())
        if args[-1] == f"origin/{branch}":
            return _completed((SHA + "\n").encode())
        if args[:2] == ["git", "ls-remote"]:
            return _completed(f"{remote_sha}\trefs/heads/{branch}\n".encode())
        return _completed()

    monkeypatch.setattr(publish, "_run", fake_run)
    return calls, source, receipt


@pytest.mark.parametrize("branch", ["main", "master"])
def test_execute_uses_resolved_branch_and_never_places_token_in_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, branch: str) -> None:
    calls, source, receipt = _prepare_execute_mocks(monkeypatch, tmp_path, branch=branch)
    result = publish.publish(source, receipt, execute=True)
    assert result["status"] == "verified" and result["branch"] == branch
    assert any(call[:2] == ["git", "clone"] and "--branch" in call and call[call.index("--branch") + 1] == branch for call in calls)
    assert any("push" in call and "--force" not in call for call in calls)
    assert all("test-token-not-real" not in " ".join(call) for call in calls)
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "verified"


def test_receipt_prewrite_failure_prevents_push(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls, source, receipt = _prepare_execute_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr(publish, "_atomic_receipt", lambda *args, **kwargs: (_ for _ in ()).throw(publish.PublishError("receipt write failed")))
    with pytest.raises(publish.PublishError, match="receipt write failed"):
        publish.publish(source, receipt, execute=True)
    assert not any("push" in call for call in calls)


@pytest.mark.parametrize("gate_failure", ["missing manifest path", "extra stale path", "blob mismatch"])
def test_index_gate_failure_prevents_commit_push_and_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate_failure: str) -> None:
    calls, source, receipt = _prepare_execute_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr(publish, "_index_projection_gate", lambda *_: (_ for _ in ()).throw(publish.PublishError(gate_failure)))
    with pytest.raises(publish.PublishError, match=gate_failure):
        publish.publish(source, receipt, execute=True)
    assert not receipt.exists()
    assert not any("commit" in call or "push" in call for call in calls)


def test_post_push_mismatch_keeps_durable_remote_mismatch_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls, source, receipt = _prepare_execute_mocks(monkeypatch, tmp_path, remote_sha="c" * 40)
    with pytest.raises(publish.PublishedUnverifiedReceipt, match="remote SHA mismatch"):
        publish.publish(source, receipt, execute=True)
    assert any("push" in call for call in calls)
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "remote_mismatch"


def test_final_receipt_failure_after_push_keeps_prepared_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls, source, receipt = _prepare_execute_mocks(monkeypatch, tmp_path)
    original = publish._atomic_receipt
    count = 0

    def fail_finalize(path: Path, payload: dict[str, str], *, require_new: bool) -> None:
        nonlocal count
        count += 1
        if count > 1:
            raise publish.PublishError("simulated receipt finalize failure")
        original(path, payload, require_new=require_new)

    monkeypatch.setattr(publish, "_atomic_receipt", fail_finalize)
    with pytest.raises(publish.PublishedUnverifiedReceipt, match="receipt finalization failed"):
        publish.publish(source, receipt, execute=True)
    assert any("push" in call for call in calls)
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "prepared"
