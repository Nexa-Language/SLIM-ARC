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


def test_manifest_has_resource_and_result_fields(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text(
        "LLAMA_COMMIT=360e134\nLLAMA_RESOLVED_COMMIT=" + "a" * 40 + "\n",
        encoding="utf-8",
    )

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
    )

    assert manifest["memory_limit_bytes"] == 12 * 1024**3
    assert manifest["memory_swap_limit_bytes"] == 0
    assert manifest["memory_peak_bytes"] == 10 * 1024**3
    assert manifest["cpu_quota"] == 400000
    assert manifest["cpu_period"] == 100000
    assert manifest["llama_commit"] == "360e134"
    assert manifest["variant"] == "patched"
    assert manifest["outcome"] == "success"


def test_manifest_records_pressure_admission_environment(tmp_path: Path) -> None:
    cgroup_dir = tmp_path / "cgroup"
    cgroup_dir.mkdir()
    write_fixture(cgroup_dir)
    build_manifest = tmp_path / "build-manifest.env"
    build_manifest.write_text("LLAMA_COMMIT=360e134\n", encoding="utf-8")

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
    )

    assert manifest["environment"] == {
        "SLIM_ARC_PRESSURE_ADMISSION": "1",
        "SLIM_ARC_PRESSURE_RESERVE_MB": "512",
    }


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
