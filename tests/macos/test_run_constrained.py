from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "run_constrained.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_run_constrained", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
run_constrained = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_constrained
SPEC.loader.exec_module(run_constrained)


def config(**overrides: object) -> Any:
    values: dict[str, object] = {
        "memory_gib": 8,
        "cpus": 4,
        "pp": 4,
        "tg": 1,
        "repetitions": 2,
        "timeout_seconds": 1800,
        "variant": "patched",
        "env": {},
    }
    values.update(overrides)
    return run_constrained.RunConfig(**values)


def test_no_swap_docker_limits_are_exact(tmp_path: Path) -> None:
    cfg = config()
    command = run_constrained.build_docker_command(
        cfg, tmp_path, container_name="slim-arc-run-test", image_id=image_id()
    )
    assert ["--memory", "8g"] == command[
        command.index("--memory") : command.index("--memory") + 2
    ]
    assert ["--memory-swap", "8g"] == command[
        command.index("--memory-swap") : command.index("--memory-swap") + 2
    ]
    assert ["--cpus", "4"] == command[
        command.index("--cpus") : command.index("--cpus") + 2
    ]
    assert ["--ulimit", "memlock=536870912:536870912"] == command[
        command.index("--ulimit") : command.index("--ulimit") + 2
    ]
    assert (
        "type=bind,source=/var/lib/slim-arc/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf,target=/models/model.gguf,readonly"
        in command
    )


def test_allows_one_gib_extreme_memory_diagnostic(tmp_path: Path) -> None:
    command = run_constrained.build_docker_command(
        config(memory_gib=1),
        tmp_path,
        container_name="slim-arc-run-test",
        image_id=image_id(),
    )

    assert command[command.index("--memory") + 1] == "1g"
    assert command[command.index("--memory-swap") + 1] == "1g"


def image_id() -> str:
    return "sha256:" + "a" * 64


def test_docker_command_uses_resolved_immutable_image_identity(tmp_path: Path) -> None:
    command = run_constrained.build_docker_command(
        config(), tmp_path, container_name="slim-arc-run-test", image_id=image_id()
    )

    assert command[-2] == image_id()
    assert command.count(f"RUN_IMAGE_ID={image_id()}") == 1
    assert run_constrained.IMAGE not in command


@pytest.mark.parametrize("raw", ["", "sha256:" + "A" * 64, "sha256:" + "a" * 63])
def test_rejects_malformed_inspected_image_identity(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setattr(
        run_constrained,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, f"{raw}\n", ""),
    )

    with pytest.raises(ValueError, match="image ID"):
        run_constrained.resolve_image_id()


@pytest.mark.parametrize(
    "cfg",
    [
        config(memory_gib=17),
        config(memory_gib=0),
        config(cpus=9),
        config(timeout_seconds=1),
        config(variant="unknown"),
        config(env={"SLIM_ARC_UNKNOWN": "1"}),
        config(variant="baseline", env={"SLIM_ARC_DISABLE": "1"}),
    ],
)
def test_rejects_unsafe_configuration(cfg: Any) -> None:
    with pytest.raises(ValueError):
        cfg.validate()


def test_classifies_inspected_oom_before_exit_code() -> None:
    outcome = run_constrained.classify_outcome(
        timed_out=False,
        return_code=137,
        container_state={"OOMKilled": True, "ExitCode": 137},
        memory_events={"oom_kill": 1},
    )

    assert outcome == "oom"


def test_classifies_timeout_before_oom() -> None:
    outcome = run_constrained.classify_outcome(
        timed_out=True,
        return_code=None,
        container_state={"OOMKilled": True, "ExitCode": 137},
        memory_events={"oom_kill": 1},
    )

    assert outcome == "timeout"


def test_exit_137_without_oom_evidence_is_error() -> None:
    outcome = run_constrained.classify_outcome(
        timed_out=False,
        return_code=137,
        container_state={"OOMKilled": False, "ExitCode": 137},
        memory_events={"oom_kill": 0},
    )

    assert outcome == "error"


