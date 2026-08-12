from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "run_ablation.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_run_ablation", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
run_ablation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_ablation
SPEC.loader.exec_module(run_ablation)

CONTROLLER = run_ablation._load_controller()
MODEL_IDENTITY = {
    "expected_sha256": "d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a",
    "actual_sha256": "d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a",
    "filename": "Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf",
    "size": 48410988384,
}


def test_loads_fixed_finalist_configuration_order() -> None:
    config_path = (
        Path(__file__).parents[2]
        / "scripts"
        / "macos"
        / "configs"
        / "current-ablation.json"
    )

    configurations = run_ablation.load_configurations(config_path)

    assert [item.name for item in configurations] == [
        "baseline",
        "patched-control",
        "patched-reclaim",
        "patched-residency",
        "patched-combined",
    ]
    assert [dict(item.env) for item in configurations] == [
        {},
        {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1"},
        {
            "SLIM_ARC_DECODE_MADV": "SEQUENTIAL",
            "SLIM_ARC_DYNAMIC_MADV": "1",
            "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1",
        },
        {
            "SLIM_ARC_DECODE_MADV": "SEQUENTIAL",
            "SLIM_ARC_DYNAMIC_MADV": "1",
            "SLIM_ARC_EXPERT_RESIDENCY": "1",
        },
        {
            "SLIM_ARC_DECODE_MADV": "SEQUENTIAL",
            "SLIM_ARC_DYNAMIC_MADV": "1",
            "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1",
            "SLIM_ARC_EXPERT_RESIDENCY": "1",
        },
    ]


def test_builds_symmetric_round_schedule() -> None:
    configurations = [
        run_ablation.AblationConfig(name="baseline", variant="baseline", env={}),
        run_ablation.AblationConfig(name="patched", variant="patched", env={}),
    ]

    schedule = run_ablation.build_schedule(configurations, rounds=2)

    assert [
        (round_index, configuration.name, cache)
        for round_index, configuration, cache in schedule
    ] == [
        (1, "baseline", "cold"),
        (1, "baseline", "warm"),
        (1, "patched", "cold"),
        (1, "patched", "warm"),
        (2, "baseline", "cold"),
        (2, "baseline", "warm"),
        (2, "patched", "cold"),
        (2, "patched", "warm"),
    ]


@pytest.mark.parametrize("rounds", [0, 6])
def test_rejects_unbounded_round_count(rounds: int) -> None:
    with pytest.raises(ValueError, match="rounds"):
        run_ablation.build_schedule([], rounds=rounds)


def test_builds_campaign_manifest_from_recorded_attempts() -> None:
    manifest = run_ablation.build_campaign_manifest(
        [
            {
                "round": 2,
                "configuration": "patched-control",
                "cache": "warm",
                "outcome": "success",
                "run_id": "ablation-r2-patched-control-warm-run",
            },
            {
                "round": 1,
                "configuration": "baseline",
                "cache": "cold",
                "outcome": "success",
                "run_id": "ablation-r1-baseline-cold-run",
            },
        ]
    )

    assert manifest == {
        "schema_version": 1,
        "seed": 1,
        "seed_source": "implicit_c_rand_default",
        "context_tokens": 80,
        "benchmark_contract": {
            "n_prompt": 64,
            "n_gen": 16,
            "n_depth": 0,
            "threads": 4,
            "no_warmup": True,
            "load_mode": "mmap",
            "offline": True,
        },
        "runs": {
            "runs/ablation-r1-baseline-cold-run": {
                "round": 1,
                "configuration": "baseline",
                "cache_state": "cold",
                "outcome": "success",
            },
            "runs/ablation-r2-patched-control-warm-run": {
                "round": 2,
                "configuration": "patched-control",
                "cache_state": "warm",
                "outcome": "success",
            },
        },
    }


def test_campaign_manifest_rejects_duplicate_labels_and_unsafe_run_ids() -> None:
    duplicate = {
        "round": 1,
        "configuration": "baseline",
        "cache": "cold",
        "outcome": "success",
        "run_id": "valid-run",
    }
    with pytest.raises(ValueError, match="duplicate"):
        run_ablation.build_campaign_manifest([duplicate, dict(duplicate)])
    with pytest.raises(ValueError, match="run_id"):
        run_ablation.build_campaign_manifest([{**duplicate, "run_id": "../escape"}])


def test_rejects_duplicate_configuration_names(tmp_path: Path) -> None:
    config_path = tmp_path / "duplicate.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "configurations": [
                    {"name": "duplicate", "variant": "baseline", "env": {}},
                    {"name": "duplicate", "variant": "patched", "env": {}},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        run_ablation.load_configurations(config_path)


def _write_campaign_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    result_root = tmp_path / "results"
    result_root.mkdir()
    (result_root / "matrix-state.json").write_text(
        json.dumps({"lowest_stable_gib": 2}), encoding="utf-8"
    )
    (result_root / "model-manifest.json").write_text(
        json.dumps(MODEL_IDENTITY), encoding="utf-8"
    )
    campaign_state = tmp_path / "campaign-state.json"
    campaign_state.write_text(
        json.dumps(
            {"deadline_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "ablation.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "configurations": [{"name": "baseline", "variant": "baseline", "env": {}}],
            }
        ),
        encoding="utf-8",
    )
    return campaign_state, result_root, config_path


def _attempt(run_id: str, *, cache: str = "cold", outcome: str = "running", timeout: int = 3600) -> dict[str, object]:
    return {
        "round": 1,
        "configuration": "baseline",
        "cache": cache,
        "outcome": outcome,
        "run_id": run_id,
        "expected_config": {
            "memory_gib": 2,
            "cpus": 4,
            "pp": 64,
            "tg": 16,
            "repetitions": 1,
            "timeout_seconds": timeout,
            "variant": "baseline",
            "env": {},
        },
    }


def _state(attempts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": run_ablation.STATE_SCHEMA_VERSION,
        "planned_workload_contract": dict(run_ablation.PLANNED_WORKLOAD_CONTRACT),
        "planned_model": dict(MODEL_IDENTITY),
        "attempts": attempts,
        "stop_reason": None,
    }


def _controller_result(path: Path, attempt: dict[str, object], *, outcome: str = "success", workload_contract: object = run_ablation.PLANNED_WORKLOAD_CONTRACT) -> None:
    config = attempt["expected_config"]
    assert isinstance(config, dict)
    path.parent.mkdir(parents=True, exist_ok=True)
    controller_config = CONTROLLER.RunConfig(**config)
    CONTROLLER._write_controller_result(
        path=path,
        run_id=str(attempt["run_id"]),
        config=controller_config,
        container_name="slim-arc-run-test",
        outcome=outcome,
        return_code=0 if outcome == "success" else 137,
        timed_out=outcome == "timeout",
        state={"OOMKilled": outcome == "oom", "ExitCode": 0 if outcome == "success" else 137},
        stderr="",
        model_manifest=MODEL_IDENTITY,
        cold_cache=attempt["cache"] == "cold",
        image_id="sha256:" + "a" * 64,
        workload_contract=workload_contract if isinstance(workload_contract, dict) else None,
    )


def _wrapper_manifest(path: Path, attempt: dict[str, object]) -> None:
    config = attempt["expected_config"]
    assert isinstance(config, dict)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "outcome": "success",
                "variant": "baseline",
                "environment": {},
                "image_id": "sha256:" + "a" * 64,
                "pp": 64,
                "tg": 16,
                "threads": 4,
                "repetitions": 1,
                "memory_limit_bytes": 2 * 1024**3,
                "memory_swap_limit_bytes": 0,
                "llama_commit": "360e134",
                "workload_contract": run_ablation.PLANNED_WORKLOAD_CONTRACT,
            }
        ),
        encoding="utf-8",
    )


