from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "run_constrained.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_run_constrained", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
run_constrained = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_constrained
SPEC.loader.exec_module(run_constrained)


def config(**overrides: object) -> object:
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
        cfg, tmp_path, container_name="slim-arc-run-test"
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
    assert (
        "type=bind,source=/var/lib/slim-arc/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf,target=/models/model.gguf,readonly"
        in command
    )


@pytest.mark.parametrize(
    "cfg",
    [
        config(memory_gib=17),
        config(memory_gib=1),
        config(cpus=9),
        config(timeout_seconds=1),
        config(variant="unknown"),
        config(env={"SLIM_ARC_UNKNOWN": "1"}),
        config(variant="baseline", env={"SLIM_ARC_DISABLE": "1"}),
    ],
)
def test_rejects_unsafe_configuration(cfg: object) -> None:
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
        config=cfg,
        container_name="slim-arc-run-test",
        outcome="success",
        return_code=0,
        timed_out=False,
        state={"OOMKilled": False, "ExitCode": 0},
        stderr="",
        model_manifest={"actual_sha256": "a" * 64},
        cold_cache=True,
    )

    assert '"SLIM_ARC_DYNAMIC_MADV": "1"' in output.read_text(encoding="utf-8")
