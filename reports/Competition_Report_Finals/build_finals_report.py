#!/usr/bin/env python3
"""Build the finals PDF only with a current JSON hash proof injected by this driver."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import import_finals_results as importer


REPORT_ROOT = Path(__file__).resolve().parent
PDF_PATH = REPORT_ROOT / "main.pdf"


def _ensure_removable_pdf() -> None:
    if PDF_PATH.is_symlink():
        raise ValueError("refusing to build with a symlinked main.pdf")
    if PDF_PATH.exists() and not PDF_PATH.is_file():
        raise ValueError("refusing to build with a non-regular main.pdf")
    PDF_PATH.unlink(missing_ok=True)


def _current_hash(json_path: Path) -> str:
    if json_path.is_symlink() or not json_path.is_file():
        raise ValueError(f"missing or unsafe finals results: {json_path}")
    return hashlib.sha256(json_path.read_bytes()).hexdigest()


def _prepare_results(json_path: Path) -> str:
    expected = importer.build_from_path(json_path)
    if importer.GENERATED_PATH.exists() or importer.GENERATED_PATH.is_symlink():
        importer.verify_generated(importer.GENERATED_PATH, expected)
    importer.write_atomically(importer.GENERATED_PATH, expected)
    importer.verify_generated(importer.GENERATED_PATH, expected)
    current_hash = _current_hash(json_path)
    if f"\\newcommand{{\\FinalsResultsJsonSha}}{{{current_hash}}}" not in expected:
        raise ValueError("generated finals TeX hash does not bind the current JSON")
    return current_hash


def _entry_file(json_sha256: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".verified-finals-", suffix=".tex", dir=REPORT_ROOT, text=True)
    entry = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"\\def\\SLIMARCVerifiedBuild{{{json_sha256}}}\n\\input{{main.tex}}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        entry.unlink(missing_ok=True)
        raise
    return entry


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=REPORT_ROOT, check=True)


def build(json_path: Path) -> None:
    _ensure_removable_pdf()
    entry: Path | None = None
    succeeded = False
    try:
        json_sha256 = _prepare_results(json_path)
        entry = _entry_file(json_sha256)
        xelatex = ["xelatex", "-jobname=main", "-interaction=nonstopmode", "-halt-on-error", entry.name]
        _run(xelatex)
        _run(["bibtex", "main"])
        _run(xelatex)
        _run(xelatex)
        if PDF_PATH.is_symlink() or not PDF_PATH.is_file():
            raise ValueError("XeLaTeX did not produce a regular main.pdf")
        succeeded = True
    finally:
        if entry is not None:
            entry.unlink(missing_ok=True)
        if not succeeded and PDF_PATH.exists() and not PDF_PATH.is_symlink():
            PDF_PATH.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-path", type=Path, default=importer.RESULTS_PATH)
    args = parser.parse_args()
    try:
        build(args.results_path)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Finals report build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
