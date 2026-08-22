#!/usr/bin/env python3
"""Reject accidental local state and oversized files from the public tree."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_GIT_FILE_BYTES = 100 * 1024 * 1024
FORBIDDEN_TRACKED_PATHS = (
    "AGENT.md",
    "design-qa.md",
    "plan/",
    "docs/superpowers/",
    "logs/roo_task_",
)
TEXT_SUFFIXES = {".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".tex", ".py", ".sh"}
FORBIDDEN_TEXT = ("/Users/bytedance/", "file:///Users/", "/private/tmp/")


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / item.decode("utf-8") for item in output.split(b"\0") if item]


def main() -> int:
    failures: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if any(relative == prefix or relative.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PATHS):
            failures.append(f"forbidden tracked path: {relative}")
        if path.is_file() and path.stat().st_size > MAX_GIT_FILE_BYTES:
            failures.append(f"tracked file exceeds 100 MiB: {relative}")
        if relative != "scripts/check-public-tree.py" and path.suffix.lower() in TEXT_SUFFIXES and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            for marker in FORBIDDEN_TEXT:
                if marker in text:
                    failures.append(f"local absolute path {marker!r}: {relative}")
    if failures:
        print("Public-tree check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("Public-tree check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