def test_pre_registers_running_attempt_before_invoking_controller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)

    class Controller:
        RunConfig = lambda **kwargs: SimpleNamespace(**kwargs)

        @staticmethod
        def run_once(config: object, run_dir: Path, *, cold_cache: bool) -> object:
            state = json.loads((result_root / "ablation-state.json").read_text(encoding="utf-8"))
            campaign = json.loads((result_root / "campaign-manifest.json").read_text(encoding="utf-8"))
            assert state["planned_workload_contract"] == run_ablation.PLANNED_WORKLOAD_CONTRACT
            assert state["attempts"][0]["outcome"] == "running"
            assert state["attempts"][0]["run_id"] == run_dir.name
            assert state["attempts"][0]["expected_config"]["pp"] == 64
            assert campaign["runs"][f"runs/{run_dir.name}"]["outcome"] == "running"
            raise KeyboardInterrupt

    monkeypatch.setattr(run_ablation, "_load_controller", lambda: Controller)

    with pytest.raises(KeyboardInterrupt):
        run_ablation.execute_ablation(
            campaign_state=campaign_state, result_root=result_root, config_path=config_path
        )

    state = json.loads((result_root / "ablation-state.json").read_text(encoding="utf-8"))
    assert state["attempts"][0]["outcome"] == "running"


