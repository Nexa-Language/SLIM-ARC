#!/usr/bin/env python3
"""Write the immutable build provenance sidecar after verification gates pass."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

GIT_COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)
SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
REQUIRED_BUILD_FIELDS = (
    "LLAMA_COMMIT",
    "SLIM_ARC_GIT_COMMIT",
    "SLIM_ARC_BUILD_CONTEXT_SHA256",
    "PATCHED_SOURCE_SHA256",
)


def _read_build_fields(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("build manifest must be a regular file")
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or not value or key in fields:
            raise ValueError("build manifest contains duplicate or malformed fields")
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key, re.ASCII) is None:
            raise ValueError("build manifest contains an invalid field name")
        fields[key] = value
    missing = [name for name in REQUIRED_BUILD_FIELDS if name not in fields]
    if missing:
        raise ValueError(f"build manifest is missing fields: {', '.join(missing)}")
    if fields["LLAMA_COMMIT"] != "360e134":
        raise ValueError("build manifest has an unexpected llama commit")
    if GIT_COMMIT.fullmatch(fields["SLIM_ARC_GIT_COMMIT"]) is None:
        raise ValueError("SLIM_ARC_GIT_COMMIT is malformed")
    for name in ("SLIM_ARC_BUILD_CONTEXT_SHA256", "PATCHED_SOURCE_SHA256"):
        if SHA256.fullmatch(fields[name]) is None:
            raise ValueError(f"{name} is malformed")
    return fields


def _read_model_sha256(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError("model manifest must be a regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("model manifest must contain an object")
    expected, actual = payload.get("expected_sha256"), payload.get("actual_sha256")
    if (
        not isinstance(expected, str)
        or not isinstance(actual, str)
        or SHA256.fullmatch(expected) is None
        or SHA256.fullmatch(actual) is None
        or expected != actual
    ):
        raise ValueError("model manifest hash is missing, malformed, or mismatched")
    return expected


def _validate_output_dir(result_dir: Path) -> Path:
    if not result_dir.is_dir() or result_dir.is_symlink():
        raise ValueError("result directory must be an existing regular directory")
    output = result_dir / "build-evidence.json"
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise ValueError("build-evidence.json must be a regular file")
    return output


def _write_atomic(output: Path, payload: Mapping[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_build_evidence(
    result_dir: Path, build_manifest: Path, model_manifest: Path, image_id: str
) -> Path:
    output = _validate_output_dir(result_dir)
    fields = _read_build_fields(build_manifest)
    model_sha256 = _read_model_sha256(model_manifest)
    if IMAGE_ID.fullmatch(image_id) is None:
        raise ValueError("runtime image id is malformed")
    payload = {
        "schema_version": 1,
        "git_commit": fields["SLIM_ARC_GIT_COMMIT"],
        "build_context_sha256": fields["SLIM_ARC_BUILD_CONTEXT_SHA256"],
        "patched_source_sha256": fields["PATCHED_SOURCE_SHA256"],
        "model_sha256": model_sha256,
        "llama_commit": "360e134",
        "image_ids": {"baseline": image_id, "patched": image_id},
        "variant_linkage": {"baseline": "verified", "patched": "verified"},
    }
    _write_atomic(output, payload)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--build-manifest", required=True, type=Path)
    parser.add_argument("--model-manifest", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        output = write_build_evidence(
            args.result_dir, args.build_manifest, args.model_manifest, args.image_id
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"write-build-evidence: {error}") from error
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
