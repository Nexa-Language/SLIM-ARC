"""Build an immutable, allowlisted SLIM-ARC finals release tree offline.

``stage`` never overlays an existing directory.  It builds a complete release
candidate in a private sibling directory, verifies it, then atomically renames
that directory into a *previously nonexistent* output path.  Git/network work
belongs exclusively to ``publish-finals-gitlab.py``.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_SCHEMA_VERSION = 1
DEFAULT_MANIFEST_NAME = ".slim-arc-finals-manifest.json"
DEFAULT_MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_PPTX_MEMBERS = 1024
MAX_PPTX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_PPTX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_PPTX_COMPRESSION_RATIO = 100
ALLOWED_ROOT_FILES = {".gitattributes", "CHANGELOG.md", "CMakeLists.txt", "LICENSE", "Makefile", "NOTICE", "README.md", "pyproject.toml", "requirements.txt"}
TEXT_SUFFIXES = {".c", ".cc", ".cpp", ".csv", ".h", ".hpp", ".json", ".jsonl", ".md", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml"}
SOURCE_SUFFIXES = TEXT_SUFFIXES | {".css", ".html", ".js"}
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".svg"}
REPORT_DIRS = {"Competition_Report_Official"}
FINAL_PPTX: set[str] = set()
FINAL_PDF: set[str] = set()
FINAL_DOCS: set[str] = set()
DENIED_COMPONENTS = {".agent", ".agents", ".cache", ".claude", ".codex", ".git", ".omo", ".roo", ".svn", ".venv", "__pycache__", "build", "cache", "dist", "downloads", "models", "node_modules", "superpowers", "target"}
DENIED_SUFFIXES = {".a", ".bin", ".bz2", ".class", ".dll", ".dmg", ".dylib", ".exe", ".gguf", ".gz", ".iso", ".o", ".obj", ".onnx", ".pt", ".pth", ".pyc", ".rar", ".safetensors", ".so", ".tar", ".tgz", ".xz", ".zip", ".7z"}
MACHO_MAGICS = {b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"(?im)^\s*['\"]?(?:api[_-]?key|aws[_-]?secret(?:[_-]?access[_-]?key)?|token|password)['\"]?\s*[:=]\s*(?:['\"][^'\"\r\n]{8,}['\"]|[A-Za-z0-9_./+=:-]{20,})\s*[,;]?\s*$"
    ),
    re.compile(
        r"(?i)[{,]\s*['\"]?(?:api[_-]?key|aws[_-]?secret(?:[_-]?access[_-]?key)?|token|password)['\"]?\s*:\s*['\"][^'\"\r\n]{8,}['\"]"
    ),
)
COMMENT_SECRET_PATTERN = re.compile(
    r"(?im)#.*?\b(?:api[_-]?key|aws[_-]?secret(?:[_-]?access[_-]?key)?|token|password|secret)\b\s*[:=]\s*(?:['\"][^'\"\r\n]{8,}['\"]|[A-Za-z0-9_./+=:-]{20,})"
)


class ReleaseError(ValueError):
    """Raised when the release boundary cannot be proven safe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(raw_path: str) -> PurePosixPath:
    if not raw_path or "\\" in raw_path or raw_path.startswith("/") or "//" in raw_path:
        raise ReleaseError(f"unsafe relative path: {raw_path!r}")
    candidate = PurePosixPath(raw_path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts) or candidate.as_posix() != raw_path:
        raise ReleaseError(f"unsafe relative path: {raw_path!r}")
    return candidate


def _denied_reason(relative: PurePosixPath) -> str | None:
    parts = [part.lower() for part in relative.parts]
    name = parts[-1]
    if name in {"agent.md", "agents.md"}:
        return "internal agent instructions are denied"
    if name == ".ds_store" or name.startswith(".env"):
        return "environment or Finder state is denied"
    if any(part in DENIED_COMPONENTS for part in parts):
        return "denied path component"
    if re.search(r"(?:^|[_.-])(?:credential|cookie|token|secret)(?:$|[_.-])", name) or name.endswith((".key", ".pem")) or name in {"id_rsa", "known_hosts"}:
        return "credential-like filename is denied"
    if relative.suffix.lower() in DENIED_SUFFIXES:
        return "compiled, archive, or model artifact is denied"
    return None