def test_controller_result_serializes_frozen_environment(tmp_path: Path) -> None:
    output = tmp_path / "controller-result.json"
    cfg = config(env={"SLIM_ARC_DYNAMIC_MADV": "1"})

    run_constrained._write_controller_result(
        path=output,
        run_id="ablation-r1-baseline-cold-test",
        config=cfg,
        container_name="slim-arc-run-test",
        outcome="success",
        return_code=0,
        timed_out=False,
        state={"OOMKilled": False, "ExitCode": 0},
        stderr="",
        model_manifest={"actual_sha256": "a" * 64},
        cold_cache=True,
        image_id=image_id(),
        workload_contract={
            "seed": 1,
            "seed_source": "implicit_c_rand_default",
            "context_tokens": 5,
            "n_prompt": 4,
            "n_gen": 1,
            "n_depth": 0,
            "threads": 4,
            "no_warmup": True,
            "load_mode": "mmap",
            "offline": True,
        },
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["config"]["env"] == {"SLIM_ARC_DYNAMIC_MADV": "1"}
    assert payload["image_id"] == image_id()
    assert payload["run_id"] == "ablation-r1-baseline-cold-test"
    assert payload["workload_contract"]["n_depth"] == 0


def test_controller_writer_keeps_zero_microsecond_timestamp_canonical(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FixedDateTime:
        @staticmethod
        def now(tz: object) -> datetime:
            assert tz is timezone.utc
            return datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(run_constrained, "datetime", FixedDateTime)
    output = tmp_path / "controller-result.json"
    run_constrained._write_controller_result(
        path=output,
        run_id="ablation-r1-baseline-cold-zero-microseconds",
        config=config(),
        container_name="slim-arc-run-test",
        outcome="oom",
        return_code=137,
        timed_out=False,
        state={"OOMKilled": True, "ExitCode": 137},
        stderr="",
        model_manifest={"actual_sha256": "a" * 64},
        cold_cache=True,
        image_id=image_id(),
        workload_contract=None,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["created_at"] == "2026-08-12T12:00:00.000000+00:00"


def test_pressure_environment_is_allowlisted() -> None:
    cfg = config(
        env={
            "SLIM_ARC_PRESSURE_ADMISSION": "1",
            "SLIM_ARC_PRESSURE_RESERVE_MB": "512",
        }
    )

    cfg.validate()


@pytest.mark.parametrize("value", ["1", "512", "768", "1024"])
def test_allows_extended_hot_expert_budget(value: str) -> None:
    config(env={"SLIM_ARC_EXPERT_HOT_MB": value}).validate()


@pytest.mark.parametrize("value", ["", "0", "1025", "-1", "1.5", "true"])
def test_rejects_invalid_hot_expert_budget(value: str) -> None:
    with pytest.raises(ValueError, match="SLIM_ARC_EXPERT_HOT_MB"):
        config(env={"SLIM_ARC_EXPERT_HOT_MB": value}).validate()


@pytest.mark.parametrize("value", ["1", "32", "64"])
def test_allows_bounded_layer_local_expert_pipeline(value: str) -> None:
    cfg = config(env={"SLIM_ARC_EXPERT_PIPELINE_MB": value})

    cfg.validate()


@pytest.mark.parametrize("value", ["", "0", "65", "-1", "1.5", "true"])
def test_rejects_unbounded_layer_local_expert_pipeline(value: str) -> None:
    cfg = config(env={"SLIM_ARC_EXPERT_PIPELINE_MB": value})

    with pytest.raises(ValueError, match="SLIM_ARC_EXPERT_PIPELINE_MB"):
        cfg.validate()


@pytest.mark.parametrize("value", ["1", "8", "10", "16", "64"])
def test_allows_cross_layer_router_topk(value: str) -> None:
    config(
        env={
            "SLIM_ARC_CROSS_LAYER_GATE": "1",
            "SLIM_ARC_CROSS_LAYER_TOPK": value,
        }
    ).validate()


@pytest.mark.parametrize("value", ["", "0", "65", "-1", "1.5", "true"])
def test_rejects_invalid_cross_layer_router_topk(value: str) -> None:
    with pytest.raises(ValueError, match="SLIM_ARC_CROSS_LAYER_TOPK"):
        config(
            env={
                "SLIM_ARC_CROSS_LAYER_GATE": "1",
                "SLIM_ARC_CROSS_LAYER_TOPK": value,
            }
        ).validate()


def test_cross_layer_router_requires_gate_and_topk_together() -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        config(env={"SLIM_ARC_CROSS_LAYER_GATE": "1"}).validate()
    with pytest.raises(ValueError, match="must be configured together"):
        config(env={"SLIM_ARC_CROSS_LAYER_TOPK": "10"}).validate()


@pytest.mark.parametrize("value", ["1", "2", "4", "8", "64"])
def test_allows_cross_layer_transition_topk(value: str) -> None:
    config(
        env={
            "SLIM_ARC_CROSS_LAYER_TRANSITION": "1",
            "SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": value,
        }
    ).validate()


@pytest.mark.parametrize("value", ["", "0", "65", "-1", "1.5", "true"])
def test_rejects_invalid_cross_layer_transition_topk(value: str) -> None:
    with pytest.raises(ValueError, match="SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK"):
        config(
            env={
                "SLIM_ARC_CROSS_LAYER_TRANSITION": "1",
                "SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": value,
            }
        ).validate()


def test_cross_layer_transition_requires_flag_and_topk_together() -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        config(env={"SLIM_ARC_CROSS_LAYER_TRANSITION": "1"}).validate()
    with pytest.raises(ValueError, match="must be configured together"):
        config(env={"SLIM_ARC_CROSS_LAYER_TRANSITION_TOPK": "2"}).validate()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (name, value)
        for name in (
            "SLIM_ARC_EXPERT_RECLAIM_WASTE",
            "SLIM_ARC_EXPERT_RESIDENCY",
            "SLIM_ARC_NO_EXPERT_PREFETCH",
            "SLIM_ARC_NO_WEIGHT_PREFETCH",
            "SLIM_ARC_ROUTER_MLOCK",
            "SLIM_ARC_ROUTER_PREFETCH",
            "SLIM_ARC_SLOW_STORAGE",
        )
        for value in ("0", "2", "true", "", "01")
    ],
)
def test_rejects_non_enabled_finalist_policy_values(name: str, value: str) -> None:
    cfg = config(env={name: value})

    with pytest.raises(ValueError, match="must be exactly 1"):
        cfg.validate()


def test_allows_finalist_policy_flags_only_when_enabled() -> None:
    cfg = config(
        env={
            "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1",
            "SLIM_ARC_EXPERT_RESIDENCY": "1",
            "SLIM_ARC_NO_EXPERT_PREFETCH": "1",
            "SLIM_ARC_NO_WEIGHT_PREFETCH": "1",
            "SLIM_ARC_ROUTER_MLOCK": "1",
            "SLIM_ARC_ROUTER_PREFETCH": "1",
            "SLIM_ARC_SLOW_STORAGE": "1",
        }
    )

    cfg.validate()


def test_docker_command_carries_each_enabled_finalist_policy(tmp_path: Path) -> None:
    cfg = config(
        env={
            "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1",
            "SLIM_ARC_EXPERT_RESIDENCY": "1",
            "SLIM_ARC_NO_EXPERT_PREFETCH": "1",
            "SLIM_ARC_NO_WEIGHT_PREFETCH": "1",
            "SLIM_ARC_ROUTER_MLOCK": "1",
            "SLIM_ARC_ROUTER_PREFETCH": "1",
            "SLIM_ARC_SLOW_STORAGE": "1",
        }
    )

    command = run_constrained.build_docker_command(
        cfg, tmp_path, container_name="slim-arc-run-test", image_id=image_id()
    )

    assert command.count("SLIM_ARC_EXPERT_RECLAIM_WASTE=1") == 1
    assert command.count("SLIM_ARC_EXPERT_RESIDENCY=1") == 1
    assert command.count("SLIM_ARC_NO_EXPERT_PREFETCH=1") == 1
    assert command.count("SLIM_ARC_NO_WEIGHT_PREFETCH=1") == 1
    assert command.count("SLIM_ARC_ROUTER_MLOCK=1") == 1
    assert command.count("SLIM_ARC_ROUTER_PREFETCH=1") == 1
    assert command.count("SLIM_ARC_SLOW_STORAGE=1") == 1
