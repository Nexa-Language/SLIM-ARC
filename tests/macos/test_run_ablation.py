from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "run_ablation.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_run_ablation", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
run_ablation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_ablation
SPEC.loader.exec_module(run_ablation)


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
