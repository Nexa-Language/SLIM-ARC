#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Mapping


REPO_ID = "Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF"
FILENAME = "Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
API_URL = f"https://huggingface.co/api/models/{REPO_ID}?blobs=true"
MIN_FILE_SIZE = 40_000_000_000
MAX_FILE_SIZE = 60_000_000_000
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ModelFile:
    repo_id: str
    revision: str
    filename: str
    size: int
    expected_sha256: str


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def select_model_file(payload: Mapping[str, Any]) -> ModelFile:
    repo_id = payload.get("id")
    if repo_id != REPO_ID:
        raise ValueError(f"unexpected repository id: {repo_id!r}")

    revision = payload.get("sha")
    if not isinstance(revision, str) or REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("model revision must be a 40-character lowercase Git SHA")

    siblings = payload.get("siblings")
    if not isinstance(siblings, list):
        raise ValueError("siblings must be a list")
    matches = [
        item
        for item in siblings
        if isinstance(item, Mapping) and item.get("rfilename") == FILENAME
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one exact model file named {FILENAME}")

    selected = matches[0]
    lfs = selected.get("lfs")
    if not isinstance(lfs, Mapping):
        raise ValueError("exact model file is missing LFS metadata")
    size = _require_int(selected.get("size"), "file size")
    lfs_size = _require_int(lfs.get("size"), "LFS size")
    if size != lfs_size:
        raise ValueError("file and LFS size mismatch")
    if not MIN_FILE_SIZE <= size <= MAX_FILE_SIZE:
        raise ValueError("model size must be between 40 GB and 60 GB")

    expected_sha256 = lfs.get("sha256")
    if (
        not isinstance(expected_sha256, str)
        or SHA256_PATTERN.fullmatch(expected_sha256) is None
    ):
        raise ValueError(
            "LFS SHA-256 must contain exactly 64 lowercase hexadecimal characters"
        )
    return ModelFile(
        repo_id=repo_id,
        revision=revision,
        filename=FILENAME,
        size=size,
        expected_sha256=expected_sha256,
    )


def fetch_payload(api_url: str) -> Mapping[str, Any]:
    request = urllib.request.Request(
        api_url, headers={"User-Agent": "SLIM-ARC-model-provenance/1"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, Mapping):
        raise ValueError("Hugging Face API response must be a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve the official Qwen Q4_K_M GGUF and validate its LFS metadata."
    )
    parser.add_argument("--api-url", default=API_URL)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        model = select_model_file(fetch_payload(args.api_url))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Unable to resolve verified model metadata: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(model), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
