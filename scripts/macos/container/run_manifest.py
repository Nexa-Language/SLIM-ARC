#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


VARIANTS = frozenset({"baseline", "patched"})
OUTCOMES = frozenset({"success", "oom", "timeout", "error"})
SLIM_ARC_ENV_ALLOWLIST = frozenset(
    {
        "SLIM_ARC_DECODE_MADV",
        "SLIM_ARC_DISABLE",
        "SLIM_ARC_DYNAMIC_MADV",
        "SLIM_ARC_EXPERT_BUDGET",
        "SLIM_ARC_EXPERT_CONF",
        "SLIM_ARC_EXPERT_POP",
        "SLIM_ARC_EXPERT_RECLAIM_WASTE",
        "SLIM_ARC_EXPERT_RESIDENCY",
        "SLIM_ARC_KV_EVICT",
        "SLIM_ARC_KV_SINK",
        "SLIM_ARC_KV_WINDOW",
        "SLIM_ARC_NO_MADV_RANDOM",
        "SLIM_ARC_NO_PREFETCH",
        "SLIM_ARC_PRESSURE_ADMISSION",
        "SLIM_ARC_PRESSURE_RESERVE_MB",
    }
)
RUNTIME_LINE_PREFIX = "[SLIM-ARC-RUNTIME]"
RUNTIME_COUNTER_FIELDS = (
    "expert_samples",
    "expert_issued_bytes",
    "expert_hit_bytes",
    "expert_waste_bytes",
    "reclaim_candidates",
    "reclaim_calls",
    "reclaimed_bytes",
    "reclaim_skipped_bytes",
    "reclaim_failures",
    "residency_samples",
    "residency_admitted_experts",
    "residency_admitted_bytes",
    "residency_skipped_bytes",
    "residency_fallbacks",
    "pressure_normal",
    "pressure_high",
    "pressure_critical",
)
RUNTIME_FIELD_NAMES = ("schema", *RUNTIME_COUNTER_FIELDS)
UINT64_MAX = 2**64 - 1
ASCII_UNSIGNED_DECIMAL = re.compile(r"[0-9]+", flags=re.ASCII)


def _read_int(path: Path, *, positive: bool = False) -> int:
    if not path.is_file():
        raise ValueError(f"required cgroup file is missing: {path.name}")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw.isdecimal():
        raise ValueError(f"{path.name} must contain a finite integer")
    value = int(raw)
    if positive and value <= 0:
        raise ValueError(f"{path.name} must be positive")
    return value


def _read_key_values(path: Path) -> dict[str, int] | None:
    if not path.is_file():
        return None
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdecimal():
            raise ValueError(f"invalid key/value row in {path.name}")
        result[parts[0]] = int(parts[1])
    return result


