#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence


PROFILE = "slim-arc"
DOCKER_CONTEXT = "colima-slim-arc"
IMAGE = "slim-arc-llama:360e134"
MODEL_GUEST_PATH = "/var/lib/slim-arc/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
MODEL_CONTAINER_PATH = "/models/model.gguf"
REPO_ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = REPO_ROOT / "docs" / "macos_test_notes"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CONTAINER_NAME_PATTERN = re.compile(r"^slim-arc-run-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$")
ENV_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_.+-]{1,64}$")
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
        "SLIM_ARC_PRESSURE_ADMISSION",
        "SLIM_ARC_PRESSURE_RESERVE_MB",
    }
)


@dataclass(frozen=True)
class RunConfig:
    memory_gib: int
    cpus: int
    pp: int
    tg: int
    repetitions: int
    timeout_seconds: int
    variant: str
    env: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))

    def validate(self) -> None:
        if not 2 <= self.memory_gib <= 16:
            raise ValueError("memory_gib must be between 2 and 16")
        if not 1 <= self.cpus <= 8:
            raise ValueError("cpus must be between 1 and 8")
        if not 1 <= self.pp <= 512 or not 1 <= self.tg <= 128:
            raise ValueError("pp and tg exceed the bounded benchmark range")
        if not 1 <= self.repetitions <= 5:
            raise ValueError("repetitions must be between 1 and 5")
        if not 30 <= self.timeout_seconds <= 7200:
            raise ValueError("timeout_seconds must be between 30 and 7200")
        if self.variant not in {"baseline", "patched"}:
            raise ValueError("variant must be baseline or patched")
        if self.variant == "baseline" and self.env:
            raise ValueError(
                "baseline runs must not set SLIM-ARC environment variables"
            )
        for name, value in self.env.items():
            if name not in SLIM_ARC_ENV_ALLOWLIST:
                raise ValueError(f"unsupported SLIM-ARC environment variable: {name}")
            if ENV_VALUE_PATTERN.fullmatch(value) is None:
                raise ValueError(f"unsafe value for {name}")


@dataclass(frozen=True)
class RunResult:
    container_name: str
    outcome: str
    return_code: int | None
    oom_killed: bool
    result_dir: Path


