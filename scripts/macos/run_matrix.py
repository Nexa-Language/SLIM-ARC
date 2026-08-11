#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
PRIMARY_SURVIVAL_TIERS = (12, 8, 6, 4)
LOW_SURVIVAL_TIERS = (3, 2)
CPU_TIERS = (2, 4, 6, 8)


@dataclass
class MatrixState:
    attempts: list[dict[str, object]] = field(default_factory=list)
    stable_attempts: list[dict[str, object]] = field(default_factory=list)
    cpu_attempts: list[dict[str, object]] = field(default_factory=list)
    lowest_stable_gib: int | None = None
    stop_reason: str | None = None

    def record_survival(self, *, memory_gib: int, outcome: str, run_id: str) -> None:
        if memory_gib not in {*PRIMARY_SURVIVAL_TIERS, *LOW_SURVIVAL_TIERS, 5}:
            raise ValueError(f"unsupported survival tier: {memory_gib}")
        if outcome not in {"success", "oom", "timeout", "error"}:
            raise ValueError(f"unsupported run outcome: {outcome}")
        self.attempts.append(
            {"memory_gib": memory_gib, "outcome": outcome, "run_id": run_id}
        )

    def _outcomes(self, memory_gib: int) -> list[str]:
        return [
            str(item["outcome"])
            for item in self.attempts
            if item.get("memory_gib") == memory_gib
        ]

    def _decision(self, memory_gib: int) -> str | None:
        outcomes = self._outcomes(memory_gib)
        if outcomes.count("success") >= 2:
            return "success"
        if outcomes.count("oom") >= 2:
            return "oom"
        if "timeout" in outcomes:
            return "timeout"
        if "error" in outcomes:
            return "error"
        return None

    @property
    def lowest_survival_gib(self) -> int | None:
        successful = [
            tier
            for tier in {*PRIMARY_SURVIVAL_TIERS, *LOW_SURVIVAL_TIERS, 5}
            if self._decision(tier) == "success"
        ]
        return min(successful, default=None)

    def next_survival_tier(self) -> int | None:
        for tier in PRIMARY_SURVIVAL_TIERS[:-1]:
            decision = self._decision(tier)
            if decision is None:
                return tier
            if decision != "success":
                return None

        four_decision = self._decision(4)
        if four_decision is None:
            return 4
        if four_decision == "oom":
            return 5 if self._decision(5) is None else None
        if four_decision != "success":
            return None

        for tier in LOW_SURVIVAL_TIERS:
            decision = self._decision(tier)
            if decision is None:
                return tier
            if decision != "success":
                return None
        return None

    def save(self, path: Path) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "attempts": self.attempts,
            "stable_attempts": self.stable_attempts,
            "cpu_attempts": self.cpu_attempts,
            "lowest_survival_gib": self.lowest_survival_gib,
            "lowest_stable_gib": self.lowest_stable_gib,
            "stop_reason": self.stop_reason,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> MatrixState:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported matrix state schema")
        for name in ("attempts", "stable_attempts", "cpu_attempts"):
            if not isinstance(payload.get(name), list):
                raise ValueError(f"matrix state {name} must be a list")
        lowest_stable = payload.get("lowest_stable_gib")
        if lowest_stable is not None and not isinstance(lowest_stable, int):
            raise ValueError("lowest_stable_gib must be an integer or null")
        stop_reason = payload.get("stop_reason")
        if stop_reason is not None and not isinstance(stop_reason, str):
            raise ValueError("stop_reason must be a string or null")
        return cls(
            attempts=list(payload["attempts"]),
            stable_attempts=list(payload["stable_attempts"]),
            cpu_attempts=list(payload["cpu_attempts"]),
            lowest_stable_gib=lowest_stable,
            stop_reason=stop_reason,
        )


def _remaining_seconds(campaign_state: Path) -> int:
    payload = json.loads(campaign_state.read_text(encoding="utf-8"))
    deadline = datetime.fromisoformat(payload["deadline_at"])
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise ValueError("campaign deadline must be timezone-aware")
    return max(0, int((deadline - datetime.now(timezone.utc)).total_seconds()))


def _load_controller() -> Any:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import run_constrained

    return run_constrained


