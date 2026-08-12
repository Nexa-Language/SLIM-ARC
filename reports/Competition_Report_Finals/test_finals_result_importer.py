#!/usr/bin/env python3
"""Standard-library regression tests for the finals JSON-to-TeX release gate."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("finals_importer", ROOT / "import_finals_results.py")
assert SPEC is not None and SPEC.loader is not None
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


def valid_result() -> dict[str, object]:
    metrics = {
        "memory_peak_bytes": 2 * 1024**3,
        "major_faults": 1,
        "read_blocks": 2,
        "wall_seconds": 3.5,
        "decode_tps": 4.5,
        "expert_waste_bytes": 5,
    }
    runs: list[dict[str, object]] = []
    for round_number in IMPORTER.ROUNDS:
        for configuration in IMPORTER.CONFIGURATIONS:
            for cache in IMPORTER.CACHES:
                runs.append(
                    {
                        "run_id": f"r{round_number}-{configuration}-{cache}",
                        "source_directory": f"runs/r{round_number}-{configuration}-{cache}",
                        "round": round_number,
                        "configuration": configuration,
                        "cache_state": cache,
                        "outcome": "success",
                        **metrics,
                    }
                )
    keys = [f"{configuration}:{cache}" for configuration in IMPORTER.CONFIGURATIONS for cache in IMPORTER.CACHES]
    return {
        "schema_version": 1,
        "runs": runs,
        "sample_counts": {key: 2 for key in keys},
        "aggregated_metrics": {key: dict(metrics) for key in keys},
        "per_cache": {cache: {decision: "kept_opt_in" for decision in IMPORTER.DECISIONS} for cache in IMPORTER.CACHES},
        "decisions": {decision: "kept_opt_in" for decision in IMPORTER.DECISIONS},
    }


class FinalsResultImporterTests(unittest.TestCase):
    def write_fixture(self, directory: Path, payload: Any) -> Path:
        path = directory / "finals-results.json"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return path

    def test_valid_fixture_renders_hash_bound_tex(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = self.write_fixture(Path(temporary), valid_result())
            rendered = IMPORTER.build_from_path(source)
        self.assertIn("\\FinalsResultsJsonSha", rendered)
        self.assertIn("\\FinalsResultsRunCount}{20}", rendered)
        self.assertIn("\\FinalsResultsTable", rendered)

    def test_missing_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                IMPORTER.build_from_path(Path(temporary) / "finals-results.json")

    def test_malformed_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "finals-results.json"
            source.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                IMPORTER.build_from_path(source)

    def test_partial_matrix_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_result()
            runs = payload["runs"]
            assert isinstance(runs, list)
            runs.pop()
            source = self.write_fixture(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "exactly 20 runs"):
                IMPORTER.build_from_path(source)

    def test_non_success_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_result()
            runs = payload["runs"]
            assert isinstance(runs, list) and isinstance(runs[0], dict)
            runs[0]["outcome"] = "oom"
            source = self.write_fixture(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "not successful"):
                IMPORTER.build_from_path(source)

    def test_invalid_aggregate_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            payload = valid_result()
            aggregates = payload["aggregated_metrics"]
            assert isinstance(aggregates, dict)
            aggregates["baseline:cold"] = {}
            source = self.write_fixture(Path(temporary), payload)
            with self.assertRaisesRegex(ValueError, "unexpected metric schema"):
                IMPORTER.build_from_path(source)

    def test_atomic_write_and_stale_hash_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = self.write_fixture(directory, valid_result())
            generated = directory / "generated.tex"
            expected = IMPORTER.build_from_path(source)
            IMPORTER.write_atomically(generated, expected)
            IMPORTER.verify_generated(generated, expected)
            generated.write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                IMPORTER.verify_generated(generated, expected)


class FinalsBuildProofTests(unittest.TestCase):
    def isolated_report(self, temporary: Path) -> Path:
        report = temporary / "report"
        shutil.copytree(ROOT, report, ignore=shutil.ignore_patterns("__pycache__", "main.pdf", "main.aux", "main.bbl", "main.blg", "main.log", "main.out", "main.toc", "generated_finals_results.tex"))
        return report

    def write_json(self, temporary: Path, payload: dict[str, object], name: str = "finals-results.json") -> Path:
        source = temporary / name
        source.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return source

    def run_command(self, command: list[str], report: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=report, check=False, text=True, capture_output=True, timeout=120)

    def write_generated(self, report: Path, source: Path) -> str:
        expected = IMPORTER.build_from_path(source)
        IMPORTER.write_atomically(report / "sections/generated_finals_results.tex", expected)
        return hashlib.sha256(source.read_bytes()).hexdigest()

    def test_stale_generated_without_json_plain_xelatex_fails_without_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            report = self.isolated_report(temporary)
            source = self.write_json(temporary, valid_result())
            self.write_generated(report, source)
            source.unlink()
            result = self.run_command(["xelatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"], report)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((report / "main.pdf").exists())

    def test_valid_json_driver_builds_regular_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            report = self.isolated_report(temporary)
            source = self.write_json(temporary, valid_result())
            result = self.run_command([sys.executable, "build_finals_report.py", "--results-path", str(source)], report)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            pdf = report / "main.pdf"
            self.assertTrue(pdf.is_file())
            self.assertFalse(pdf.is_symlink())

    def test_changed_json_rejects_stale_generated_for_direct_and_driver_builds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            report = self.isolated_report(temporary)
            first = self.write_json(temporary, valid_result(), "first.json")
            self.write_generated(report, first)
            changed = valid_result()
            aggregates = changed["aggregated_metrics"]
            assert isinstance(aggregates, dict) and isinstance(aggregates["baseline:cold"], dict)
            aggregates["baseline:cold"]["wall_seconds"] = 9.5
            second = self.write_json(temporary, changed, "second.json")
            second_hash = hashlib.sha256(second.read_bytes()).hexdigest()
            entry = report / "direct-proof.tex"
            entry.write_text(f"\\def\\SLIMARCVerifiedBuild{{{second_hash}}}\n\\input{{main.tex}}\n", encoding="utf-8")
            direct = self.run_command(["xelatex", "-jobname=main", "-interaction=nonstopmode", "-halt-on-error", entry.name], report)
            self.assertNotEqual(direct.returncode, 0, direct.stdout + direct.stderr)
            self.assertFalse((report / "main.pdf").exists())
            driver = self.run_command([sys.executable, "build_finals_report.py", "--results-path", str(second)], report)
            self.assertNotEqual(driver.returncode, 0, driver.stdout + driver.stderr)
            self.assertFalse((report / "main.pdf").exists())

    def test_failed_build_removes_preexisting_regular_pdf_and_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            report = self.isolated_report(temporary)
            pdf = report / "main.pdf"
            pdf.write_bytes(b"stale")
            missing = temporary / "missing.json"
            failed = self.run_command([sys.executable, "build_finals_report.py", "--results-path", str(missing)], report)
            self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
            self.assertFalse(pdf.exists())
            target = temporary / "target.pdf"
            target.write_bytes(b"target")
            pdf.symlink_to(target)
            rejected = self.run_command([sys.executable, "build_finals_report.py", "--results-path", str(missing)], report)
            self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
            self.assertTrue(pdf.is_symlink())


if __name__ == "__main__":
    unittest.main()