def _allowlisted(relative: PurePosixPath) -> bool:
    parts = relative.parts
    if len(parts) == 1:
        return relative.name in ALLOWED_ROOT_FILES
    if parts[0] in {"config", "data"}:
        return relative.suffix.lower() in TEXT_SUFFIXES
    if parts[0] in {"patches", "scripts", "tests"}:
        return relative.suffix.lower() in SOURCE_SUFFIXES
    if parts[0] in {"src", "include", "examples", "assets"}:
        return relative.suffix.lower() in SOURCE_SUFFIXES | IMAGE_SUFFIXES
    if parts[0] == "docs":
        return relative.as_posix() in FINAL_DOCS
    if parts[0] != "reports":
        return False
    return len(parts) == 2 and relative.name in FINAL_PPTX | FINAL_PDF or len(parts) >= 3 and parts[1] in REPORT_DIRS and relative.suffix.lower() in SOURCE_SUFFIXES | IMAGE_SUFFIXES | {".bib", ".pdf", ".tex"}


def _may_contain_allowed(relative: PurePosixPath) -> bool:
    parts = relative.parts
    if not parts:
        return False
    if parts[0] in {"config", "data", "patches", "scripts", "tests", "src", "include", "examples", "assets"}:
        return True
    if parts[0] == "docs":
        return any(PurePosixPath(item).parts[: len(parts)] == parts for item in FINAL_DOCS)
    return parts[0] == "reports" and (len(parts) == 1 or len(parts) >= 2 and (parts[1] in REPORT_DIRS or parts[1] in FINAL_PPTX | FINAL_PDF))


def _must_fail_when_seen(relative: PurePosixPath) -> bool:
    name = relative.name.lower()
    return name == ".ds_store" or name.startswith(".env") or re.search(r"(?:^|[_.-])(?:credential|cookie|token|secret)(?:$|[_.-])", name) is not None or name.endswith((".key", ".pem")) or name in {"id_rsa", "known_hosts"}


def _internal_agent_file(relative: PurePosixPath) -> bool:
    return relative.name.lower() in {"agent.md", "agents.md"}


def _public_exclusion(relative: PurePosixPath) -> bool:
    """Exclude planning, generation traces, and non-public result trees."""
    parts = tuple(part.lower() for part in relative.parts)
    if relative.name.lower() in {"agent.md", "agents.md", "roadmap.md", ".gitignore"}:
        return True
    if not parts:
        return False
    if parts[0] in {"docs", "plan", "site"}:
        return True
    if parts[0] == "scripts" and len(parts) >= 2 and parts[1] in {"agent", "release"}:
        return True
    if parts[0] == "scripts" and relative.name.lower().startswith("prepare-gitlab"):
        return True
    if parts[0] == "tests" and ("agent" in parts or relative.name.lower() == "test_prepare_finals_gitlab.py"):
        return True
    if parts[0] == "reports" and len(parts) >= 2 and parts[1] != "competition_report_official":
        return True
    return False


def _ensure_directory(path: Path, label: str) -> Path:
    if not path.is_dir() or path.is_symlink():
        raise ReleaseError(f"{label} must be a real directory: {path}")
    return path.resolve(strict=True)


def _binary_reason(path: Path, relative: PurePosixPath) -> str | None:
    if not relative.suffix and path.stat().st_mode & 0o111:
        return "suffix-less executable is denied"
    header = path.read_bytes()[:8]
    if header.startswith(b"\x7fELF"):
        return "ELF executable is denied"
    if header[:4] in MACHO_MAGICS:
        return "Mach-O executable is denied"
    if header.startswith(b"MZ"):
        return "PE executable is denied"
    if header.startswith(b"PK\x03\x04") and relative.suffix.lower() != ".pptx":
        return "archive payload is denied"
    if relative.suffix.lower() == ".pdf" and not header.startswith(b"%PDF-"):
        return "PDF payload is invalid"
    if header.startswith(b"%PDF-") and relative.suffix.lower() != ".pdf":
        return "PDF payload has an unexpected suffix"
    return None


