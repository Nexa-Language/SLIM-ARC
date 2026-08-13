"""Publish a frozen SLIM-ARC finals snapshot to the official GitLab project.

The default mode is an offline plan: it does not clone, fetch, commit, push, or
read credentials.  ``--execute`` enables the guarded network release flow.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

OFFICIAL_URL = "https://gitlab.eduxiji.net/T2026105589911358/project3136859-389100.git"
MIN_PRELIMINARY_COMMITS = 88
TOKEN_ENV = "SLIM_ARC_GITLAB_TOKEN"
MANIFEST_NAME = ".slim-arc-finals-manifest.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024


class PublishError(RuntimeError):
    """Raised before an unsafe or unverifiable publication action."""


class PublishedUnverifiedReceipt(PublishError):
    """The remote changed, but the local receipt could not reach verified state."""

    def __init__(self, result: dict[str, str], detail: str):
        super().__init__(detail)
        self.result = result


def _load_prepare() -> Any:
    path = Path(__file__).with_name("prepare-finals-gitlab.py")
    spec = importlib.util.spec_from_file_location("slim_arc_prepare_finals", path)
    if spec is None or spec.loader is None:
        raise PublishError("cannot load offline release-tree helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREPARE = _load_prepare()


def _redact(text: str, token: str | None = None) -> str:
    if token:
        text = text.replace(token, "[REDACTED]")
    return re.sub(r"(?i)(glpat-|gh[pousr]_)[A-Za-z0-9_-]+", r"\1[REDACTED]", text)


def _run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, token: str | None = None) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(args, cwd=cwd, env=env, capture_output=True, check=False)
    if completed.returncode:
        output = _redact((completed.stdout + completed.stderr).decode("utf-8", errors="replace"), token)
        raise PublishError(f"command failed ({args[0]}): {output.strip()}")
    return completed


def _clean_source(source: Path) -> tuple[Path, str]:
    candidate = source.resolve(strict=True)
    root = Path(_run(["git", "-C", str(candidate), "rev-parse", "--show-toplevel"]).stdout.decode().strip())
    if _run(["git", "-C", str(root), "status", "--porcelain=v1", "-z"]).stdout:
        raise PublishError("source Git worktree must be clean")
    head = _run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.decode().strip()
    if not HEX40.fullmatch(head):
        raise PublishError("source HEAD is not a full SHA-1 commit")
    return root, head


def _safe_git_relative(raw: str) -> PurePosixPath:
    return PREPARE._safe_relative(raw)


def _validated_tar_members(tar: tarfile.TarFile) -> list[tuple[tarfile.TarInfo, PurePosixPath]]:
    members = tar.getmembers()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise PublishError("git archive contains too many members")
    entries: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
    types: dict[str, bool] = {}
    folded: set[str] = set()
    total = 0
    for member in members:
        raw = member.name
        is_directory = member.isdir()
        spelling = raw[:-1] if is_directory and raw.endswith("/") else raw
        try:
            relative = _safe_git_relative(spelling)
        except Exception as error:
            raise PublishError("git archive has unsafe member path") from error
        canonical = relative.as_posix()
        permitted_spellings = {canonical, f"{canonical}/"} if is_directory else {canonical}
        if raw not in permitted_spellings:
            raise PublishError("git archive has noncanonical member path")
        if not (is_directory or member.isfile()) or member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise PublishError("git archive has an unsupported member type")
        if member.size < 0 or member.size > MAX_ARCHIVE_MEMBER_BYTES:
            raise PublishError("git archive member exceeds size policy")
        total += member.size
        if total > MAX_ARCHIVE_TOTAL_BYTES:
            raise PublishError("git archive exceeds total size policy")
        name = relative.as_posix()
        if name in types or name.casefold() in folded:
            raise PublishError("git archive has duplicate or case-colliding member paths")
        for parent in relative.parents:
            prior = types.get(parent.as_posix())
            if prior is False:
                raise PublishError("git archive has file-directory path collision")
        if not is_directory and any(existing.startswith(f"{name}/") for existing in types):
            raise PublishError("git archive has file-directory path collision")
        types[name] = is_directory
        folded.add(name.casefold())
        entries.append((member, relative))
    return entries


def _under_root(root: Path, candidate: Path) -> bool:
    resolved = candidate.resolve(strict=False)
    return resolved == root or root in resolved.parents


def _extract_tar_bytes(archive: bytes, destination: Path) -> None:
    root = destination.resolve(strict=True)
    if destination.is_symlink() or not destination.is_dir():
        raise PublishError("archive destination must be a real directory")
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            entries = _validated_tar_members(tar)
            for member, relative in entries:
                output = root.joinpath(*relative.parts)
                if not _under_root(root, output.parent):
                    raise PublishError("git archive extraction escaped destination")
                if member.isdir():
                    output.mkdir(mode=0o700, parents=True, exist_ok=True)
                    if output.is_symlink() or not output.is_dir():
                        raise PublishError("git archive directory conflicts with existing path")
                    continue
                output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if output.parent.is_symlink() or not output.parent.is_dir() or not _under_root(root, output.parent):
                    raise PublishError("git archive parent is unsafe")
                stream = tar.extractfile(member)
                if stream is None:
                    raise PublishError("git archive regular member has no data stream")
                written = 0
                descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    with os.fdopen(descriptor, "wb") as target:
                        while chunk := stream.read(1024 * 1024):
                            written += len(chunk)
                            if written > member.size:
                                raise PublishError("git archive member exceeds header size")
                            target.write(chunk)
                    if written != member.size:
                        raise PublishError("git archive member is truncated")
                    output.chmod(0o644)
                finally:
                    stream.close()
    except (OSError, tarfile.TarError) as error:
        raise PublishError("git archive extraction failed") from error


def _extract_archive(source: Path, destination: Path) -> None:
    archive = _run(["git", "-C", str(source), "archive", "--format=tar", "HEAD"]).stdout
    _extract_tar_bytes(archive, destination)


def _askpass_environment(root: Path, token: str) -> dict[str, str]:
    script = root / "askpass.sh"
    script.write_text("#!/bin/sh\ncase \"$1\" in\n  *Username*) printf '%s\\n' oauth2 ;;\n  *Password*) printf '%s\\n' \"$SLIM_ARC_GITLAB_TOKEN\" ;;\n  *) exit 1 ;;\nesac\n", encoding="utf-8")
    script.chmod(0o700)
    environment = os.environ.copy()
    environment.update({"GIT_ASKPASS": str(script), "GIT_TERMINAL_PROMPT": "0", TOKEN_ENV: token})
    return environment


def _resolve_default_branch(environment: dict[str, str], token: str) -> str:
    output = _run(["git", "ls-remote", "--symref", OFFICIAL_URL, "HEAD"], env=environment, token=token).stdout.decode("utf-8", errors="strict")
    refs = [line for line in output.splitlines() if line.startswith("ref: ") and line.endswith("\tHEAD")]
    if len(refs) != 1:
        raise PublishError("official remote HEAD symref is missing or ambiguous")
    reference = refs[0][len("ref: ") : -len("\tHEAD")]
    prefix = "refs/heads/"
    if not reference.startswith(prefix):
        raise PublishError("official remote HEAD is not a branch ref")
    branch = reference[len(prefix) :]
    if branch not in {"main", "master"} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch):
        raise PublishError("official remote default branch is not an approved canonical branch")
    return branch


def _require_clean_clone(clone: Path, branch: str, expected_head: str | None = None) -> str:
    origin = _run(["git", "-C", str(clone), "remote", "get-url", "origin"]).stdout.decode().strip()
    if origin != OFFICIAL_URL:
        raise PublishError("clone origin does not match the canonical official URL")
    if _run(["git", "-C", str(clone), "status", "--porcelain=v1", "-z"]).stdout:
        raise PublishError("fresh official clone is not clean")
    head = _run(["git", "-C", str(clone), "rev-parse", "HEAD"]).stdout.decode().strip()
    current_branch = _run(["git", "-C", str(clone), "branch", "--show-current"]).stdout.decode().strip()
    if current_branch != branch or not HEX40.fullmatch(head) or expected_head is not None and head != expected_head:
        raise PublishError("official clone HEAD is unexpected")
    count = int(_run(["git", "-C", str(clone), "rev-list", "--count", "HEAD"]).stdout.decode().strip())
    if count < MIN_PRELIMINARY_COMMITS:
        raise PublishError("official preliminary history is shorter than expected")
    return head


def _delete_tracked_files(clone: Path) -> None:
    listed = _run(["git", "-C", str(clone), "ls-files", "-z"]).stdout.decode("utf-8", errors="strict").split("\0")
    for raw in listed:
        if not raw:
            continue
        relative = _safe_git_relative(raw)
        candidate = clone.joinpath(*relative.parts)
        if candidate.is_symlink() or not candidate.is_file():
            raise PublishError(f"tracked clone path is not a regular file: {raw}")
        candidate.unlink()


def _copy_release_tree(release: Path, clone: Path) -> None:
    for source in sorted(release.rglob("*")):
        if source.is_dir():
            continue
        relative = _safe_git_relative(source.relative_to(release).as_posix())
        if source.is_symlink() or not source.is_file() or relative.parts[0] == ".git":
            raise PublishError("release tree has an unsafe projection path")
        destination = clone.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _release_entries(release: Path) -> dict[str, tuple[bytes, str]]:
    manifest = PREPARE._read_manifest(release, MANIFEST_NAME)
    expected: dict[str, tuple[bytes, str]] = {}
    for entry in manifest["files"]:
        path = str(entry["path"])
        content = release.joinpath(*_safe_git_relative(path).parts).read_bytes()
        expected[path] = (content, str(entry["sha256"]))
    manifest_bytes = (release / MANIFEST_NAME).read_bytes()
    expected[MANIFEST_NAME] = (manifest_bytes, hashlib.sha256(manifest_bytes).hexdigest())
    return expected


def _stage_exact_release(clone: Path, release: Path) -> None:
    _run(["git", "-C", str(clone), "add", "-u"])
    for path in sorted(_release_entries(release)):
        _run(["git", "-C", str(clone), "add", "-f", "--", path])


def _parse_index_entries(payload: bytes) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, encoded_path = raw.split(b"\t", 1)
            mode, oid, stage = metadata.decode("ascii").split()
            path = encoded_path.decode("utf-8", errors="strict")
        except ValueError as error:
            raise PublishError("Git index entry has invalid syntax") from error
        _safe_git_relative(path)
        if stage != "0" or path in entries:
            raise PublishError("Git index has conflict or duplicate entry")
        entries[path] = (mode, oid)
    return entries


def _index_projection_gate(clone: Path, release: Path) -> None:
    expected = _release_entries(release)
    actual = _parse_index_entries(_run(["git", "-C", str(clone), "ls-files", "--cached", "-s", "-z"]).stdout)
    if set(actual) != set(expected):
        raise PublishError("Git index path set does not exactly match release manifest")
    for path, (expected_bytes, expected_sha) in expected.items():
        mode, _ = actual[path]
        if mode != "100644":
            raise PublishError(f"Git index path is not a regular non-executable file: {path}")
        index_bytes = _run(["git", "-C", str(clone), "show", f":{path}"]).stdout
        if index_bytes != expected_bytes or hashlib.sha256(index_bytes).hexdigest() != expected_sha:
            raise PublishError(f"Git index blob mismatch: {path}")


def _manifest_sha(release: Path) -> str:
    return hashlib.sha256((release / MANIFEST_NAME).read_bytes()).hexdigest()


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_receipt(path: Path, payload: dict[str, str], *, require_new: bool) -> None:
    if require_new:
        _validate_receipt_path(path)
    elif path.is_symlink() or not path.is_file():
        raise PublishError("prepared receipt is unavailable for finalization")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists():
        raise PublishError("receipt temporary path already exists")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _validate_receipt_path(path: Path) -> None:
    if path.exists() or path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        raise PublishError("receipt path must be a new file under a real directory")


def _preflight_receipt_parent(path: Path) -> None:
    _validate_receipt_path(path)
    probe = path.with_name(f".{path.name}.probe")
    if probe.exists():
        raise PublishError("receipt probe path already exists")
    try:
        with probe.open("xb") as stream:
            stream.write(b"probe\n")
            stream.flush()
            os.fsync(stream.fileno())
        probe.unlink()
        _fsync_directory(path.parent)
    except OSError as error:
        if probe.exists():
            probe.unlink(missing_ok=True)
        raise PublishError("receipt path is not durably writable") from error


def publish(source: Path, receipt: Path, *, execute: bool = False) -> dict[str, str]:
    """Validate a source locally, or execute the guarded, append-only release."""
    source_root, source_sha = _clean_source(source)
    if not execute:
        temporary_root = Path(tempfile.mkdtemp(prefix="slim-arc-finals-dry-run-"))
        try:
            frozen, release = temporary_root / "frozen", temporary_root / "release"
            frozen.mkdir()
            _extract_archive(source_root, frozen)
            PREPARE.stage(frozen, release, MANIFEST_NAME)
            PREPARE.verify(frozen, release, MANIFEST_NAME)
            return {"mode": "dry-run", "source_sha": source_sha, "manifest_sha256": _manifest_sha(release)}
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)
    _preflight_receipt_parent(receipt)
    token = os.environ.get(TOKEN_ENV)
    if not token:
        raise PublishError(f"{TOKEN_ENV} must be set for --execute")
    temporary_root = Path(tempfile.mkdtemp(prefix="slim-arc-finals-publish-", dir=receipt.parent))
    try:
        frozen, release, clone, post_clone = temporary_root / "frozen", temporary_root / "release", temporary_root / "official", temporary_root / "post"
        frozen.mkdir()
        _extract_archive(source_root, frozen)
        PREPARE.stage(frozen, release, MANIFEST_NAME)
        PREPARE.verify(frozen, release, MANIFEST_NAME)
        environment = _askpass_environment(temporary_root, token)
        branch = _resolve_default_branch(environment, token)
        _run(["git", "clone", "--branch", branch, "--single-branch", OFFICIAL_URL, str(clone)], env=environment, token=token)
        official_previous = _require_clean_clone(clone, branch)
        _delete_tracked_files(clone)
        _copy_release_tree(release, clone)
        PREPARE.verify(release, clone, MANIFEST_NAME)
        _stage_exact_release(clone, release)
        _index_projection_gate(clone, release)
        _run(["git", "-C", str(clone), "diff", "--cached", "--check"])
        _run(["git", "-C", str(clone), "commit", "-m", "[milestone] Publish finals release", "-m", "Root cause: NA\nSolution: Publish a frozen, verified finals release tree.\nRisks: Release contents are constrained by the finals allowlist.\nDependency: source@" + source_sha + "\nLinks: NA"], env=environment, token=token)
        new_sha = _run(["git", "-C", str(clone), "rev-parse", "HEAD"]).stdout.decode().strip()
        prepared = {"status": "prepared", "source_sha": source_sha, "official_previous_sha": official_previous, "planned_sha": new_sha, "branch": branch, "manifest_sha256": _manifest_sha(release), "timestamp": datetime.now(timezone.utc).isoformat()}
        _atomic_receipt(receipt, prepared, require_new=True)
        _run(["git", "-C", str(clone), "fetch", "origin", branch], env=environment, token=token)
        fetched = _run(["git", "-C", str(clone), "rev-parse", f"origin/{branch}"]).stdout.decode().strip()
        if fetched != official_previous:
            raise PublishError("official branch advanced before push; refusing non-fast-forward publication")
        _run(["git", "-C", str(clone), "merge-base", "--is-ancestor", official_previous, new_sha])
        _run(["git", "-C", str(clone), "push", "origin", f"HEAD:{branch}"], env=environment, token=token)
        remote = _run(["git", "ls-remote", OFFICIAL_URL, f"refs/heads/{branch}"], env=environment, token=token).stdout.decode().split()
        if not remote or remote[0] != new_sha:
            mismatch = {**prepared, "status": "remote_mismatch"}
            try:
                _atomic_receipt(receipt, mismatch, require_new=False)
            except PublishError as error:
                raise PublishedUnverifiedReceipt(prepared, f"published_unverified_receipt: remote SHA mismatch; receipt finalization failed: {error}") from error
            raise PublishedUnverifiedReceipt(mismatch, "published_unverified_receipt: post-push ls-remote SHA mismatch")
        _run(["git", "clone", "--branch", branch, OFFICIAL_URL, str(post_clone)], env=environment, token=token)
        try:
            _require_clean_clone(post_clone, branch, new_sha)
            PREPARE.verify(release, post_clone, MANIFEST_NAME)
            verified = {**prepared, "status": "verified", "official_new_sha": new_sha}
            _atomic_receipt(receipt, verified, require_new=False)
            return verified
        except Exception as error:
            try:
                _atomic_receipt(receipt, {**prepared, "status": "remote_mismatch"}, require_new=False)
            except PublishError as receipt_error:
                raise PublishedUnverifiedReceipt(prepared, f"published_unverified_receipt: {error}; receipt finalization failed: {receipt_error}") from receipt_error
            raise PublishedUnverifiedReceipt({**prepared, "status": "remote_mismatch"}, f"published_unverified_receipt: {error}") from error
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded official GitLab finals publisher.")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(publish(args.source, args.receipt, execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishedUnverifiedReceipt as error:
        print(json.dumps(error.result, indent=2, sort_keys=True), file=sys.stderr)
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(3)
    except PublishError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
