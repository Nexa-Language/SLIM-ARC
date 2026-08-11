from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "summarize_results.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_summarize_results", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
summarize_results = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = summarize_results
SPEC.loader.exec_module(summarize_results)


def row(
    run_id: str, memory_gib: int, cache: str, outcome: str, *, swap_limit_bytes: int = 0
) -> object:
    return summarize_results.RunRow(
        run_id=run_id,
        outcome=outcome,
        memory_gib=memory_gib,
        cpus=4,
        pp=64,
        tg=16,
        repetitions=1,
        variant="patched",
        environment={},
        cache=cache,
        swap_limit_bytes=swap_limit_bytes,
        memory_peak_bytes=None,
        model_sha256="a" * 64,
        llama_commit="360e134",
        benchmark_rows=[],
    )


def test_selects_lowest_stable_no_swap_tier() -> None:
    rows = [
        row("8g-cold", 8, "cold", "success"),
        row("8g-warm", 8, "warm", "success"),
        row("6g-cold", 6, "cold", "success"),
        row("6g-warm", 6, "warm", "success"),
        row("4g-cold", 4, "cold", "oom"),
    ]

    assert summarize_results.select_lowest_stable(rows).memory_gib == 6


def test_never_promotes_swap_row_to_no_swap_result() -> None:
    rows = [
        row("no-swap", 6, "cold", "success"),
        row("swap", 4, "cold", "success", swap_limit_bytes=2 * 1024**3),
    ]

    assert [item.run_id for item in summarize_results.no_swap_rows(rows)] == ["no-swap"]


def test_rejects_duplicate_run_ids() -> None:
    rows = [
        row("duplicate", 6, "cold", "success"),
        row("duplicate", 6, "warm", "success"),
    ]

    with pytest.raises(ValueError, match="duplicate run id"):
        summarize_results.validate_rows(rows)


def test_rejects_mixed_model_identity() -> None:
    first = row("first", 6, "cold", "success")
    second = replace(row("second", 6, "warm", "success"), model_sha256="b" * 64)

    with pytest.raises(ValueError, match="model SHA-256"):
        summarize_results.validate_rows([first, second])
