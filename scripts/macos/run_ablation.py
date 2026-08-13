#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_UTC_CANONICAL = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\+00:00$"
)
STATE_SCHEMA_VERSION = 2
MODEL_FILENAME = "Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
MODEL_SHA256 = "d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a"
MODEL_SIZE_BYTES = 48410988384
FINALIST_NAMES = frozenset(
    {
        "baseline",
        "patched-control",
        "patched-reclaim",
        "patched-residency",
        "patched-combined",
    }
)
ATTEMPT_OUTCOMES = frozenset(
    {"running", "success", "oom", "timeout", "error", "interrupted"}
)
TERMINAL_OUTCOMES = ATTEMPT_OUTCOMES - {"running"}
PLANNED_WORKLOAD_CONTRACT: dict[str, object] = {
    "seed": 1,
    "seed_source": "implicit_c_rand_default",
    "context_tokens": 80,
    "n_prompt": 64,
    "n_gen": 16,
    "n_depth": 0,
    "threads": 4,
    "no_warmup": True,
    "load_mode": "mmap",
    "offline": True,
}


@dataclass(frozen=True)
class AblationConfig:
    name: str
    variant: str
    env: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


def load_configurations(path: Path) -> list[AblationConfig]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(
        payload.get("configurations"), list
    ):
        raise ValueError("unsupported ablation configuration schema")
    configurations: list[AblationConfig] = []
    for raw in payload["configurations"]:
        if not isinstance(raw, dict):
            raise ValueError("each ablation configuration must be an object")
        name = raw.get("name")
        variant = raw.get("variant")
        environment = raw.get("env")
        if not isinstance(name, str) or NAME_PATTERN.fullmatch(name) is None:
            raise ValueError("ablation configuration name is invalid")
        if variant not in {"baseline", "patched"}:
            raise ValueError(f"invalid variant for {name}")
        if not isinstance(environment, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in environment.items()
        ):
            raise ValueError(f"invalid environment for {name}")
        configurations.append(
            AblationConfig(name=name, variant=variant, env=dict(environment))
        )
    names = [item.name for item in configurations]
    if len(names) != len(set(names)):
        raise ValueError("duplicate ablation configuration name")
    return configurations


def build_schedule(
    configurations: list[AblationConfig], *, rounds: int
) -> list[tuple[int, AblationConfig, str]]:
    if not 1 <= rounds <= 5:
        raise ValueError("rounds must be between 1 and 5")
    return [
        (round_index, configuration, cache)
        for round_index in range(1, rounds + 1)
        for configuration in configurations
        for cache in ("cold", "warm")
    ]


def build_campaign_manifest(
    attempts: list[object], *, planned_workload_contract: Mapping[str, object] = PLANNED_WORKLOAD_CONTRACT
) -> dict[str, object]:
    if dict(planned_workload_contract) != PLANNED_WORKLOAD_CONTRACT:
        raise ValueError("campaign planned workload contract is invalid")
    runs: dict[str, dict[str, object]] = {}
    labels: set[tuple[int, str, str]] = set()
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("campaign attempt must be an object")
        round_index = attempt.get("round")
        configuration = attempt.get("configuration")
        cache = attempt.get("cache")
        outcome = attempt.get("outcome")
        run_id = attempt.get("run_id")
        if isinstance(round_index, bool) or not isinstance(round_index, int) or not 1 <= round_index <= 5:
            raise ValueError("campaign round must be between 1 and 5")
        if configuration not in FINALIST_NAMES or cache not in {"cold", "warm"}:
            raise ValueError("campaign finalist label is invalid")
        if not isinstance(run_id, str) or NAME_PATTERN.fullmatch(run_id) is None:
            raise ValueError("campaign run_id is invalid")
        if outcome not in ATTEMPT_OUTCOMES:
            raise ValueError("campaign outcome is invalid")
        label = (round_index, configuration, cache)
        if label in labels or f"runs/{run_id}" in runs:
            raise ValueError("duplicate campaign run label")
        labels.add(label)
        row: dict[str, object] = {
            "round": round_index,
            "configuration": configuration,
            "cache_state": cache,
            "outcome": outcome,
        }
        image_id = attempt.get("image_id")
        if image_id is not None:
            if not isinstance(image_id, str) or IMAGE_ID_PATTERN.fullmatch(image_id) is None:
                raise ValueError("campaign image_id is invalid")
            row["image_id"] = image_id
        workload_contract = attempt.get("workload_contract")
        if workload_contract is not None:
            if not isinstance(workload_contract, dict):
                raise ValueError("campaign workload_contract is invalid")
            row["workload_contract"] = dict(workload_contract)
        runs[f"runs/{run_id}"] = row
    return {
        "schema_version": 1,
        "seed": PLANNED_WORKLOAD_CONTRACT["seed"],
        "seed_source": PLANNED_WORKLOAD_CONTRACT["seed_source"],
        "context_tokens": PLANNED_WORKLOAD_CONTRACT["context_tokens"],
        "benchmark_contract": {
            key: value
            for key, value in PLANNED_WORKLOAD_CONTRACT.items()
            if key not in {"seed", "seed_source", "context_tokens"}
        },
        "runs": dict(sorted(runs.items())),
    }


