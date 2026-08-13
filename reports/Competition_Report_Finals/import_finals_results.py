#!/usr/bin/env python3
"""Validate the fixed finals JSON and atomically render its TeX import."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPORT_ROOT = Path(__file__).resolve().parent
RESULTS_PATH = REPORT_ROOT.parent.parent / "docs/macos_test_notes/2026-08-12/finals-results.json"
GENERATED_PATH = REPORT_ROOT / "sections/generated_finals_results.tex"
CONFIGURATIONS = ("baseline", "patched-control", "patched-reclaim", "patched-residency", "patched-combined")
CACHES = ("cold", "warm")
ROUNDS = (1, 2)
METRICS = ("memory_peak_bytes", "major_faults", "read_blocks", "wall_seconds", "decode_tps", "expert_waste_bytes")
DECISIONS = ("reclaim", "residency", "combined")
DECISION_VALUES = frozenset({"promoted", "kept_opt_in", "rejected", "insufficient_evidence"})


def _object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _pairs() -> set[tuple[str, str]]:
    return {(configuration, cache) for configuration in CONFIGURATIONS for cache in CACHES}


def validate_results(payload: object) -> Mapping[str, object]:
    """Validate the full machine-produced schema required for a finals PDF."""

    result = _object(payload, "finals results")
    expected_top = {"schema_version", "runs", "sample_counts", "aggregated_metrics", "per_cache", "decisions"}
    if set(result) != expected_top or result.get("schema_version") != 1:
        raise ValueError("unsupported finals-results schema")
    runs = result.get("runs")
    if not isinstance(runs, list) or len(runs) != 20:
        raise ValueError("finals results must contain exactly 20 runs")
    expected_run = {"run_id", "source_directory", "round", "configuration", "cache_state", "outcome", *METRICS}
    seen: set[tuple[int, str, str]] = set()
    run_ids: set[str] = set()
    for index, raw in enumerate(runs):
        run = _object(raw, f"runs[{index}]")
        if set(run) != expected_run:
            raise ValueError(f"runs[{index}] does not match the finals run schema")
        run_id = _text(run.get("run_id"), f"runs[{index}].run_id")
        _text(run.get("source_directory"), f"runs[{index}].source_directory")
        round_number, configuration, cache = run.get("round"), run.get("configuration"), run.get("cache_state")
        if isinstance(round_number, bool) or round_number not in ROUNDS:
            raise ValueError(f"runs[{index}] has an invalid round")
        if configuration not in CONFIGURATIONS or cache not in CACHES:
            raise ValueError(f"runs[{index}] has an invalid configuration or cache")
        if run.get("outcome") != "success":
            raise ValueError(f"runs[{index}] is not successful")
        for metric in METRICS:
            _number(run.get(metric), f"runs[{index}].{metric}")
        identity = (round_number, configuration, cache)
        if identity in seen or run_id in run_ids:
            raise ValueError("duplicate finals run identity")
        seen.add(identity)
        run_ids.add(run_id)
    expected_identities = {(round_number, configuration, cache) for round_number in ROUNDS for configuration, cache in _pairs()}
    if seen != expected_identities:
        raise ValueError("runs must contain each configuration/cache pair in both rounds")

    metric_keys = {f"{configuration}:{cache}" for configuration, cache in _pairs()}
    sample_counts = _object(result.get("sample_counts"), "sample_counts")
    if set(sample_counts) != metric_keys or any(value != 2 for value in sample_counts.values()):
        raise ValueError("sample_counts must record exactly two samples per configuration/cache pair")
    aggregates = _object(result.get("aggregated_metrics"), "aggregated_metrics")
    if set(aggregates) != metric_keys:
        raise ValueError("aggregated_metrics is incomplete")
    for key in metric_keys:
        aggregate = _object(aggregates[key], f"aggregated_metrics.{key}")
        if set(aggregate) != set(METRICS):
            raise ValueError(f"aggregated_metrics.{key} has an unexpected metric schema")
        for metric in METRICS:
            _number(aggregate[metric], f"aggregated_metrics.{key}.{metric}")
    per_cache = _object(result.get("per_cache"), "per_cache")
    if set(per_cache) != set(CACHES):
        raise ValueError("per_cache is incomplete")
    for cache in CACHES:
        values = _object(per_cache[cache], f"per_cache.{cache}")
        if set(values) != set(DECISIONS) or any(value not in DECISION_VALUES for value in values.values()):
            raise ValueError(f"per_cache.{cache} has invalid decisions")
    decisions = _object(result.get("decisions"), "decisions")
    if set(decisions) != set(DECISIONS) or any(value not in DECISION_VALUES for value in decisions.values()):
        raise ValueError("decisions is incomplete or invalid")
    return result


def _tex_number(value: object, digits: int = 3) -> str:
    return f"{_number(value, 'generated metric'):.{digits}f}"


def _tex_decision(value: object) -> str:
    return _text(value, "generated decision").replace("_", "\\_")


def render_results_tex(result: Mapping[str, object], json_sha256: str) -> str:
    """Render only values derived from a previously validated payload."""

    aggregates = _object(result["aggregated_metrics"], "aggregated_metrics")
    per_cache = _object(result["per_cache"], "per_cache")
    decisions = _object(result["decisions"], "decisions")
    control_cold = _object(aggregates["patched-control:cold"], "patched-control:cold")
    baseline_cold = _object(aggregates["baseline:cold"], "baseline:cold")
    reclaim_cold = _object(aggregates["patched-reclaim:cold"], "patched-reclaim:cold")
    residency_cold = _object(aggregates["patched-residency:cold"], "patched-residency:cold")
    combined_cold = _object(aggregates["patched-combined:cold"], "patched-combined:cold")
    control_cold_wall = _number(control_cold["wall_seconds"], "patched-control:cold.wall_seconds")
    combined_cold_wall = _number(combined_cold["wall_seconds"], "patched-combined:cold.wall_seconds")
    if control_cold_wall == 0:
        raise ValueError("patched-control:cold.wall_seconds must be positive")
    combined_cold_regression = (combined_cold_wall / control_cold_wall - 1.0) * 100.0
    memory_peaks = [
        _number(_object(aggregates[key], f"aggregated_metrics.{key}")["memory_peak_bytes"], f"aggregated_metrics.{key}.memory_peak_bytes")
        for key in sorted(aggregates)
    ]
    linebreak = "\\\\"
    lines = [
        "% Generated by import_finals_results.py; do not edit.",
        f"% finals-results.json SHA-256: {json_sha256}",
        f"\\newcommand{{\\FinalsResultsJsonSha}}{{{json_sha256}}}",
        "\\newcommand{\\FinalsResultsRunCount}{20}",
        f"\\newcommand{{\\FinalsControlColdWall}}{{{_tex_number(control_cold_wall)}}}",
        f"\\newcommand{{\\FinalsBaselineColdWall}}{{{_tex_number(baseline_cold['wall_seconds'])}}}",
        f"\\newcommand{{\\FinalsReclaimColdWall}}{{{_tex_number(reclaim_cold['wall_seconds'])}}}",
        f"\\newcommand{{\\FinalsResidencyColdWall}}{{{_tex_number(residency_cold['wall_seconds'])}}}",
        f"\\newcommand{{\\FinalsCombinedColdWall}}{{{_tex_number(combined_cold_wall)}}}",
        f"\\newcommand{{\\FinalsCombinedColdRegressionPercent}}{{{_tex_number(combined_cold_regression)}}}",
        f"\\newcommand{{\\FinalsPeakMinimumGiB}}{{{_tex_number(min(memory_peaks) / 1024**3)}}}",
        f"\\newcommand{{\\FinalsPeakMaximumGiB}}{{{_tex_number(max(memory_peaks) / 1024**3)}}}",
        "\\newcommand{\\FinalsResultsTable}{%",
        "\\begin{table}[H]",
        "\\centering",
        "\\small",
        "\\caption{固定 Mac 2\\,GiB/4 vCPU/no-swap 协议下的两轮聚合结果（由 finals-results.json 派生）。}",
        "\\label{tab:finals-results}",
        "\\begin{tabular}{llrrrr}",
        "\\toprule",
        "配置 & 缓存 & 峰值内存 (GiB) & Wall (s) & Decode (t/s) & 专家浪费 (B) " + linebreak,
        "\\midrule",
    ]
    for configuration in CONFIGURATIONS:
        for cache in CACHES:
            row = _object(aggregates[f"{configuration}:{cache}"], "aggregate")
            lines.append(
                f"{configuration} & {cache} & {_tex_number(_number(row['memory_peak_bytes'], 'memory_peak_bytes') / 1024**3)} & "
                f"{_tex_number(row['wall_seconds'])} & {_tex_number(row['decode_tps'])} & {_tex_number(row['expert_waste_bytes'], 0)} {linebreak}"
            )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "}",
            "\\newcommand{\\FinalsDecisionSummary}{%",
            "\\begin{table}[H]",
            "\\centering",
            "\\caption{由两轮 cache-separated promotion gate 聚合的功能分类（由 finals-results.json 派生）。}",
            "\\label{tab:finals-decisions}",
            "\\begin{tabular}{llll}",
            "\\toprule",
            "机制 & cold & warm & 总体 " + linebreak,
            "\\midrule",
            f"错误专家回收 & {_tex_decision(_object(per_cache['cold'], 'per_cache.cold')['reclaim'])} & "
            f"{_tex_decision(_object(per_cache['warm'], 'per_cache.warm')['reclaim'])} & {_tex_decision(decisions['reclaim'])} {linebreak}",
            f"专家驻留 & {_tex_decision(_object(per_cache['cold'], 'per_cache.cold')['residency'])} & "
            f"{_tex_decision(_object(per_cache['warm'], 'per_cache.warm')['residency'])} & {_tex_decision(decisions['residency'])} {linebreak}",
            f"组合策略 & {_tex_decision(_object(per_cache['cold'], 'per_cache.cold')['combined'])} & "
            f"{_tex_decision(_object(per_cache['warm'], 'per_cache.warm')['combined'])} & {_tex_decision(decisions['combined'])} {linebreak}",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "\\noindent\\scriptsize\\texttt{finals-results.json SHA-256: " + json_sha256 + "}\\normalsize",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def build_from_path(json_path: Path) -> str:
    if json_path.is_symlink() or not json_path.is_file():
        raise ValueError(f"missing or unsafe finals results: {json_path}")
    raw = json_path.read_bytes()
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("finals-results.json is not valid JSON") from error
    return render_results_tex(validate_results(payload), hashlib.sha256(raw).hexdigest())


def write_atomically(path: Path, content: str) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"unsafe generated TeX destination: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def verify_generated(path: Path, expected: str) -> None:
    if path.is_symlink() or not path.is_file() or path.read_text(encoding="utf-8") != expected:
        raise ValueError("generated finals TeX does not match the current finals-results.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.write and not args.verify:
        parser.error("at least one of --write or --verify is required")
    try:
        expected = build_from_path(RESULTS_PATH)
        if args.write:
            write_atomically(GENERATED_PATH, expected)
        if args.verify:
            verify_generated(GENERATED_PATH, expected)
    except (OSError, ValueError) as error:
        print(f"Finals result import failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
