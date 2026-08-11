#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RunRow:
    run_id: str
    outcome: str
    memory_gib: int
    cpus: int
    pp: int
    tg: int
    repetitions: int
    variant: str
    environment: Mapping[str, str]
    cache: str
    swap_limit_bytes: int
    memory_peak_bytes: int | None
    model_sha256: str
    llama_commit: str
    benchmark_rows: list[dict[str, object]]


def no_swap_rows(rows: Iterable[RunRow]) -> list[RunRow]:
    return [row for row in rows if row.swap_limit_bytes == 0]


def validate_rows(rows: Iterable[RunRow]) -> None:
    materialized = list(rows)
    run_ids = [row.run_id for row in materialized]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("duplicate run id in normalized results")
    model_hashes = {row.model_sha256 for row in materialized}
    if len(model_hashes) > 1:
        raise ValueError("model SHA-256 differs across benchmark rows")
    if model_hashes and (
        len(next(iter(model_hashes))) != 64
        or SHA256_PATTERN.fullmatch(next(iter(model_hashes))) is None
    ):
        raise ValueError("invalid model SHA-256 in benchmark rows")
    commits = {row.llama_commit for row in materialized}
    if commits - {"360e134"}:
        raise ValueError("llama commit differs from the pinned build")
    for row in materialized:
        if row.memory_gib < 2 or row.memory_gib > 16 or row.cpus < 1 or row.cpus > 8:
            raise ValueError(
                f"resource limits are outside the campaign bounds: {row.run_id}"
            )
        if row.swap_limit_bytes < 0:
            raise ValueError(f"negative swap limit: {row.run_id}")


def select_lowest_stable(rows: Iterable[RunRow]) -> RunRow:
    candidates = [
        row
        for row in no_swap_rows(rows)
        if row.outcome == "success" and row.pp == 64 and row.tg == 16
    ]
    by_memory: dict[int, list[RunRow]] = {}
    for row in candidates:
        by_memory.setdefault(row.memory_gib, []).append(row)
    for memory_gib in sorted(by_memory):
        tier_rows = by_memory[memory_gib]
        if {row.cache for row in tier_rows} >= {"cold", "warm"}:
            return next(row for row in tier_rows if row.cache == "cold")
    raise ValueError("no stable no-swap tier has both cold and warm successes")


