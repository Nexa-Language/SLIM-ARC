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
        wall_seconds=(),
        major_faults=(),
        filesystem_inputs=(),
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


def test_summary_reports_prefill_and_decode_separately() -> None:
    benchmark = [
        {"n_prompt": 64, "n_gen": 0, "avg_ts": 1.25},
        {"n_prompt": 0, "n_gen": 16, "avg_ts": 2.75},
    ]
    measured = replace(row("measured", 2, "cold", "success"), benchmark_rows=benchmark)

    summary = summarize_results.render_summary([measured])

    assert "| pp t/s | tg t/s |" in summary
    assert "| 1.2500 | 2.7500 |" in summary
    assert "avg t/s" not in summary


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0:55.33", 55.33), ("1:08.29", 68.29), ("1:02:03", 3723.0)],
)
def test_parses_gnu_time_elapsed(raw: str, expected: float) -> None:
    assert summarize_results.parse_elapsed_seconds(raw) == pytest.approx(expected)


def test_summary_reports_wall_time() -> None:
    measured = replace(row("measured", 2, "cold", "success"), wall_seconds=(52.0, 54.0))

    summary = summarize_results.render_summary([measured])

    assert "| wall s |" in summary
    assert "| 53.00 |" in summary


def test_summary_names_ablation_numerator_and_denominator_runs() -> None:
    baseline = replace(
        row("ablation-baseline-warm", 2, "warm", "success"),
        variant="baseline",
        wall_seconds=(55.0,),
    )
    default = replace(
        row("ablation-patched-default-warm", 2, "warm", "success"),
        wall_seconds=(54.0,),
    )
    no_prefetch = replace(
        row("ablation-patched-no-prefetch-warm", 2, "warm", "success"),
        environment={"SLIM_ARC_NO_PREFETCH": "1"},
        wall_seconds=(51.0,),
    )

    summary = summarize_results.render_summary([baseline, default, no_prefetch])

    assert "ablation-patched-no-prefetch-warm" in summary
    assert "ablation-patched-default-warm" in summary
    assert "5.56%" in summary
    assert "Start plan 23 pressure admission: yes" in summary


def test_summary_reports_cpu_curve_and_unobserved_oom_boundary() -> None:
    cpu_two = replace(row("cpu-2c", 2, "cold", "success"), cpus=2, wall_seconds=(70.0,))
    cpu_four = replace(
        row("cpu-4c", 2, "cold", "success"), cpus=4, wall_seconds=(60.0,)
    )

    summary = summarize_results.render_summary([cpu_two, cpu_four])

    assert "2 CPU `cpu-2c` 70.00s" in summary
    assert "4 CPU `cpu-4c` 60.00s" in summary
    assert "No OOM boundary was observed down to the 2 GiB controller floor" in summary