def _run_id(phase: str, detail: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    return f"{phase}-{detail}-{timestamp}-{secrets.token_hex(3)}"


def _bounded_timeout(campaign_state: Path, maximum: int) -> int | None:
    remaining = _remaining_seconds(campaign_state)
    if remaining < 60:
        return None
    return min(maximum, remaining - 30)


def _run_survival(
    state: MatrixState, state_path: Path, result_root: Path, campaign_state: Path
) -> None:
    controller = _load_controller()
    while (tier := state.next_survival_tier()) is not None:
        timeout = _bounded_timeout(campaign_state, 1800)
        if timeout is None:
            state.stop_reason = "campaign_deadline"
            state.save(state_path)
            return
        run_id = _run_id("survival", f"{tier}g")
        config = controller.RunConfig(
            memory_gib=tier,
            cpus=4,
            pp=4,
            tg=1,
            repetitions=1,
            timeout_seconds=timeout,
            variant="patched",
            env={},
        )
        result = controller.run_once(
            config, result_root / "runs" / run_id, cold_cache=True
        )
        state.record_survival(memory_gib=tier, outcome=result.outcome, run_id=run_id)
        state.save(state_path)
        if result.outcome in {"timeout", "error"}:
            state.stop_reason = f"survival_{result.outcome}"
            state.save(state_path)
            return


def _successful_survival_tiers(state: MatrixState) -> list[int]:
    tiers = [
        tier
        for tier in {*PRIMARY_SURVIVAL_TIERS, *LOW_SURVIVAL_TIERS, 5}
        if state._decision(tier) == "success"
    ]
    return sorted(tiers)


def _stable_phase_complete(state: MatrixState, memory_gib: int) -> bool:
    attempts = [
        item for item in state.stable_attempts if item.get("memory_gib") == memory_gib
    ]
    return any(
        item.get("cache") == "cold" and item.get("outcome") == "success"
        for item in attempts
    ) and any(
        item.get("cache") == "warm" and item.get("outcome") == "success"
        for item in attempts
    )


def _run_stable_search(
    state: MatrixState, state_path: Path, result_root: Path, campaign_state: Path
) -> None:
    controller = _load_controller()
    for tier in _successful_survival_tiers(state):
        if _stable_phase_complete(state, tier):
            state.lowest_stable_gib = tier
            state.save(state_path)
            return
        existing = [
            item for item in state.stable_attempts if item.get("memory_gib") == tier
        ]
        for cache in ("cold", "warm"):
            if any(item.get("cache") == cache for item in existing):
                continue
            timeout = _bounded_timeout(campaign_state, 5400)
            if timeout is None:
                state.stop_reason = "campaign_deadline"
                state.save(state_path)
                return
            run_id = _run_id("stable", f"{tier}g-{cache}")
            config = controller.RunConfig(
                memory_gib=tier,
                cpus=4,
                pp=64,
                tg=16,
                repetitions=1,
                timeout_seconds=timeout,
                variant="patched",
                env={},
            )
            result = controller.run_once(
                config, result_root / "runs" / run_id, cold_cache=cache == "cold"
            )
            state.stable_attempts.append(
                {
                    "memory_gib": tier,
                    "cache": cache,
                    "outcome": result.outcome,
                    "run_id": run_id,
                }
            )
            state.save(state_path)
            if result.outcome != "success":
                break
        if _stable_phase_complete(state, tier):
            state.lowest_stable_gib = tier
            state.save(state_path)
            return
    state.stop_reason = state.stop_reason or "no_stable_tier"
    state.save(state_path)


def _run_cpu_matrix(
    state: MatrixState, state_path: Path, result_root: Path, campaign_state: Path
) -> None:
    if state.lowest_stable_gib is None:
        return
    controller = _load_controller()
    completed = {
        value
        for item in state.cpu_attempts
        if isinstance((value := item.get("cpus")), int)
    }
    for cpus in CPU_TIERS:
        if cpus in completed:
            continue
        timeout = _bounded_timeout(campaign_state, 5400)
        if timeout is None:
            state.stop_reason = "campaign_deadline"
            state.save(state_path)
            return
        run_id = _run_id("cpu", f"{cpus}c")
        config = controller.RunConfig(
            memory_gib=state.lowest_stable_gib,
            cpus=cpus,
            pp=64,
            tg=16,
            repetitions=2,
            timeout_seconds=timeout,
            variant="patched",
            env={},
        )
        result = controller.run_once(
            config, result_root / "runs" / run_id, cold_cache=True
        )
        state.cpu_attempts.append(
            {"cpus": cpus, "outcome": result.outcome, "run_id": run_id}
        )
        state.save(state_path)
        if result.outcome in {"timeout", "error"}:
            state.stop_reason = f"cpu_{result.outcome}"
            state.save(state_path)
            return
    state.stop_reason = "matrix_complete"
    state.save(state_path)


def execute_matrix(
    *, campaign_state: Path, result_root: Path, rerun: bool
) -> MatrixState:
    result_root = result_root.resolve()
    state_path = result_root / "matrix-state.json"
    if rerun and state_path.exists():
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
        state_path = result_root / f"matrix-state-rerun-{suffix}.json"
    state = MatrixState.load(state_path) if state_path.exists() else MatrixState()
    _run_survival(state, state_path, result_root, campaign_state)
    if state.stop_reason is not None:
        return state
    _run_stable_search(state, state_path, result_root, campaign_state)
    if state.stop_reason in {"campaign_deadline", "no_stable_tier"}:
        return state
    _run_cpu_matrix(state, state_path, result_root, campaign_state)
    return state


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the resumable SLIM-ARC memory and CPU benchmark matrix."
    )
    parser.add_argument("--campaign-state", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--rerun", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        state = execute_matrix(
            campaign_state=args.campaign_state,
            result_root=args.result_root,
            rerun=args.rerun,
        )
    except (OSError, ValueError) as exc:
        print(f"Matrix execution failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "lowest_survival_gib": state.lowest_survival_gib,
                "lowest_stable_gib": state.lowest_stable_gib,
                "stop_reason": state.stop_reason,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