def _safe_pptx_fragments(path: Path) -> Iterable[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_PPTX_MEMBERS:
                raise ReleaseError("PPTX contains too many members")
            total = 0
            for info in infos:
                name = info.filename
                if info.flag_bits & 1:
                    raise ReleaseError("encrypted PPTX member is denied")
                if "\\" in name or name.startswith("/") or "//" in name:
                    raise ReleaseError("PPTX has unsafe member path")
                member = PurePosixPath(name)
                if any(part in {"", ".", ".."} for part in member.parts) or member.as_posix() != name:
                    raise ReleaseError("PPTX has unsafe member path")
                if info.file_size > MAX_PPTX_MEMBER_BYTES or info.compress_size == 0 and info.file_size or info.compress_size and info.file_size / info.compress_size > MAX_PPTX_COMPRESSION_RATIO:
                    raise ReleaseError("PPTX member exceeds decompression policy")
                total += info.file_size
                if total > MAX_PPTX_TOTAL_BYTES:
                    raise ReleaseError("PPTX exceeds total decompression policy")
                lower = name.lower()
                if lower.endswith((".bin", ".exe", ".dll", ".com", ".jar", ".zip", ".gz")) or lower.startswith("ppt/embeddings/") or lower in {"ppt/vbaproject.bin", "ppt/activeX"}:
                    raise ReleaseError("PPTX embeds an executable, macro, or OLE payload")
                permitted_text = lower == "[content_types].xml" or lower == "_rels/.rels" or lower.startswith(("ppt/", "docprops/")) and lower.endswith((".xml", ".rels", ".txt"))
                permitted_media = lower.startswith("ppt/media/") and Path(lower).suffix in IMAGE_SUFFIXES
                permitted_thumbnail = lower.startswith("docprops/thumbnail.") and Path(lower).suffix in IMAGE_SUFFIXES
                if not permitted_text and not permitted_media and not permitted_thumbnail:
                    raise ReleaseError("PPTX contains an unsupported member")
                if permitted_text:
                    yield archive.read(info).decode("utf-8", errors="ignore")
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleaseError(f"Office document is unreadable: {path}") from error


def _content_fragments(path: Path) -> Iterable[str]:
    if path.suffix.lower() == ".pptx":
        yield from _safe_pptx_fragments(path)
    elif path.suffix.lower() == ".pdf":
        yield path.read_bytes().decode("latin-1", errors="ignore")
    elif path.suffix.lower() not in IMAGE_SUFFIXES:
        try:
            yield path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ReleaseError(f"non-text payload is not permitted: {path}") from error


def _sensitive_identifier(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized in {"api_key", "aws_secret", "aws_secret_access_key", "password", "secret", "token"} or normalized.endswith(
        ("_api_key", "_password", "_secret", "_token")
    )


def _environment_lookup(node: ast.AST) -> bool:
    if isinstance(node, ast.Subscript):
        return (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and node.value.attr == "environ"
        )
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
        return (
            function.value.id == "os"
            and function.attr == "getenv"
            and len(node.args) == 1
            and not node.keywords
        )
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "get"
        and isinstance(function.value, ast.Attribute)
        and isinstance(function.value.value, ast.Name)
        and function.value.value.id == "os"
        and function.value.attr == "environ"
        and len(node.args) == 1
        and not node.keywords
    )


def _target_names(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Attribute):
        yield node.attr
    elif isinstance(node, (ast.List, ast.Tuple)):
        for item in node.elts:
            yield from _target_names(item)
    elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        yield node.slice.value


def _contains_secret_literal(node: ast.AST) -> bool:
    if _environment_lookup(node):
        return False
    return any(isinstance(item, ast.Constant) and isinstance(item.value, str) and len(item.value) >= 8 for item in ast.walk(node))


def _python_has_secret_literal(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise ReleaseError("Python source cannot be parsed for secret scanning") from error
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_sensitive_identifier(name) for target in targets for name in _target_names(target)) and _contains_secret_literal(node.value):
                return True
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and _sensitive_identifier(key.value) and _contains_secret_literal(value):
                    return True
        elif isinstance(node, ast.keyword) and node.arg is not None and _sensitive_identifier(node.arg) and _contains_secret_literal(node.value):
            return True
    return False


def _scan_secrets(path: Path, relative: PurePosixPath) -> None:
    for fragment in _content_fragments(path):
        python_literal = relative.suffix.lower() == ".py" and _python_has_secret_literal(fragment)
        if python_literal or COMMENT_SECRET_PATTERN.search(fragment) or any(pattern.search(fragment) for pattern in SECRET_PATTERNS):
            raise ReleaseError(f"secret-like content is denied: {relative.as_posix()}")


PUBLIC_CONTENT_DENY = re.compile(
    r"(?i)\b(?:agent\s+harness|codex|chatgpt|openai)\b|依托\s*agent|(?:负向|负优化|回退|被拒绝)实验|内部审计|队内沟通"
)


def _scan_public_content(path: Path, relative: PurePosixPath) -> None:
    public_document = relative.as_posix() == "README.md" or relative.parts[:2] == ("reports", "Competition_Report_Official")
    if not public_document or relative.suffix.lower() in IMAGE_SUFFIXES | {".pdf"}:
        return
    for fragment in _content_fragments(path):
        if PUBLIC_CONTENT_DENY.search(fragment):
            raise ReleaseError(f"non-public narrative is denied: {relative.as_posix()}")


def _scan_source(root: Path, max_file_bytes: int) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directory = Path(current)
        directories.sort()
        filenames.sort()
        kept: list[str] = []
        for name in directories:
            child = directory / name
            relative = PurePosixPath(child.relative_to(root).as_posix())
            if child.is_symlink():
                raise ReleaseError(f"symlink is denied: {relative}")
            if _public_exclusion(relative):
                continue
            reason = _denied_reason(relative)
            if relative.parts == (".git",):
                continue
            if reason and not _internal_agent_file(relative) and (_must_fail_when_seen(relative) or _may_contain_allowed(relative)):
                raise ReleaseError(f"denied source path {relative}: {reason}")
            if not reason:
                kept.append(name)
        directories[:] = kept
        for name in filenames:
            child = directory / name
            relative = PurePosixPath(child.relative_to(root).as_posix())
            if child.is_symlink():
                raise ReleaseError(f"symlink is denied: {relative}")
            if _public_exclusion(relative):
                continue
            reason = _denied_reason(relative)
            if reason:
                if not _internal_agent_file(relative) and (_must_fail_when_seen(relative) or _may_contain_allowed(relative)):
                    raise ReleaseError(f"denied source path {relative}: {reason}")
                continue
            if not child.is_file():
                raise ReleaseError(f"source entry is not a regular file: {relative}")
            binary = _binary_reason(child, relative)
            if binary:
                raise ReleaseError(f"denied source path {relative}: {binary}")
            if not _allowlisted(relative):
                continue
            size = child.stat().st_size
            if size > max_file_bytes:
                raise ReleaseError(f"file exceeds size policy ({max_file_bytes} bytes): {relative}")
            _scan_secrets(child, relative)
            _scan_public_content(child, relative)
            entries.append({"path": relative.as_posix(), "sha256": _sha256(child), "size": size})
    return entries


def build_source_manifest(source: Path, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, object]:
    if max_file_bytes <= 0:
        raise ReleaseError("max_file_bytes must be positive")
    root = _ensure_directory(source, "source")
    return {"files": sorted(_scan_source(root, max_file_bytes), key=lambda item: str(item["path"])), "schema_version": MANIFEST_SCHEMA_VERSION}


def _parse_manifest(payload: Any, label: str) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != {"files", "schema_version"} or payload["schema_version"] != MANIFEST_SCHEMA_VERSION or not isinstance(payload["files"], list):
        raise ReleaseError(f"{label} has an invalid schema")
    previous = ""
    files: list[dict[str, object]] = []
    for item in payload["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise ReleaseError(f"{label} has an invalid file entry")
        path, digest, size = item["path"], item["sha256"], item["size"]
        relative = _safe_relative(path) if isinstance(path, str) else None
        if relative is None or not isinstance(digest, str) or not isinstance(size, int) or isinstance(size, bool) or not _allowlisted(relative) or _denied_reason(relative) or path <= previous or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) or size < 0:
            raise ReleaseError(f"{label} has an invalid file entry")
        previous = path
        files.append({"path": path, "sha256": digest, "size": size})
    return {"files": files, "schema_version": MANIFEST_SCHEMA_VERSION}


def _manifest_path(root: Path, manifest_name: str) -> Path:
    relative = _safe_relative(manifest_name)
    if len(relative.parts) != 1 or _denied_reason(relative):
        raise ReleaseError("manifest name must be one permitted relative filename")
    return root / relative.name


def _read_manifest(root: Path, manifest_name: str) -> dict[str, object]:
    path = _manifest_path(root, manifest_name)
    if path.is_symlink() or not path.is_file():
        raise ReleaseError("manifest must be a regular file")
    try:
        return _parse_manifest(json.loads(path.read_text(encoding="utf-8")), "manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseError("manifest is unreadable") from error


def _copy_checked(source: Path, destination: Path, entry: dict[str, object]) -> None:
    if source.is_symlink() or not source.is_file() or source.stat().st_size != entry["size"] or _sha256(source) != entry["sha256"]:
        raise ReleaseError(f"source changed after manifest preflight: {entry['path']}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if destination.stat().st_size != entry["size"] or _sha256(destination) != entry["sha256"]:
        raise ReleaseError(f"copy mismatch: {entry['path']}")


def _write_manifest(root: Path, manifest_name: str, manifest: dict[str, object]) -> None:
    _manifest_path(root, manifest_name).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stage(source: Path, output: Path, manifest_name: str = DEFAULT_MANIFEST_NAME, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES, dry_run: bool = False) -> dict[str, object]:
    """Atomically publish a new complete release tree at a nonexistent output."""
    source_root = _ensure_directory(source, "source")
    if output.exists() or output.is_symlink():
        raise ReleaseError(f"output must not exist: {output}")
    parent = _ensure_directory(output.parent, "output parent")
    if source_root == parent / output.name:
        raise ReleaseError("source and output must be different directories")
    manifest = build_source_manifest(source_root, max_file_bytes)
    if any(item["path"] == manifest_name for item in manifest["files"]):
        raise ReleaseError("manifest name collides with a staged source path")
    _manifest_path(parent, manifest_name)
    if dry_run:
        return manifest
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=parent))
    try:
        for entry in manifest["files"]:
            relative = _safe_relative(str(entry["path"]))
            _copy_checked(source_root.joinpath(*relative.parts), temporary.joinpath(*relative.parts), entry)
        _write_manifest(temporary, manifest_name, manifest)
        verify(source_root, temporary, manifest_name, max_file_bytes=max_file_bytes)
        os.replace(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def verify(source: Path, output: Path, manifest_name: str = DEFAULT_MANIFEST_NAME, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, object]:
    """Read-only proof that a complete release tree matches its source manifest."""
    expected = build_source_manifest(source, max_file_bytes)
    root = _ensure_directory(output, "output")
    actual = _read_manifest(root, manifest_name)
    if actual != expected:
        raise ReleaseError("manifest mismatch between source and output")
    for entry in actual["files"]:
        candidate = root.joinpath(*_safe_relative(str(entry["path"])).parts)
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size != entry["size"] or _sha256(candidate) != entry["sha256"]:
            raise ReleaseError(f"manifest mismatch for staged file: {entry['path']}")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an offline SLIM-ARC finals release tree.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest-name", default=DEFAULT_MANIFEST_NAME)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run and args.verify:
        raise ReleaseError("--dry-run and --verify cannot be combined")
    manifest = verify(args.source, args.output, args.manifest_name, max_file_bytes=args.max_file_bytes) if args.verify else stage(args.source, args.output, args.manifest_name, max_file_bytes=args.max_file_bytes, dry_run=args.dry_run)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
