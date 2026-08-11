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


def _load_stable_memory(result_root: Path) -> int:
    payload = json.loads(
        (result_root / "matrix-state.json").read_text(encoding="utf-8")
    )
    value = payload.get("lowest_stable_gib")
    if not isinstance(value, int) or not 2 <= value <= 16:
        raise ValueError("matrix state does not contain a valid lowest stable tier")
    return value


def execute_ablation(
    *, campaign_state: Path, result_root: Path, config_path: Path
) -> dict[str, object]:
    result_root = result_root.resolve()
    state_path = result_root / "ablation-state.json"
    state: dict[str, object]
    if state_path.exists():
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if (
            not isinstance(loaded, dict)
            or loaded.get("schema_version") != 1
            or not isinstance(loaded.get("attempts"), list)
        ):
            raise ValueError("invalid ablation state")
        state = loaded
    else:
        state = {"schema_version": 1, "attempts": [], "stop_reason": None}
    attempts = state["attempts"]
    assert isinstance(attempts, list)
    completed = {
        (item.get("configuration"), item.get("cache"))
        for item in attempts
        if isinstance(item, dict)
    }
    memory_gib = _load_stable_memory(result_root)
    controller = _load_controller()

    for configuration in load_configurations(config_path):
        for cache in ("cold", "warm"):
            if (configuration.name, cache) in completed:
                continue
            remaining = _remaining_seconds(campaign_state)
            if remaining < 60:
                state["stop_reason"] = "campaign_deadline"
                _save_state(state_path, state)
                return state
            timeout = min(5400, remaining - 30)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
            run_id = f"ablation-{configuration.name}-{cache}-{timestamp}-{secrets.token_hex(3)}"
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
            result = controller.run_once(
                config, result_root / "runs" / run_id, cold_cache=cache == "cold"
            )
            attempts.append(
                {
                    "configuration": configuration.name,
                    "cache": cache,
                    "outcome": result.outcome,
                    "run_id": run_id,
                }
            )
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_state(state_path, state)
            if result.outcome == "timeout":
                state["stop_reason"] = "run_timeout"
                _save_state(state_path, state)
                return state
    state["stop_reason"] = "ablation_complete"
    _save_state(state_path, state)
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
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        state = execute_ablation(
            campaign_state=args.campaign_state,
            result_root=args.result_root,
            config_path=args.config,
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
