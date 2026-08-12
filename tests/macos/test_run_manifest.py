from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[2] / "scripts" / "macos" / "container" / "run_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("slim_arc_run_manifest", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
run_manifest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_manifest
SPEC.loader.exec_module(run_manifest)


RUNTIME_LINE = (
    "[SLIM-ARC-RUNTIME] schema=1 expert_samples=0 expert_issued_bytes=0 "
    "expert_hit_bytes=0 expert_waste_bytes=0 reclaim_candidates=0 reclaim_calls=0 "
    "reclaimed_bytes=0 reclaim_skipped_bytes=0 reclaim_failures=0 "
    "residency_samples=0 residency_admitted_experts=0 residency_admitted_bytes=0 "
    "residency_skipped_bytes=0 residency_fallbacks=0 pressure_normal=0 "
    "pressure_high=0 pressure_critical=0"
)


def write_fixture(cgroup_dir: Path, *, swap_max: str = "0") -> None:
    values = {
        "memory.max": "12884901888\n",
        "memory.swap.max": f"{swap_max}\n",
        "memory.peak": "10737418240\n",
        "memory.events": "low 0\nhigh 0\nmax 1\noom 0\noom_kill 0\n",
        "cpu.max": "400000 100000\n",
    }
    for name, value in values.items():
        (cgroup_dir / name).write_text(value, encoding="utf-8")


def write_runtime_log(path: Path, content: str = RUNTIME_LINE) -> Path:
    path.write_text(f"diagnostic line\n{content}\n", encoding="utf-8")
    return path


def runtime_line(counter_values: dict[str, int]) -> str:
    fields = ["schema=1"]
    fields.extend(
        f"{name}={counter_values[name]}" for name in run_manifest.RUNTIME_COUNTER_FIELDS
    )
    return f"[SLIM-ARC-RUNTIME] {' '.join(fields)}"