def _require_int(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _load_benchmark_rows(run_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for log_path in sorted(run_dir.glob("rep-*.stdout.log")):
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(
                    f"benchmark output must contain JSON objects: {log_path}"
                )
            rows.append(payload)
    return rows


def load_run(run_dir: Path) -> RunRow:
    controller_path = run_dir / "controller-result.json"
    controller = json.loads(controller_path.read_text(encoding="utf-8"))
    config = controller.get("config")
    model = controller.get("model")
    if not isinstance(config, dict) or not isinstance(model, dict):
        raise ValueError(
            f"controller result lacks config or model identity: {run_dir.name}"
        )
    environment = config.get("env")
    if not isinstance(environment, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in environment.items()
    ):
        raise ValueError(f"invalid environment map: {run_dir.name}")
    model_sha256 = model.get("actual_sha256")
    if not isinstance(model_sha256, str):
        raise ValueError(f"missing model SHA-256: {run_dir.name}")

    wrapper_path = run_dir / "run-manifest.json"
    wrapper: dict[str, Any] = {}
    if wrapper_path.is_file():
        payload = json.loads(wrapper_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"run manifest must be a JSON object: {run_dir.name}")
        wrapper = payload
    configured_limit = _require_int(controller, "memory_limit_bytes")
    if wrapper and _require_int(wrapper, "memory_limit_bytes") != configured_limit:
        raise ValueError(
            f"memory limit disagrees between controller and cgroup: {run_dir.name}"
        )
    configured_swap = _require_int(controller, "memory_swap_limit_bytes")
    if wrapper and _require_int(wrapper, "memory_swap_limit_bytes") != configured_swap:
        raise ValueError(
            f"swap limit disagrees between controller and cgroup: {run_dir.name}"
        )

    memory_peak = wrapper.get("memory_peak_bytes")
    if memory_peak is not None and not isinstance(memory_peak, int):
        raise ValueError(f"memory peak must be an integer or null: {run_dir.name}")
    outcome = controller.get("outcome")
    variant = config.get("variant")
    if not isinstance(outcome, str) or not isinstance(variant, str):
        raise ValueError(f"invalid outcome or variant: {run_dir.name}")
    return RunRow(
        run_id=run_dir.name,
        outcome=outcome,
        memory_gib=_require_int(config, "memory_gib"),
        cpus=_require_int(config, "cpus"),
        pp=_require_int(config, "pp"),
        tg=_require_int(config, "tg"),
        repetitions=_require_int(config, "repetitions"),
        variant=variant,
        environment=dict(environment),
        cache="cold" if controller.get("cold_cache") is True else "warm",
        swap_limit_bytes=configured_swap,
        memory_peak_bytes=memory_peak,
        model_sha256=model_sha256,
        llama_commit=str(controller.get("llama_commit", "")),
        benchmark_rows=_load_benchmark_rows(run_dir),
    )


def load_rows(result_root: Path) -> list[RunRow]:
    runs_root = result_root / "runs"
    rows = [
        load_run(path.parent)
        for path in sorted(runs_root.glob("*/controller-result.json"))
    ]
    validate_rows(rows)
    return rows


def _configuration_name(row: RunRow) -> str:
    if row.variant == "baseline":
        return "baseline"
    if not row.environment:
        return "patched-default"
    return "patched-" + "+".join(
        f"{key}={value}" for key, value in sorted(row.environment.items())
    )


def _average_tokens_per_second(row: RunRow) -> float | None:
    values = [item.get("avg_ts") for item in row.benchmark_rows]
    numeric = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return sum(numeric) / len(numeric) if numeric else None


def render_summary(rows: list[RunRow]) -> str:
    lines = [
        "# macOS constrained 80B benchmark",
        "",
        "All primary rows use cgroups v2 with swap disabled.",
        "",
    ]
    if not rows:
        lines.extend(("No completed benchmark rows were found.", ""))
        return "\n".join(lines)
    lines.extend(
        (
            f"- Model SHA-256: `{rows[0].model_sha256}`",
            f"- llama.cpp: `{rows[0].llama_commit}`",
        )
    )
    survival = [
        row.memory_gib for row in no_swap_rows(rows) if row.outcome == "success"
    ]
    if survival:
        lines.append(f"- Lowest observed survival tier: {min(survival)} GiB")
    try:
        stable = select_lowest_stable(rows)
        lines.append(f"- Lowest stable tier: {stable.memory_gib} GiB")
    except ValueError:
        lines.append("- Lowest stable tier: not established")
    lines.extend(
        (
            "",
            "## Runs",
            "",
            "| Run | Config | Memory | CPUs | Cache | Outcome | Peak bytes | avg t/s |",
            "|---|---:|---:|---:|---|---|---:|---:|",
        )
    )
    for row in rows:
        peak = (
            "unsupported"
            if row.memory_peak_bytes is None
            else str(row.memory_peak_bytes)
        )
        speed = _average_tokens_per_second(row)
        speed_text = "unsupported" if speed is None else f"{speed:.4f}"
        lines.append(
            f"| `{row.run_id}` | `{_configuration_name(row)}` | {row.memory_gib} GiB | {row.cpus} | {row.cache} | {row.outcome} | {peak} | {speed_text} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_results(result_root: Path, rows: list[RunRow]) -> None:
    normalized = []
    for row in rows:
        payload = asdict(row)
        payload["environment"] = dict(row.environment)
        normalized.append(payload)
    (result_root / "results.json").write_text(
        json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (result_root / "summary.md").write_text(render_summary(rows), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize and summarize constrained SLIM-ARC runs."
    )
    parser.add_argument("--result-root", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        rows = load_rows(args.result_root)
        write_results(args.result_root, rows)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Unable to summarize benchmark results: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"rows": len(rows), "summary": str(args.result_root / "summary.md")},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