def new_container_name(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    timestamp = current.astimezone(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    return f"slim-arc-run-{timestamp}-{secrets.token_hex(4)}"


def build_docker_command(
    config: RunConfig, result_dir: Path, *, container_name: str | None = None
) -> list[str]:
    config.validate()
    name = container_name or new_container_name()
    if CONTAINER_NAME_PATTERN.fullmatch(name) is None and name != "slim-arc-run-test":
        raise ValueError("invalid runner-owned container name")
    resolved_result = result_dir.resolve()
    if "," in str(resolved_result):
        raise ValueError("result path must not contain a comma")

    command = [
        "docker",
        "--context",
        DOCKER_CONTEXT,
        "run",
        "--name",
        name,
        "--memory",
        f"{config.memory_gib}g",
        "--memory-swap",
        f"{config.memory_gib}g",
        "--cpus",
        str(config.cpus),
        "--env",
        f"VARIANT={config.variant}",
        "--env",
        f"MODEL_PATH={MODEL_CONTAINER_PATH}",
        "--env",
        f"PP={config.pp}",
        "--env",
        f"TG={config.tg}",
        "--env",
        f"THREADS={config.cpus}",
        "--env",
        f"REPETITIONS={config.repetitions}",
    ]
    for name, value in sorted(config.env.items()):
        command.extend(("--env", f"{name}={value}"))
    command.extend(
        (
            "--mount",
            f"type=bind,source={MODEL_GUEST_PATH},target={MODEL_CONTAINER_PATH},readonly",
            "--mount",
            f"type=bind,source={resolved_result},target=/results",
            IMAGE,
            "/usr/local/bin/slim-arc-run-benchmark",
        )
    )
    return command


def resolve_result_dir(path: Path) -> Path:
    resolved = path.resolve()
    result_root = RESULT_ROOT.resolve()
    if resolved == result_root:
        raise ValueError("result directory must be below the benchmark result root")
    try:
        resolved.relative_to(result_root)
    except ValueError as exc:
        raise ValueError(
            "result directory must stay below docs/macos_test_notes"
        ) from exc
    return resolved


def classify_outcome(
    *,
    timed_out: bool,
    return_code: int | None,
    container_state: Mapping[str, object],
    memory_events: Mapping[str, int] | None,
) -> str:
    if timed_out:
        return "timeout"
    if container_state.get("OOMKilled") is True or (
        memory_events is not None and memory_events.get("oom_kill", 0) > 0
    ):
        return "oom"
    if return_code == 0 and container_state.get("ExitCode") == 0:
        return "success"
    return "error"


def _run(
    argv: Sequence[str], *, timeout: int | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        shell=False,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def _inspect_container(container_name: str) -> dict[str, object]:
    completed = _run(
        [
            "docker",
            "--context",
            DOCKER_CONTEXT,
            "inspect",
            container_name,
            "--format",
            "{{json .State}}",
        ],
        check=True,
    )
    state = json.loads(completed.stdout)
    if not isinstance(state, dict):
        raise ValueError("Docker container state must be a JSON object")
    return state


def _load_memory_events(result_dir: Path) -> dict[str, int] | None:
    manifest_path = result_dir / "run-manifest.json"
    if not manifest_path.is_file():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    events = payload.get("memory_events")
    if not isinstance(events, dict):
        return None
    return {
        str(key): int(value) for key, value in events.items() if isinstance(value, int)
    }


def _assert_model_ready() -> None:
    _run(
        ["colima", "--profile", PROFILE, "ssh", "--", "test", "-f", MODEL_GUEST_PATH],
        check=True,
    )


def _load_model_manifest(result_dir: Path) -> dict[str, object]:
    relative = result_dir.relative_to(RESULT_ROOT.resolve())
    if not relative.parts:
        raise ValueError("result directory must include a campaign directory")
    manifest_path = RESULT_ROOT.resolve() / relative.parts[0] / "model-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"verified model manifest is missing: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = payload.get("expected_sha256")
    actual = payload.get("actual_sha256")
    if (
        not isinstance(expected, str)
        or SHA256_PATTERN.fullmatch(expected) is None
        or actual != expected
    ):
        raise ValueError("model manifest does not contain a matching verified SHA-256")
    if payload.get("filename") != Path(MODEL_GUEST_PATH).name:
        raise ValueError("model manifest filename does not match the mounted model")
    return payload


def _drop_guest_caches() -> None:
    _run(
        [
            "colima",
            "--profile",
            PROFILE,
            "ssh",
            "--",
            "sudo",
            "sh",
            "-c",
            "sync; echo 3 > /proc/sys/vm/drop_caches",
        ],
        check=True,
    )


def _remove_owned_container(container_name: str) -> None:
    if CONTAINER_NAME_PATTERN.fullmatch(container_name) is None:
        raise ValueError("refusing to remove a non-runner container")
    _run(["docker", "--context", DOCKER_CONTEXT, "rm", container_name], check=True)


def _write_controller_result(
    *,
    path: Path,
    config: RunConfig,
    container_name: str,
    outcome: str,
    return_code: int | None,
    timed_out: bool,
    state: Mapping[str, object],
    stderr: str,
    model_manifest: Mapping[str, object],
    cold_cache: bool,
) -> None:
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "memory_gib": config.memory_gib,
            "cpus": config.cpus,
            "pp": config.pp,
            "tg": config.tg,
            "repetitions": config.repetitions,
            "timeout_seconds": config.timeout_seconds,
            "variant": config.variant,
            "env": dict(config.env),
        },
        "container_name": container_name,
        "outcome": outcome,
        "return_code": return_code,
        "timed_out": timed_out,
        "container_state": dict(state),
        "model": dict(model_manifest),
        "llama_commit": "360e134",
        "memory_limit_bytes": config.memory_gib * 1024**3,
        "memory_swap_limit_bytes": 0,
        "cold_cache": cold_cache,
        "stderr_summary": stderr[-2000:],
    }
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def run_once(
    config: RunConfig, result_dir: Path, *, cold_cache: bool = False
) -> RunResult:
    config.validate()
    result_dir = resolve_result_dir(result_dir)
    if result_dir.exists() and any(result_dir.iterdir()):
        raise ValueError("result directory must be empty")
    result_dir.mkdir(parents=True, exist_ok=True)
    model_manifest = _load_model_manifest(result_dir)
    _assert_model_ready()
    if cold_cache:
        _drop_guest_caches()

    container_name = new_container_name()
    command = build_docker_command(config, result_dir, container_name=container_name)
    timed_out = False
    completed: subprocess.CompletedProcess[str] | None = None
    try:
        completed = _run(command, timeout=config.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _run(
            [
                "docker",
                "--context",
                DOCKER_CONTEXT,
                "stop",
                "--time",
                "10",
                container_name,
            ]
        )

    state = _inspect_container(container_name)
    return_code = completed.returncode if completed is not None else None
    events = _load_memory_events(result_dir)
    outcome = classify_outcome(
        timed_out=timed_out,
        return_code=return_code,
        container_state=state,
        memory_events=events,
    )
    stderr = completed.stderr if completed is not None else "controller timeout"
    _write_controller_result(
        path=result_dir / "controller-result.json",
        config=config,
        container_name=container_name,
        outcome=outcome,
        return_code=return_code,
        timed_out=timed_out,
        state=state,
        stderr=stderr,
        model_manifest=model_manifest,
        cold_cache=cold_cache,
    )
    _remove_owned_container(container_name)
    return RunResult(
        container_name=container_name,
        outcome=outcome,
        return_code=return_code,
        oom_killed=state.get("OOMKilled") is True,
        result_dir=result_dir,
    )


def _parse_environment(values: Sequence[str]) -> dict[str, str]:
    environment: dict[str, str] = {}
    for item in values:
        name, separator, value = item.partition("=")
        if not separator or name in environment:
            raise ValueError(
                f"environment option must be a unique NAME=VALUE pair: {item}"
            )
        environment[name] = value
    return environment


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one no-swap Qwen benchmark inside the dedicated Colima profile."
    )
    parser.add_argument("--memory-gib", type=int, required=True)
    parser.add_argument("--cpus", type=int, required=True)
    parser.add_argument("--pp", type=int, required=True)
    parser.add_argument("--tg", type=int, required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--variant", choices=("baseline", "patched"), required=True)
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--cold-cache", action="store_true")
    parser.add_argument("--result-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        config = RunConfig(
            memory_gib=args.memory_gib,
            cpus=args.cpus,
            pp=args.pp,
            tg=args.tg,
            repetitions=args.repetitions,
            timeout_seconds=args.timeout_seconds,
            variant=args.variant,
            env=_parse_environment(args.env),
        )
        result = run_once(config, args.result_dir, cold_cache=args.cold_cache)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Constrained run failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "container_name": result.container_name,
                "outcome": result.outcome,
                "result_dir": str(result.result_dir),
            },
            sort_keys=True,
        )
    )
    return {"success": 0, "oom": 20, "timeout": 21, "error": 1}[result.outcome]


if __name__ == "__main__":
    raise SystemExit(main())
