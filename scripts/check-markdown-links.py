#!/usr/bin/env python3
"""Validate repository-relative links in public maintenance documentation."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
ROOT_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "AUTHORS.md",
    "CHANGELOG.md",
    "NOTICE",
)
PUBLIC_DOCUMENT_DIRS = ("docs/wiki", "docs/guides")


def public_documents() -> list[Path]:
    documents = [ROOT / name for name in ROOT_DOCUMENTS if (ROOT / name).is_file()]
    for directory in PUBLIC_DOCUMENT_DIRS:
        documents.extend(sorted((ROOT / directory).glob("*.md")))
    return documents


def relative_target(raw_target: str) -> str | None:
    target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    return unquote(target.split("#", maxsplit=1)[0])


def main() -> int:
    failures: list[str] = []
    for document in public_documents():
        text = document.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(text):
            target = relative_target(raw_target)
            if target is None:
                continue
            destination = (ROOT / target.lstrip("/")) if target.startswith("/") else (document.parent / target)
            resolved = destination.resolve()
            wiki_page = resolved.with_suffix(".md") if document.parent == ROOT / "docs/wiki" else resolved
            if not resolved.exists() and not wiki_page.exists():
                failures.append(f"{document.relative_to(ROOT)} -> {target}")
    if failures:
        print("Markdown link check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"Markdown link check passed for {len(public_documents())} documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