def test_manifest_has_resource_and_result_fields(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text(
        "LLAMA_COMMIT=360e134\nLLAMA_RESOLVED_COMMIT=" + "a" * 40 + "\n",
        encoding="utf-8",
    )
    runtime_logs = [
        write_runtime_log(tmp_path / "rep-1.stderr.log"),
        write_runtime_log(tmp_path / "rep-2.stderr.log"),
    ]

    manifest = run_manifest.build_manifest(
        variant="patched",
        outcome="success",
        exit_code=0,
        cgroup_dir=cgroup_dir,
        build_manifest_path=build_manifest,
        pp=4,
        tg=1,
        threads=4,
        repetitions=2,
        environment={"SLIM_ARC_DYNAMIC_MADV": "1"},
        runtime_logs=runtime_logs,
    )

    assert manifest["memory_limit_bytes"] == 12 * 1024**3
    assert manifest["memory_swap_limit_bytes"] == 0
    assert manifest["memory_peak_bytes"] == 10 * 1024**3
    assert manifest["cpu_quota"] == 400000
    assert manifest["cpu_period"] == 100000
    assert manifest["llama_commit"] == "360e134"
    assert manifest["variant"] == "patched"
    assert manifest["outcome"] == "success"
    assert manifest["runtime_metrics"] == [
        {
            "schema": 1,
            "expert_samples": 0,
            "expert_issued_bytes": 0,
            "expert_hit_bytes": 0,
            "expert_waste_bytes": 0,
            "reclaim_candidates": 0,
            "reclaim_calls": 0,
            "reclaimed_bytes": 0,
            "reclaim_skipped_bytes": 0,
            "reclaim_failures": 0,
            "residency_samples": 0,
            "residency_admitted_experts": 0,
            "residency_admitted_bytes": 0,
            "residency_skipped_bytes": 0,
            "residency_fallbacks": 0,
            "pressure_normal": 0,
            "pressure_high": 0,
            "pressure_critical": 0,
        }
    ] * 2
    assert manifest["runtime_metrics_summary"] == {
        key: 0 for key in run_manifest.RUNTIME_COUNTER_FIELDS
    }


def test_patched_success_requires_one_runtime_line_per_repetition(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")
    runtime_log = write_runtime_log(tmp_path / "rep-1.stderr.log")

    with pytest.raises(ValueError, match="runtime log count"):
        run_manifest.build_manifest(
            variant="patched",
            outcome="success",
            exit_code=0,
            cgroup_dir=cgroup_dir,
            build_manifest_path=build_manifest,
            pp=4,
            tg=1,
            threads=4,
            repetitions=2,
            environment={},
            runtime_logs=[runtime_log],
        )


@pytest.mark.parametrize(
    "line",
    [
        RUNTIME_LINE.replace("schema=1 ", ""),
        RUNTIME_LINE.replace("expert_samples=0", "expert_samples=0 expert_samples=0"),
        RUNTIME_LINE.replace("pressure_critical=0", "unknown=0"),
        RUNTIME_LINE.replace("expert_samples=0", "expert_samples=+1"),
        RUNTIME_LINE.replace("schema=1", "schema=2"),
        RUNTIME_LINE.replace("expert_samples=0", "expert_samples=\u0661"),
        RUNTIME_LINE.replace("expert_samples=0", "expert_samples=18446744073709551616"),
        f"{RUNTIME_LINE} extra-token",
        f"{RUNTIME_LINE} ",
    ],
)
def test_rejects_malformed_runtime_metric_line(line: str) -> None:
    with pytest.raises(ValueError):
        run_manifest.parse_runtime_metric_line(line)


def test_rejects_multiple_runtime_lines_in_one_log(tmp_path: Path) -> None:
    runtime_log = write_runtime_log(tmp_path / "rep-1.stderr.log", f"{RUNTIME_LINE}\n{RUNTIME_LINE}")

    with pytest.raises(ValueError, match="exactly one"):
        run_manifest.parse_runtime_log(runtime_log)


def test_runtime_metric_summary_saturates_each_counter() -> None:
    metric = run_manifest.parse_runtime_metric_line(
        RUNTIME_LINE.replace("expert_samples=0", "expert_samples=18446744073709551615")
    )

    assert run_manifest._runtime_metrics_summary([metric, metric])["expert_samples"] == 18446744073709551615


def test_manifest_preserves_runtime_log_order_and_saturates_each_counter(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")
    first = {
        name: run_manifest.UINT64_MAX - index
        for index, name in enumerate(run_manifest.RUNTIME_COUNTER_FIELDS)
    }
    second = {
        name: index + 1
        for index, name in enumerate(run_manifest.RUNTIME_COUNTER_FIELDS)
    }
    runtime_logs = [
        write_runtime_log(tmp_path / "rep-1.stderr.log", runtime_line(first)),
        write_runtime_log(tmp_path / "rep-2.stderr.log", runtime_line(second)),
    ]

    manifest = run_manifest.build_manifest(
        variant="patched",
        outcome="success",
        exit_code=0,
        cgroup_dir=cgroup_dir,
        build_manifest_path=build_manifest,
        pp=4,
        tg=1,
        threads=4,
        repetitions=2,
        environment={},
        runtime_logs=runtime_logs,
    )

    assert manifest["runtime_metrics"] == [{"schema": 1, **first}, {"schema": 1, **second}]
    assert manifest["runtime_metrics_summary"] == {
        name: run_manifest.UINT64_MAX for name in run_manifest.RUNTIME_COUNTER_FIELDS
    }


def test_baseline_accepts_no_runtime_logs_with_zero_summary(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")

    manifest = run_manifest.build_manifest(
        variant="baseline",
        outcome="success",
        exit_code=0,
        cgroup_dir=cgroup_dir,
        build_manifest_path=build_manifest,
        pp=4,
        tg=1,
        threads=4,
        repetitions=2,
        environment={},
        runtime_logs=[],
    )

    assert manifest["runtime_metrics"] == []
    assert manifest["runtime_metrics_summary"] == {
        key: 0 for key in run_manifest.RUNTIME_COUNTER_FIELDS
    }


def test_baseline_rejects_runtime_metric_line(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")
    runtime_log = write_runtime_log(tmp_path / "rep-1.stderr.log")

    with pytest.raises(ValueError, match="baseline runtime log"):
        run_manifest.build_manifest(
            variant="baseline",
            outcome="success",
            exit_code=0,
            cgroup_dir=cgroup_dir,
            build_manifest_path=build_manifest,
            pp=4,
            tg=1,
            threads=4,
            repetitions=1,
            environment={},
            runtime_logs=[runtime_log],
        )


def test_failed_patched_run_allows_absent_runtime_logs(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")

    manifest = run_manifest.build_manifest(
        variant="patched",
        outcome="error",
        exit_code=1,
        cgroup_dir=cgroup_dir,
        build_manifest_path=build_manifest,
        pp=4,
        tg=1,
        threads=4,
        repetitions=2,
        environment={},
        runtime_logs=[],
    )

    assert manifest["runtime_metrics"] == []


def test_manifest_records_pressure_admission_environment(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")
    runtime_log = write_runtime_log(tmp_path / "rep-1.stderr.log")

    manifest = run_manifest.build_manifest(
        variant="patched",
        outcome="success",
        exit_code=0,
        cgroup_dir=cgroup_dir,
        build_manifest_path=build_manifest,
        pp=64,
        tg=16,
        threads=4,
        repetitions=1,
        environment={
            "SLIM_ARC_PRESSURE_ADMISSION": "1",
            "SLIM_ARC_PRESSURE_RESERVE_MB": "512",
        },
        runtime_logs=[runtime_log],
    )

    assert manifest["environment"] == {
        "SLIM_ARC_PRESSURE_ADMISSION": "1",
        "SLIM_ARC_PRESSURE_RESERVE_MB": "512",
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (name, value)
        for name in ("SLIM_ARC_EXPERT_RECLAIM_WASTE", "SLIM_ARC_EXPERT_RESIDENCY")
        for value in ("0", "2", "true", "", "01")
    ],
)
def test_manifest_environment_rejects_non_enabled_finalist_policies(name: str, value: str) -> None:
    with pytest.raises(ValueError, match="must be exactly 1"):
        run_manifest.collect_slim_arc_environment({name: value})


def test_manifest_environment_rejects_unknown_slim_arc_variable() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        run_manifest.collect_slim_arc_environment({"SLIM_ARC_UNKNOWN": "1"})


def test_rejects_missing_hard_memory_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="memory.max"):
        run_manifest.build_manifest(
            variant="baseline",
            outcome="error",
            exit_code=1,
            cgroup_dir=tmp_path,
            build_manifest_path=tmp_path / "missing.env",
            pp=4,
            tg=1,
            threads=2,
            repetitions=1,
            environment={},
        )


def test_rejects_nonzero_swap_limit(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir, swap_max="1024")
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")

    with pytest.raises(ValueError, match="swap"):
        run_manifest.build_manifest(
            variant="patched",
            outcome="success",
            exit_code=0,
            cgroup_dir=cgroup_dir,
            build_manifest_path=build_manifest,
            pp=4,
            tg=1,
            threads=2,
            repetitions=1,
            environment={},
        )