def test_resume_recovers_recorded_controller_outcome_without_duplicate_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    run_id = "ablation-r1-baseline-cold-existing"
    recovered_attempt = _attempt(run_id)
    _controller_result(result_root / "runs" / run_id / "controller-result.json", recovered_attempt)
    _wrapper_manifest(result_root / "runs" / run_id / "run-manifest.json", recovered_attempt)
    (result_root / "ablation-state.json").write_text(
        json.dumps(_state([recovered_attempt])),
        encoding="utf-8",
    )

    class Controller:
        RunConfig = lambda **kwargs: SimpleNamespace(**kwargs)

        @staticmethod
        def run_once(config: object, run_dir: Path, *, cold_cache: bool) -> object:
            assert run_dir.name != run_id
            next_attempt = _attempt(run_dir.name, cache="warm", timeout=config.timeout_seconds)
            _controller_result(run_dir / "controller-result.json", next_attempt)
            _wrapper_manifest(run_dir / "run-manifest.json", next_attempt)
            return SimpleNamespace(outcome="success", image_id="sha256:" + "a" * 64)

    monkeypatch.setattr(run_ablation, "_load_controller", lambda: Controller)

    state = run_ablation.execute_ablation(
        campaign_state=campaign_state, result_root=result_root, config_path=config_path
    )

    assert state["attempts"][0]["outcome"] == "success"
    assert state["attempts"][0]["run_id"] == run_id
    assert len(state["attempts"]) == 2


def test_resume_marks_missing_running_attempt_interrupted_and_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    (result_root / "ablation-state.json").write_text(
        json.dumps(_state([_attempt("ablation-r1-baseline-cold-lost")])),
        encoding="utf-8",
    )

    monkeypatch.setattr(run_ablation, "_load_controller", lambda: None)

    state = run_ablation.execute_ablation(
        campaign_state=campaign_state, result_root=result_root, config_path=config_path
    )

    assert state["stop_reason"] == "interrupted_run"
    assert state["attempts"][0]["outcome"] == "interrupted"


def test_recovery_rejects_actual_contract_that_diverges_from_campaign_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    run_id = "ablation-r1-baseline-cold-drift"
    result_path = result_root / "runs" / run_id / "controller-result.json"
    drift_attempt = _attempt(run_id)
    _controller_result(result_path, drift_attempt)
    _wrapper_manifest(result_root / "runs" / run_id / "run-manifest.json", drift_attempt)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["workload_contract"]["n_depth"] = 1
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    (result_root / "ablation-state.json").write_text(
        json.dumps(_state([drift_attempt])),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_ablation, "_load_controller", lambda: None)

    with pytest.raises(ValueError, match="diverges"):
        run_ablation.execute_ablation(
            campaign_state=campaign_state, result_root=result_root, config_path=config_path
        )


