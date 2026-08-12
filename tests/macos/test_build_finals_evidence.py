from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).parents[2]


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = _module("slim_arc_build_finals_evidence", ROOT / "scripts/macos/build_finals_evidence.py")
ablation = _module("slim_arc_finals_ablation", ROOT / "scripts/macos/run_ablation.py")
controller = _module("slim_arc_finals_controller", ROOT / "scripts/macos/run_constrained.py")
manifest = _module("slim_arc_finals_manifest", ROOT / "scripts/macos/container/run_manifest.py")
build_writer = _module("slim_arc_finals_build_writer", ROOT / "scripts/macos/write_build_evidence.py")


IMAGE_ID = "sha256:" + "d" * 64
BUILD_ENV = (
    "LLAMA_COMMIT=360e134\n"
    + "SLIM_ARC_GIT_COMMIT=" + "a" * 40 + "\n"
    + "SLIM_ARC_BUILD_CONTEXT_SHA256=" + "b" * 64 + "\n"
    + "PATCHED_SOURCE_SHA256=" + "c" * 64 + "\n"
)
CONFIGS = {
    "baseline": ("baseline", {}),
    "patched-control": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1"}),
    "patched-reclaim": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1"}),
    "patched-residency": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RESIDENCY": "1"}),
    "patched-combined": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1", "SLIM_ARC_EXPERT_RESIDENCY": "1"}),
}


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_inputs(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "build-manifest.env"
    source.write_text(BUILD_ENV, encoding="utf-8")
    model = root / "model-manifest.json"
    _write_json(
        model,
        {
            "expected_sha256": controller.MODEL_SHA256,
            "actual_sha256": controller.MODEL_SHA256,
        },
    )
    return build_writer.write_build_evidence(root, source, model, IMAGE_ID)


def _cgroup(directory: Path, peak: int) -> Path:
    directory.mkdir()
    for name, value in {
        "memory.max": str(2 * 1024**3),
        "memory.swap.max": "0",
        "memory.peak": str(peak),
        "memory.events": "oom 0\n",
        "cpu.max": "400000 100000",
    }.items():
        (directory / name).write_text(value + ("\n" if not value.endswith("\n") else ""), encoding="utf-8")
    return directory


def _runtime_line(waste: int) -> str:
    values = {name: 0 for name in manifest.RUNTIME_COUNTER_FIELDS}
    values["expert_waste_bytes"] = waste
    return "[SLIM-ARC-RUNTIME] " + " ".join(["schema=1", *(f"{name}={value}" for name, value in values.items())])


def _write_run(
    root: Path,
    *,
    configuration: str,
    cache: str,
    round_number: int,
    peak: int = 1000,
    wall: float = 100.0,
    faults: int = 10,
    reads: int = 100,
    waste: int = 100,
    decode: float = 10.0,
    outcome: str = "success",
) -> dict[str, object]:
    variant, environment = CONFIGS[configuration]
    run_id = f"{configuration}-{cache}-r{round_number}"
    directory = root / "runs" / run_id
    directory.mkdir(parents=True)
    config = controller.RunConfig(2, 4, 64, 16, 1, 120, variant, environment)
    wrapper_contract: dict[str, object] | None = None
    if outcome == "success":
        cgroup = _cgroup(directory / "cgroup", peak)
        runtime_log = directory / "rep-1.stderr.log"
        runtime_log.write_text(_runtime_line(waste) + "\n" if variant == "patched" else "baseline\n", encoding="utf-8")
        wrapper = manifest.build_manifest(
            variant=variant,
            outcome="success",
            exit_code=0,
            cgroup_dir=cgroup,
            build_manifest_path=root / "build-manifest.env",
            pp=64,
            tg=16,
            threads=4,
            repetitions=1,
            image_id=IMAGE_ID,
            n_depth=0,
            environment=environment,
            runtime_logs=[runtime_log],
        )
        _write_json(directory / "run-manifest.json", wrapper)
        wrapper_contract = dict(wrapper["workload_contract"])
        (directory / "rep-1.stdout.log").write_text(
            f'{{"n_prompt":64,"n_gen":0,"avg_ts":3.0}}\n{{"n_prompt":0,"n_gen":16,"avg_ts":{decode}}}\n', encoding="utf-8"
        )
        (directory / "rep-1.time.txt").write_text(
            f"Elapsed (wall clock) time (h:mm:ss or m:ss): 1:{wall % 60:05.2f}\nMajor (requiring I/O) page faults: {faults}\nFile system inputs: {reads}\n", encoding="utf-8"
        )
        (directory / "cgroup-after.txt").write_text(
            "=== memory.max ===\n2147483648\n=== memory.swap.current ===\n0\n=== memory.swap.max ===\n0\n=== cpu.max ===\n400000 100000\n", encoding="utf-8"
        )
    controller._write_controller_result(
        path=directory / "controller-result.json",
        run_id=run_id,
        config=config,
        container_name="slim-arc-run-test",
        outcome=outcome,
        return_code=0 if outcome == "success" else 1,
        timed_out=outcome == "timeout",
        state={"ExitCode": 0, "OOMKilled": False},
        stderr="",
        model_manifest={"expected_sha256": controller.MODEL_SHA256, "actual_sha256": controller.MODEL_SHA256, "filename": controller.MODEL_FILENAME, "size": controller.MODEL_SIZE_BYTES},
        cold_cache=cache == "cold",
        image_id=IMAGE_ID,
        workload_contract=wrapper_contract,
    )
    return {"round": round_number, "configuration": configuration, "cache": cache, "outcome": outcome, "run_id": run_id, "image_id": IMAGE_ID, "workload_contract": wrapper_contract}


def _matrix(root: Path, *, rounds: tuple[int, ...] = (1, 2)) -> tuple[Path, Path]:
    build = _build_inputs(root)
    values = {
        "baseline": (1100, 100.0, 10, 100, 100, 10.0),
        "patched-control": (1000, 100.0, 10, 100, 100, 10.0),
        "patched-reclaim": (850, 110.0, 20, 190, 100, 10.0),
        "patched-residency": (1000, 110.0, 10, 80, 80, 11.0),
        "patched-combined": (800, 110.0, 20, 80, 70, 12.0),
    }
    attempts: list[object] = []
    for round_number in rounds:
        for cache in ("cold", "warm"):
            for configuration, value in values.items():
                attempts.append(_write_run(root, configuration=configuration, cache=cache, round_number=round_number, peak=value[0], wall=value[1], faults=value[2], reads=value[3], waste=value[4], decode=value[5]))
    campaign = root / "campaign-manifest.json"
    _write_json(campaign, ablation.build_campaign_manifest(attempts))
    return build, campaign


def _campaign_row(campaign: Path, run_id: str) -> dict[str, object]:
    payload = _json(campaign)
    return payload["runs"][f"runs/{run_id}"]


def test_aggregates_two_real_producer_rounds_deterministically(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    result = tool.build_finals_evidence(tmp_path, build, campaign)
    tool.write_finals_evidence(tmp_path, result)
    first = (tmp_path / "finals-results.json").read_bytes()
    tool.write_finals_evidence(tmp_path, tool.build_finals_evidence(tmp_path, build, campaign))
    assert first == (tmp_path / "finals-results.json").read_bytes()
    assert result["decisions"] == {"reclaim": "promoted", "residency": "promoted", "combined": "promoted"}
    assert result["sample_counts"]["patched-control:cold"] == 2


@pytest.mark.parametrize("rounds", [(1,), (1, 2, 3)])
def test_requires_exactly_two_complete_rounds(tmp_path: Path, rounds: tuple[int, ...]) -> None:
    build, campaign = _matrix(tmp_path, rounds=rounds)
    assert tool.build_finals_evidence(tmp_path, build, campaign)["decisions"]["reclaim"] == "insufficient_evidence"


def test_partial_or_terminal_failure_is_retained_but_never_promoted(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    payload = _json(campaign)
    del payload["runs"]["runs/baseline-cold-r2"]
    _write_json(campaign, payload)
    assert tool.build_finals_evidence(tmp_path, build, campaign)["decisions"]["combined"] == "insufficient_evidence"
    build, campaign = _matrix(tmp_path / "failure")
    row = _campaign_row(campaign, "patched-reclaim-warm-r2")
    row["outcome"] = "timeout"
    row.pop("workload_contract")
    payload = _json(campaign)
    payload["runs"]["runs/patched-reclaim-warm-r2"] = row
    _write_json(campaign, payload)
    run = tmp_path / "failure/runs/patched-reclaim-warm-r2"
    controller_payload = _json(run / "controller-result.json")
    controller_payload["outcome"] = "timeout"
    controller_payload["return_code"] = None
    controller_payload["timed_out"] = True
    _write_json(run / "controller-result.json", controller_payload)
    for name in ("run-manifest.json", "rep-1.stdout.log", "rep-1.time.txt", "cgroup-after.txt"):
        (run / name).unlink()
    result = tool.build_finals_evidence(tmp_path / "failure", build, campaign)
    assert next(row for row in result["runs"] if row["run_id"] == "patched-reclaim-warm-r2")["outcome"] == "timeout"
    assert result["decisions"]["reclaim"] == "insufficient_evidence"


@pytest.mark.parametrize("mutator", [
    lambda payload: payload.update({"outcome": "running"}),
    lambda payload: payload.update({"run_id": "other-run"}),
    lambda payload: payload.update({"workload_contract": {}}),
])
def test_rejects_nonterminal_or_unbound_controller(tmp_path: Path, mutator: Any) -> None:
    build, campaign = _matrix(tmp_path)
    path = tmp_path / "runs/patched-control-cold-r1/controller-result.json"
    payload = _json(path)
    mutator(payload)
    _write_json(path, payload)
    with pytest.raises(ValueError):
        tool.build_finals_evidence(tmp_path, build, campaign)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("return_code", 137),
        ("timed_out", True),
        ("container_state", {"ExitCode": 137, "OOMKilled": False}),
        ("container_state", {"ExitCode": 0, "OOMKilled": True}),
    ],
)
def test_rejects_contradictory_success_controller_execution_state(
    tmp_path: Path, field: str, value: object
) -> None:
    build, campaign = _matrix(tmp_path)
    path = tmp_path / "runs/patched-control-cold-r1/controller-result.json"
    payload = _json(path)
    payload[field] = value
    _write_json(path, payload)
    with pytest.raises(ValueError, match="success execution"):
        tool.build_finals_evidence(tmp_path, build, campaign)


def test_rejects_success_wrapper_with_nonzero_exit_code(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    path = tmp_path / "runs/patched-control-cold-r1/run-manifest.json"
    payload = _json(path)
    payload["exit_code"] = 137
    _write_json(path, payload)
    with pytest.raises(ValueError, match="wrapper contract"):
        tool.build_finals_evidence(tmp_path, build, campaign)


@pytest.mark.parametrize("outcome", ["timeout", "oom", "error"])
def test_rejects_incoherent_non_success_controller_execution_state(
    tmp_path: Path, outcome: str
) -> None:
    build, campaign = _matrix(tmp_path)
    run_id = "patched-control-cold-r1"
    payload = _json(campaign)
    row = payload["runs"][f"runs/{run_id}"]
    row["outcome"] = outcome
    row.pop("workload_contract")
    _write_json(campaign, payload)
    path = tmp_path / "runs" / run_id / "controller-result.json"
    controller_payload = _json(path)
    controller_payload["outcome"] = outcome
    _write_json(path, controller_payload)
    with pytest.raises(ValueError, match="execution"):
        tool.build_finals_evidence(tmp_path, build, campaign)


def test_allows_only_preregistration_interruption_without_controller(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    run_id = "patched-control-cold-r1"
    row = _campaign_row(campaign, run_id)
    row["outcome"] = "interrupted"
    row.pop("image_id")
    row.pop("workload_contract")
    payload = _json(campaign)
    payload["runs"][f"runs/{run_id}"] = row
    _write_json(campaign, payload)
    run = tmp_path / "runs" / run_id
    for path in run.iterdir():
        if path.is_file():
            path.unlink()
    result = tool.build_finals_evidence(tmp_path, build, campaign)
    assert result["decisions"]["reclaim"] == "insufficient_evidence"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome", "timeout"),
        ("image_id", "sha256:" + "e" * 64),
        ("workload_contract", {}),
    ],
)
def test_rejects_campaign_controller_cross_binding_mismatch(
    tmp_path: Path, field: str, value: object
) -> None:
    build, campaign = _matrix(tmp_path)
    payload = _json(campaign)
    payload["runs"]["runs/patched-control-cold-r1"][field] = value
    _write_json(campaign, payload)
    with pytest.raises(ValueError, match="campaign/controller"):
        tool.build_finals_evidence(tmp_path, build, campaign)


@pytest.mark.parametrize(
    "artifact", ["run-manifest.json", "rep-1.stdout.log", "rep-1.time.txt", "cgroup-after.txt"]
)
def test_rejects_success_with_missing_required_artifact(tmp_path: Path, artifact: str) -> None:
    build, campaign = _matrix(tmp_path)
    (tmp_path / "runs/patched-control-cold-r1" / artifact).unlink()
    with pytest.raises(ValueError):
        tool.build_finals_evidence(tmp_path, build, campaign)


@pytest.mark.parametrize("key", ["/tmp/outside", "runs/../escape", "runs\\escape", "runs//duplicate", "other/name"])
def test_rejects_unsafe_campaign_paths(tmp_path: Path, key: str) -> None:
    build, campaign = _matrix(tmp_path)
    payload = _json(campaign)
    row = payload["runs"].pop("runs/baseline-cold-r1")
    payload["runs"][key] = row
    _write_json(campaign, payload)
    with pytest.raises(ValueError, match="path"):
        tool.build_finals_evidence(tmp_path, build, campaign)


def test_rejects_symlink_and_duplicate_real_run_directory(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    payload = _json(campaign)
    payload["runs"]["runs/duplicate-run"] = dict(payload["runs"]["runs/baseline-cold-r1"])
    _write_json(campaign, payload)
    (tmp_path / "runs/duplicate-run").symlink_to(tmp_path / "runs/baseline-cold-r1", target_is_directory=True)
    with pytest.raises(ValueError):
        tool.build_finals_evidence(tmp_path, build, campaign)


def test_rejects_symlinked_success_artifact(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    run = tmp_path / "runs/patched-control-cold-r1"
    controller_path = run / "controller-result.json"
    copy = run / "controller-copy.json"
    copy.write_bytes(controller_path.read_bytes())
    controller_path.unlink()
    controller_path.symlink_to(copy)
    with pytest.raises(ValueError, match="unsafe controller"):
        tool.build_finals_evidence(tmp_path, build, campaign)


def test_rejects_nondivisible_four_cpu_quota_even_when_cgroup_matches_wrapper(
    tmp_path: Path,
) -> None:
    build, campaign = _matrix(tmp_path)
    run = tmp_path / "runs/patched-control-cold-r1"
    manifest_path = run / "run-manifest.json"
    wrapper = _json(manifest_path)
    wrapper["cpu_quota"] = 300000
    _write_json(manifest_path, wrapper)
    cgroup_path = run / "cgroup-after.txt"
    cgroup_path.write_text(
        cgroup_path.read_text(encoding="utf-8").replace("400000 100000", "300000 100000"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CPU evidence"):
        tool.build_finals_evidence(tmp_path, build, campaign)


def test_rejects_internally_consistent_one_cpu_wrapper_and_cgroup(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    run = tmp_path / "runs/patched-control-cold-r1"
    manifest_path = run / "run-manifest.json"
    wrapper = _json(manifest_path)
    wrapper["threads"] = 1
    wrapper["cpu_quota"] = 100000
    wrapper["workload_contract"]["threads"] = 1
    _write_json(manifest_path, wrapper)
    cgroup_path = run / "cgroup-after.txt"
    cgroup_path.write_text(
        cgroup_path.read_text(encoding="utf-8").replace("400000 100000", "100000 100000"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="wrapper contract"):
        tool.build_finals_evidence(tmp_path, build, campaign)


def test_rejects_fractional_cgroup_cpu_quota(tmp_path: Path) -> None:
    build, campaign = _matrix(tmp_path)
    path = tmp_path / "runs/patched-control-cold-r1/cgroup-after.txt"
    path.write_text(
        path.read_text(encoding="utf-8").replace("400000 100000", "400000.0 100000"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CPU evidence"):
        tool.build_finals_evidence(tmp_path, build, campaign)


@pytest.mark.parametrize("mutator", [
    lambda wrapper: wrapper.update({"repetitions": 2}),
    lambda wrapper: wrapper["workload_contract"].update({"threads": 3}),
])
def test_rejects_success_wrapper_contract_and_repetition_mismatch(tmp_path: Path, mutator: Any) -> None:
    build, campaign = _matrix(tmp_path)
    path = tmp_path / "runs/patched-control-cold-r1/run-manifest.json"
    wrapper = _json(path)
    mutator(wrapper)
    _write_json(path, wrapper)
    with pytest.raises(ValueError):
        tool.build_finals_evidence(tmp_path, build, campaign)


@pytest.mark.parametrize("content", [
    "Elapsed (wall clock) time (h:mm:ss or m:ss): 1:00\nMajor (requiring I/O) page faults: -1\nFile system inputs: 1\n",
    "Elapsed (wall clock) time (h:mm:ss or m:ss): 1:00\nMajor (requiring I/O) page faults: 1\nFile system inputs: -1\n",
])
def test_rejects_negative_gnu_time_counters(tmp_path: Path, content: str) -> None:
    path = tmp_path / "time.txt"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        tool._time(path)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1"])
def test_rejects_nonfinite_or_negative_decode(tmp_path: Path, value: str) -> None:
    path = tmp_path / "stdout.log"
    path.write_text(f'{{"n_prompt":0,"n_gen":16,"avg_ts":{value}}}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        tool._decode(path)
