#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


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
        "SLIM_ARC_KV_EVICT",
        "SLIM_ARC_KV_SINK",
        "SLIM_ARC_KV_WINDOW",
        "SLIM_ARC_NO_MADV_RANDOM",
        "SLIM_ARC_NO_PREFETCH",
    }
)


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
    return {
        name: environment[name]
        for name in sorted(SLIM_ARC_ENV_ALLOWLIST)
        if name in environment
    }


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
    )
    with args.output.open("w", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
