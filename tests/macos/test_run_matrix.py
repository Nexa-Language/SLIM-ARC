from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "run_matrix.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_run_matrix", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
run_matrix = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_matrix
SPEC.loader.exec_module(run_matrix)


def record_twice(state: object, memory_gib: int, outcome: str) -> None:
    state.record_survival(
        memory_gib=memory_gib, outcome=outcome, run_id=f"{memory_gib}g-{outcome}-1"
    )
    state.record_survival(
        memory_gib=memory_gib, outcome=outcome, run_id=f"{memory_gib}g-{outcome}-2"
    )


def test_descends_to_three_after_four_succeeds_twice() -> None:
    state = run_matrix.MatrixState()
    for tier in (12, 8, 6, 4):
        record_twice(state, tier, "success")

    assert state.next_survival_tier() == 3


def test_tests_five_after_four_fails_twice() -> None:
    state = run_matrix.MatrixState()
    for tier in (12, 8, 6):
        record_twice(state, tier, "success")
    record_twice(state, 4, "oom")

    assert state.next_survival_tier() == 5


def test_stops_after_lower_tier_fails_and_keeps_last_success() -> None:
    state = run_matrix.MatrixState()
    for tier in (12, 8, 6, 4):
        record_twice(state, tier, "success")
    record_twice(state, 3, "oom")

    assert state.next_survival_tier() is None
    assert state.lowest_survival_gib == 4


def test_mixed_outcomes_require_a_deciding_attempt() -> None:
    state = run_matrix.MatrixState()
    state.record_survival(memory_gib=12, outcome="success", run_id="one")
    state.record_survival(memory_gib=12, outcome="oom", run_id="two")

    assert state.next_survival_tier() == 12


def test_round_trips_checkpoint(tmp_path: Path) -> None:
    state = run_matrix.MatrixState()
    record_twice(state, 12, "success")
    checkpoint = tmp_path / "matrix-state.json"
    state.save(checkpoint)

    loaded = run_matrix.MatrixState.load(checkpoint)

    assert loaded.next_survival_tier() == 8
    assert loaded.attempts == state.attempts