def _read_build_manifest(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("build manifest is missing")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value
    if values.get("LLAMA_COMMIT") != "360e134":
        raise ValueError("unexpected llama commit in build manifest")
    return values


def _read_cpu_limit(path: Path) -> tuple[int, int]:
    if not path.is_file():
        raise ValueError("required cgroup file is missing: cpu.max")
    parts = path.read_text(encoding="utf-8").split()
    if len(parts) != 2 or not all(part.isdecimal() for part in parts):
        raise ValueError("cpu.max must contain a finite quota and period")
    quota, period = (int(part) for part in parts)
    if quota <= 0 or period <= 0:
        raise ValueError("cpu.max quota and period must be positive")
    return quota, period


def collect_slim_arc_environment(environment: Mapping[str, str]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for name, value in environment.items():
        if not name.startswith("SLIM_ARC_"):
            continue
        if name not in SLIM_ARC_ENV_ALLOWLIST:
            raise ValueError(f"unsupported SLIM-ARC environment variable: {name}")
        if name in {
            "SLIM_ARC_EXPERT_RECLAIM_WASTE",
            "SLIM_ARC_EXPERT_RESIDENCY",
        } and value != "1":
            raise ValueError(f"{name} must be exactly 1")
        selected[name] = value
    return dict(sorted(selected.items()))


def parse_runtime_metric_line(line: str) -> dict[str, int]:
    if not line.startswith(f"{RUNTIME_LINE_PREFIX} "):
        raise ValueError("runtime metric line has an invalid prefix")
    fields: dict[str, int] = {}
    for item in line[len(RUNTIME_LINE_PREFIX) + 1 :].split(" "):
        name, separator, raw_value = item.partition("=")
        if not separator or not name or not raw_value or "=" in raw_value:
            raise ValueError("runtime metric field must be NAME=VALUE")
        if name in fields:
            raise ValueError(f"duplicate runtime metric field: {name}")
        if name not in RUNTIME_FIELD_NAMES:
            raise ValueError(f"unknown runtime metric field: {name}")
        if ASCII_UNSIGNED_DECIMAL.fullmatch(raw_value) is None:
            raise ValueError(f"runtime metric value is not an unsigned decimal: {name}")
        value = int(raw_value)
        if value > UINT64_MAX:
            raise ValueError(f"runtime metric value exceeds uint64_t: {name}")
        fields[name] = value
    if set(fields) != set(RUNTIME_FIELD_NAMES):
        raise ValueError("runtime metric fields do not match the required schema")
    if fields["schema"] != 1:
        raise ValueError("unsupported runtime metric schema")
    return fields


def parse_runtime_log(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise ValueError(f"runtime log is missing: {path}")
    runtime_lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(RUNTIME_LINE_PREFIX)
    ]
    if len(runtime_lines) != 1:
        raise ValueError(f"runtime log must contain exactly one runtime line: {path}")
    return parse_runtime_metric_line(runtime_lines[0])


def _runtime_metrics_summary(metrics: Sequence[Mapping[str, int]]) -> dict[str, int]:
    summary = {name: 0 for name in RUNTIME_COUNTER_FIELDS}
    for metric in metrics:
        for name in RUNTIME_COUNTER_FIELDS:
            summary[name] = min(UINT64_MAX, summary[name] + metric[name])
    return summary


def _runtime_metrics(
    *, variant: str, outcome: str, repetitions: int, runtime_logs: Sequence[Path]
) -> list[dict[str, int]]:
    if variant == "baseline":
        for path in runtime_logs:
            if not path.is_file():
                raise ValueError(f"runtime log is missing: {path}")
            if any(
                line.startswith(RUNTIME_LINE_PREFIX)
                for line in path.read_text(encoding="utf-8").splitlines()
            ):
                raise ValueError("baseline runtime log must not contain metrics")
        return []
    if outcome != "success":
        return []
    if len(runtime_logs) != repetitions:
        raise ValueError("patched success runtime log count must equal repetitions")
    return [parse_runtime_log(path) for path in runtime_logs]


def build_manifest(
    *,
    variant: str,
    outcome: str,
    exit_code: int,
    cgroup_dir: Path,
    build_manifest_path: Path,
    pp: int,
    tg: int,
    threads: int,
    repetitions: int,
    environment: Mapping[str, str],
    runtime_logs: Sequence[Path] = (),
) -> dict[str, object]:
    if variant not in VARIANTS:
        raise ValueError(f"unsupported variant: {variant}")
    if outcome not in OUTCOMES:
        raise ValueError(f"unsupported outcome: {outcome}")
    if min(pp, tg, threads, repetitions) <= 0:
        raise ValueError("benchmark dimensions must be positive")

    memory_limit = _read_int(cgroup_dir / "memory.max", positive=True)
    swap_limit = _read_int(cgroup_dir / "memory.swap.max")
    if swap_limit != 0:
        raise ValueError("memory swap limit must be zero")
    cpu_quota, cpu_period = _read_cpu_limit(cgroup_dir / "cpu.max")
    build = _read_build_manifest(build_manifest_path)
    peak_path = cgroup_dir / "memory.peak"
    memory_peak = _read_int(peak_path) if peak_path.is_file() else None
    runtime_metrics = _runtime_metrics(
        variant=variant,
        outcome=outcome,
        repetitions=repetitions,
        runtime_logs=runtime_logs,
    )

    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "variant": variant,
        "outcome": outcome,
        "exit_code": exit_code,
        "pp": pp,
        "tg": tg,
        "threads": threads,
        "repetitions": repetitions,
        "memory_limit_bytes": memory_limit,
        "memory_swap_limit_bytes": swap_limit,
        "memory_peak_bytes": memory_peak,
        "memory_events": _read_key_values(cgroup_dir / "memory.events"),
        "cpu_quota": cpu_quota,
        "cpu_period": cpu_period,
        "llama_commit": build["LLAMA_COMMIT"],
        "llama_resolved_commit": build.get("LLAMA_RESOLVED_COMMIT"),
        "environment": collect_slim_arc_environment(environment),
        "runtime_metrics": runtime_metrics,
        "runtime_metrics_summary": _runtime_metrics_summary(runtime_metrics),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write a validated constrained-run manifest."
    )
    parser.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    parser.add_argument("--outcome", required=True, choices=sorted(OUTCOMES))
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--cgroup-dir", required=True, type=Path)
    parser.add_argument("--build-manifest", required=True, type=Path)
    parser.add_argument("--pp", required=True, type=int)
    parser.add_argument("--tg", required=True, type=int)
    parser.add_argument("--threads", required=True, type=int)
    parser.add_argument("--repetitions", required=True, type=int)
    parser.add_argument("--runtime-log", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    manifest = build_manifest(
        variant=args.variant,
        outcome=args.outcome,
        exit_code=args.exit_code,
        cgroup_dir=args.cgroup_dir,
        build_manifest_path=args.build_manifest,
        pp=args.pp,
        tg=args.tg,
        threads=args.threads,
        repetitions=args.repetitions,
        environment=os.environ,
        runtime_logs=args.runtime_log,
    )
    with args.output.open("w", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