def _load_controller() -> Any:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import run_constrained

    return run_constrained


def _remaining_seconds(campaign_state: Path) -> int:
    payload = json.loads(campaign_state.read_text(encoding="utf-8"))
    deadline = datetime.fromisoformat(payload["deadline_at"])
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise ValueError("campaign deadline must be timezone-aware")
    return max(0, int((deadline - datetime.now(timezone.utc)).total_seconds()))


def _save_state(path: Path, state: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    temporary.write_text(
        json.dumps(dict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _write_campaign_projection(path: Path, state: Mapping[str, object]) -> None:
    attempts = state.get("attempts")
    planned = state.get("planned_workload_contract")
    if not isinstance(attempts, list) or not isinstance(planned, dict):
        raise ValueError("ablation state cannot produce a campaign projection")
    _save_state(
        path,
        build_campaign_manifest(attempts, planned_workload_contract=planned),
    )


def _persist_state_and_projection(
    *, state_path: Path, campaign_path: Path, state: Mapping[str, object]
) -> None:
    _save_state(state_path, state)
    _write_campaign_projection(campaign_path, state)


def _load_planned_model(result_root: Path) -> dict[str, object]:
    path = result_root / "model-manifest.json"
    if not path.is_file():
        raise ValueError("verified model manifest is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verified model manifest is invalid")
    planned = {
        "expected_sha256": payload.get("expected_sha256"),
        "actual_sha256": payload.get("actual_sha256"),
        "filename": payload.get("filename"),
        "size": payload.get("size"),
    }
    if planned != {
        "expected_sha256": MODEL_SHA256,
        "actual_sha256": MODEL_SHA256,
        "filename": MODEL_FILENAME,
        "size": MODEL_SIZE_BYTES,
    }:
        raise ValueError("verified model manifest does not match the pinned model")
    return planned


def _new_state(result_root: Path) -> dict[str, object]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "planned_workload_contract": dict(PLANNED_WORKLOAD_CONTRACT),
        "planned_model": _load_planned_model(result_root),
        "attempts": [],
        "stop_reason": None,
    }


def _load_state(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != STATE_SCHEMA_VERSION
        or not isinstance(payload.get("attempts"), list)
        or payload.get("planned_workload_contract") != PLANNED_WORKLOAD_CONTRACT
        or payload.get("planned_model")
        != {
            "expected_sha256": MODEL_SHA256,
            "actual_sha256": MODEL_SHA256,
            "filename": MODEL_FILENAME,
            "size": MODEL_SIZE_BYTES,
        }
    ):
        raise ValueError("invalid ablation state")
    return payload


def _load_stable_memory(result_root: Path) -> int:
    payload = json.loads(
        (result_root / "matrix-state.json").read_text(encoding="utf-8")
    )
    value = payload.get("lowest_stable_gib")
    if not isinstance(value, int) or not 2 <= value <= 16:
        raise ValueError("matrix state does not contain a valid lowest stable tier")
    return value


def _expected_attempt_config(attempt: Mapping[str, object]) -> dict[str, object]:
    config = attempt.get("expected_config")
    if not isinstance(config, dict):
        raise ValueError("attempt expected_config is missing")
    required = {
        "memory_gib",
        "cpus",
        "pp",
        "tg",
        "repetitions",
        "timeout_seconds",
        "variant",
        "env",
    }
    if set(config) != required:
        raise ValueError("attempt expected_config is invalid")
    if (
        any(isinstance(config[key], bool) or not isinstance(config[key], int) or config[key] <= 0 for key in required - {"variant", "env"})
        or config["variant"] not in {"baseline", "patched"}
        or not isinstance(config["env"], dict)
        or not all(isinstance(key, str) and isinstance(value, str) for key, value in config["env"].items())
    ):
        raise ValueError("attempt expected_config is invalid")
    return dict(config)


def _validate_model(model: object, planned_model: Mapping[str, object]) -> None:
    if not isinstance(model, dict):
        raise ValueError("controller model provenance is invalid")
    identity = {
        "expected_sha256": model.get("expected_sha256"),
        "actual_sha256": model.get("actual_sha256"),
        "filename": model.get("filename"),
        "size": model.get("size"),
    }
    if identity != dict(planned_model):
        raise ValueError("controller model provenance is invalid")


def _is_canonical_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or RFC3339_UTC_CANONICAL.fullmatch(value) is None:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo == timezone.utc
    except ValueError:
        return False


def _validate_success_wrapper(
    *, run_dir: Path, controller: Mapping[str, object], expected_config: Mapping[str, object]
) -> None:
    manifest_path = run_dir / "run-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("successful controller result requires a wrapper manifest")
    wrapper = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(wrapper, dict) or wrapper.get("schema_version") != 1:
        raise ValueError("wrapper manifest is invalid")
    if (
        wrapper.get("outcome") != "success"
        or wrapper.get("variant") != expected_config["variant"]
        or wrapper.get("environment") != expected_config["env"]
        or wrapper.get("image_id") != controller["image_id"]
        or wrapper.get("pp") != expected_config["pp"]
        or wrapper.get("tg") != expected_config["tg"]
        or wrapper.get("threads") != expected_config["cpus"]
        or wrapper.get("repetitions") != expected_config["repetitions"]
        or wrapper.get("memory_limit_bytes") != expected_config["memory_gib"] * 1024**3
        or wrapper.get("memory_swap_limit_bytes") != 0
        or wrapper.get("llama_commit") != "360e134"
        or wrapper.get("workload_contract") != PLANNED_WORKLOAD_CONTRACT
    ):
        raise ValueError("wrapper manifest does not match controller identity")


def _load_controller_outcome(
    run_dir: Path, attempt: Mapping[str, object], planned_model: Mapping[str, object]
) -> dict[str, object] | None:
    result_path = run_dir / "controller-result.json"
    if not result_path.is_file():
        return None
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("controller result must be an object")
    expected_config = _expected_attempt_config(attempt)
    run_id = attempt.get("run_id")
    outcome = payload.get("outcome")
    image_id = payload.get("image_id")
    workload_contract = payload.get("workload_contract")
    created_at = payload.get("created_at")
    if (
        payload.get("schema_version") != 1
        or not _is_canonical_utc_timestamp(created_at)
        or payload.get("run_id") != run_id
        or payload.get("config") != expected_config
        or payload.get("cold_cache") != (attempt.get("cache") == "cold")
        or payload.get("memory_limit_bytes") != expected_config["memory_gib"] * 1024**3
        or payload.get("memory_swap_limit_bytes") != 0
        or payload.get("llama_commit") != "360e134"
        or not isinstance(payload.get("container_state"), dict)
        or not isinstance(payload.get("timed_out"), bool)
        or not isinstance(payload.get("container_name"), str)
        or not payload["container_name"]
        or (
            payload.get("return_code") is not None
            and (isinstance(payload["return_code"], bool) or not isinstance(payload["return_code"], int))
        )
        or not isinstance(payload.get("stderr_summary"), str)
    ):
        raise ValueError("controller result identity does not match the attempt")
    _validate_model(payload.get("model"), planned_model)
    if outcome not in TERMINAL_OUTCOMES:
        raise ValueError("controller result outcome is invalid")
    if not isinstance(image_id, str) or IMAGE_ID_PATTERN.fullmatch(image_id) is None:
        raise ValueError("controller result image_id is invalid")
    if workload_contract is not None and workload_contract != PLANNED_WORKLOAD_CONTRACT:
        raise ValueError("controller result workload contract diverges from campaign plan")
    if outcome == "success":
        if workload_contract != PLANNED_WORKLOAD_CONTRACT:
            raise ValueError("successful controller result requires a complete workload contract")
        _validate_success_wrapper(
            run_dir=run_dir, controller=payload, expected_config=expected_config
        )
    return {
        "outcome": outcome,
        "image_id": image_id,
        "workload_contract": dict(workload_contract)
        if isinstance(workload_contract, dict)
        else None,
    }


def _reconcile_running_attempts(
    *, state: dict[str, object], result_root: Path
) -> bool:
    attempts = state["attempts"]
    assert isinstance(attempts, list)
    for attempt in attempts:
        if not isinstance(attempt, dict) or attempt.get("outcome") != "running":
            continue
        run_id = attempt.get("run_id")
        if not isinstance(run_id, str) or NAME_PATTERN.fullmatch(run_id) is None:
            raise ValueError("running attempt run_id is invalid")
        planned_model = state.get("planned_model")
        if not isinstance(planned_model, dict):
            raise ValueError("ablation state planned_model is invalid")
        recovered = _load_controller_outcome(
            result_root / "runs" / run_id, attempt, planned_model
        )
        if recovered is None:
            attempt["outcome"] = "interrupted"
            state["stop_reason"] = "interrupted_run"
            return False
        attempt.update(recovered)
    return True


def execute_ablation(
    *, campaign_state: Path, result_root: Path, config_path: Path, rounds: int = 1
) -> dict[str, object]:
    result_root = result_root.resolve()
    state_path = result_root / "ablation-state.json"
    state: dict[str, object]
    state = _load_state(state_path) if state_path.exists() else _new_state(result_root)
    attempts = state["attempts"]
    assert isinstance(attempts, list)
    campaign_path = result_root / "campaign-manifest.json"
    _write_campaign_projection(campaign_path, state)
    if not _reconcile_running_attempts(state=state, result_root=result_root):
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_state_and_projection(
            state_path=state_path, campaign_path=campaign_path, state=state
        )
        return state
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _persist_state_and_projection(
        state_path=state_path, campaign_path=campaign_path, state=state
    )
    completed = {
        (item.get("round", 1), item.get("configuration"), item.get("cache"))
        for item in attempts
        if isinstance(item, dict)
    }
    memory_gib = _load_stable_memory(result_root)
    controller = _load_controller()

    schedule = build_schedule(load_configurations(config_path), rounds=rounds)
    for round_index, configuration, cache in schedule:
        if (round_index, configuration.name, cache) in completed:
            continue
        remaining = _remaining_seconds(campaign_state)
        if remaining < 60:
            state["stop_reason"] = "campaign_deadline"
            _persist_state_and_projection(
                state_path=state_path, campaign_path=campaign_path, state=state
            )
            return state
        timeout = min(5400, remaining - 30)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
        run_id = (
            f"ablation-r{round_index}-{configuration.name}-{cache}-"
            f"{timestamp}-{secrets.token_hex(3)}"
        )
        config = controller.RunConfig(
            memory_gib=memory_gib,
            cpus=4,
            pp=64,
            tg=16,
            repetitions=1,
            timeout_seconds=timeout,
            variant=configuration.variant,
            env=configuration.env,
        )
        attempt: dict[str, object] = {
            "round": round_index,
            "configuration": configuration.name,
            "cache": cache,
            "outcome": "running",
            "run_id": run_id,
            "expected_config": {
                "memory_gib": memory_gib,
                "cpus": 4,
                "pp": 64,
                "tg": 16,
                "repetitions": 1,
                "timeout_seconds": timeout,
                "variant": configuration.variant,
                "env": dict(configuration.env),
            },
        }
        attempts.append(attempt)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_state_and_projection(
            state_path=state_path, campaign_path=campaign_path, state=state
        )
        result = controller.run_once(
            config, result_root / "runs" / run_id, cold_cache=cache == "cold"
        )
        if result.outcome not in TERMINAL_OUTCOMES:
            raise ValueError("controller returned an invalid ablation outcome")
        attempt["outcome"] = result.outcome
        planned_model = state.get("planned_model")
        if not isinstance(planned_model, dict):
            raise ValueError("ablation state planned_model is invalid")
        recovered = _load_controller_outcome(
            result_root / "runs" / run_id, attempt, planned_model
        )
        if recovered is not None:
            attempt.update(recovered)
        else:
            image_id = getattr(result, "image_id", None)
            if not isinstance(image_id, str) or IMAGE_ID_PATTERN.fullmatch(image_id) is None:
                raise ValueError("controller did not record an immutable image identity")
            attempt["image_id"] = image_id
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_state_and_projection(
            state_path=state_path, campaign_path=campaign_path, state=state
        )
        if result.outcome == "timeout":
            state["stop_reason"] = "run_timeout"
            _persist_state_and_projection(
                state_path=state_path, campaign_path=campaign_path, state=state
            )
            return state
    state["stop_reason"] = "ablation_complete"
    _persist_state_and_projection(
        state_path=state_path, campaign_path=campaign_path, state=state
    )
    return state


def _build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Run the fixed current-code SLIM-ARC ablation order."
    )
    parser.add_argument("--campaign-state", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=script_dir / "configs" / "current-ablation.json"
    )
    parser.add_argument("--rounds", type=int, default=1)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        state = execute_ablation(
            campaign_state=args.campaign_state,
            result_root=args.result_root,
            config_path=args.config,
            rounds=args.rounds,
        )
    except (OSError, ValueError) as exc:
        print(f"Ablation execution failed: {exc}", file=sys.stderr)
        return 1
    attempts = state.get("attempts")
    attempt_count = len(attempts) if isinstance(attempts, list) else 0
    print(
        json.dumps(
            {"attempts": attempt_count, "stop_reason": state.get("stop_reason")},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