@pytest.mark.parametrize("outcome", ["oom", "timeout", "error"])
def test_resume_preserves_terminal_failure_without_wrapper_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    run_id = f"ablation-r1-baseline-cold-{outcome}"
    oom_attempt = _attempt(run_id)
    _controller_result(
        result_root / "runs" / run_id / "controller-result.json",
        oom_attempt,
        outcome=outcome,
        workload_contract=None,
    )
    controller_path = result_root / "runs" / run_id / "controller-result.json"
    payload = json.loads(controller_path.read_text(encoding="utf-8"))
    payload["workload_contract"] = None
    controller_path.write_text(json.dumps(payload), encoding="utf-8")
    (result_root / "ablation-state.json").write_text(
        json.dumps(_state([oom_attempt])),
        encoding="utf-8",
    )

    class Controller:
        RunConfig = lambda **kwargs: SimpleNamespace(**kwargs)

        @staticmethod
        def run_once(config: object, run_dir: Path, *, cold_cache: bool) -> object:
            assert run_dir.name != run_id
            next_attempt = _attempt(run_dir.name, cache="warm", timeout=config.timeout_seconds)
            _controller_result(run_dir / "controller-result.json", next_attempt)
            _wrapper_manifest(run_dir / "run-manifest.json", next_attempt)
            return SimpleNamespace(outcome="success", image_id="sha256:" + "a" * 64)

    monkeypatch.setattr(run_ablation, "_load_controller", lambda: Controller)
    state = run_ablation.execute_ablation(campaign_state=campaign_state, result_root=result_root, config_path=config_path)

    assert state["attempts"][0]["outcome"] == outcome
    assert state["attempts"][0]["workload_contract"] is None


def test_success_without_wrapper_manifest_is_not_a_valid_recovery(tmp_path: Path) -> None:
    run_id = "ablation-r1-baseline-cold-missing-wrapper"
    attempt = _attempt(run_id)
    _controller_result(tmp_path / run_id / "controller-result.json", attempt)

    with pytest.raises(ValueError, match="wrapper"):
        run_ablation._load_controller_outcome(
            tmp_path / run_id,
            attempt,
            MODEL_IDENTITY,
        )


def test_restart_repairs_projection_after_source_state_commit_without_launching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    original_projection = run_ablation._write_campaign_projection

    def interrupt_after_state_commit(path: Path, state: object) -> None:
        assert isinstance(state, dict)
        attempts = state.get("attempts")
        if isinstance(attempts, list) and attempts:
            raise KeyboardInterrupt
        original_projection(path, state)

    class FirstController:
        RunConfig = lambda **kwargs: SimpleNamespace(**kwargs)

        @staticmethod
        def run_once(*args: object, **kwargs: object) -> object:
            raise AssertionError("controller must not launch before campaign projection")

    monkeypatch.setattr(run_ablation, "_write_campaign_projection", interrupt_after_state_commit)
    monkeypatch.setattr(run_ablation, "_load_controller", lambda: FirstController)
    with pytest.raises(KeyboardInterrupt):
        run_ablation.execute_ablation(campaign_state=campaign_state, result_root=result_root, config_path=config_path)

    persisted = json.loads((result_root / "ablation-state.json").read_text(encoding="utf-8"))
    assert persisted["attempts"][0]["outcome"] == "running"
    stale_projection = json.loads((result_root / "campaign-manifest.json").read_text(encoding="utf-8"))
    assert stale_projection["runs"] == {}

    class RestartController:
        RunConfig = lambda **kwargs: SimpleNamespace(**kwargs)

        @staticmethod
        def run_once(*args: object, **kwargs: object) -> object:
            raise AssertionError("restart must not duplicate an unlaunched attempt")

    monkeypatch.setattr(run_ablation, "_write_campaign_projection", original_projection)
    monkeypatch.setattr(run_ablation, "_load_controller", lambda: RestartController)
    state = run_ablation.execute_ablation(campaign_state=campaign_state, result_root=result_root, config_path=config_path)

    repaired = json.loads((result_root / "campaign-manifest.json").read_text(encoding="utf-8"))
    assert state["stop_reason"] == "interrupted_run"
    assert repaired == run_ablation.build_campaign_manifest(
        state["attempts"], planned_workload_contract=state["planned_workload_contract"]
    )


def test_recovery_rejects_mismatched_controller_identity_without_relaunch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    run_id = "ablation-r1-baseline-cold-foreign"
    attempt = _attempt(run_id)
    result_path = result_root / "runs" / run_id / "controller-result.json"
    _controller_result(result_path, attempt, outcome="oom", workload_contract=None)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["run_id"] = "ablation-r1-baseline-cold-other"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    (result_root / "ablation-state.json").write_text(json.dumps(_state([attempt])), encoding="utf-8")

    monkeypatch.setattr(run_ablation, "_load_controller", lambda: None)
    with pytest.raises(ValueError, match="identity"):
        run_ablation.execute_ablation(campaign_state=campaign_state, result_root=result_root, config_path=config_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("created_at", None),
        ("created_at", "2026-08-12T12:00:00+00:00"),
        ("created_at", "2026-08-12T12:00:00Z"),
        ("created_at", "2026-08-12T12:00:00.000000+08:00"),
        ("model.filename", "foreign.gguf"),
        ("model.actual_sha256", "a" * 64),
        ("model.size", 1),
    ],
)
def test_recovery_rejects_writer_artifact_identity_mutations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, value: object
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    run_id = "ablation-r1-baseline-cold-model-mutation"
    attempt = _attempt(run_id)
    result_path = result_root / "runs" / run_id / "controller-result.json"
    _controller_result(result_path, attempt, outcome="oom", workload_contract=None)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    target: dict[str, object] = payload
    parts = field.split(".")
    for key in parts[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    if value is None:
        del target[parts[-1]]
    else:
        target[parts[-1]] = value
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    (result_root / "ablation-state.json").write_text(json.dumps(_state([attempt])), encoding="utf-8")
    monkeypatch.setattr(run_ablation, "_load_controller", lambda: None)

    with pytest.raises(ValueError):
        run_ablation.execute_ablation(campaign_state=campaign_state, result_root=result_root, config_path=config_path)


def test_campaign_initialization_rejects_model_manifest_drift(tmp_path: Path) -> None:
    _, result_root, _ = _write_campaign_inputs(tmp_path)
    manifest_path = result_root / "model-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["size"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="model manifest"):
        run_ablation._new_state(result_root)


def test_recovery_rejects_internally_matching_foreign_model_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    campaign_state, result_root, config_path = _write_campaign_inputs(tmp_path)
    run_id = "ablation-r1-baseline-cold-foreign-model-hash"
    attempt = _attempt(run_id)
    result_path = result_root / "runs" / run_id / "controller-result.json"
    _controller_result(result_path, attempt, outcome="oom", workload_contract=None)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["model"]["expected_sha256"] = "a" * 64
    payload["model"]["actual_sha256"] = "a" * 64
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    (result_root / "ablation-state.json").write_text(json.dumps(_state([attempt])), encoding="utf-8")
    monkeypatch.setattr(run_ablation, "_load_controller", lambda: None)

    with pytest.raises(ValueError, match="model provenance"):
        run_ablation.execute_ablation(campaign_state=campaign_state, result_root=result_root, config_path=config_path)


def test_recovery_accepts_writer_zero_microsecond_timestamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FixedDateTime:
        @staticmethod
        def now(tz: object) -> datetime:
            assert tz is timezone.utc
            return datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)

    run_id = "ablation-r1-baseline-cold-zero-microseconds"
    attempt = _attempt(run_id)
    run_dir = tmp_path / run_id
    monkeypatch.setattr(CONTROLLER, "datetime", FixedDateTime)
    _controller_result(run_dir / "controller-result.json", attempt, outcome="oom", workload_contract=None)

    payload = json.loads((run_dir / "controller-result.json").read_text(encoding="utf-8"))
    assert payload["created_at"] == "2026-08-12T12:00:00.000000+00:00"
    assert run_ablation._load_controller_outcome(run_dir, attempt, MODEL_IDENTITY) == {
        "outcome": "oom",
        "image_id": "sha256:" + "a" * 64,
        "workload_contract": None,
    }


def test_existing_state_rejects_frozen_model_plan_drift(
    tmp_path: Path
) -> None:
    _, result_root, _ = _write_campaign_inputs(tmp_path)
    state = _state([])
    state["planned_model"]["actual_sha256"] = "a" * 64
    state_path = result_root / "ablation-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="ablation state"):
        run_ablation._load_state(state_path)
