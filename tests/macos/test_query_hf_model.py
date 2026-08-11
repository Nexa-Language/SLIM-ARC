from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "query_hf_model.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_query_hf_model", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
query_hf_model = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = query_hf_model
SPEC.loader.exec_module(query_hf_model)

FILENAME = "Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"


def model_payload(**overrides: Any) -> dict[str, Any]:
    sibling: dict[str, Any] = {
        "rfilename": FILENAME,
        "size": 48_400_000_000,
        "lfs": {"sha256": "a" * 64, "size": 48_400_000_000},
    }
    sibling.update(overrides.pop("sibling", {}))
    payload: dict[str, Any] = {
        "id": "Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF",
        "sha": "4c8630c1" + "b" * 32,
        "siblings": [sibling],
    }
    payload.update(overrides)
    return payload


def test_selects_exact_q4_k_m_file() -> None:
    model = query_hf_model.select_model_file(model_payload())

    assert model.filename == FILENAME
    assert model.size == 48_400_000_000
    assert model.expected_sha256 == "a" * 64
    assert model.revision == "4c8630c1" + "b" * 32


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (model_payload(siblings=[]), "exact model file"),
        (model_payload(sibling={"lfs": None}), "LFS metadata"),
        (
            model_payload(
                sibling={"lfs": {"sha256": "A" * 64, "size": 48_400_000_000}}
            ),
            "SHA-256",
        ),
        (
            model_payload(
                sibling={
                    "size": 39_999_999_999,
                    "lfs": {"sha256": "a" * 64, "size": 39_999_999_999},
                }
            ),
            "between 40 GB and 60 GB",
        ),
        (
            model_payload(
                sibling={
                    "size": 60_000_000_001,
                    "lfs": {"sha256": "a" * 64, "size": 60_000_000_001},
                }
            ),
            "between 40 GB and 60 GB",
        ),
        (
            model_payload(
                sibling={"lfs": {"sha256": "a" * 64, "size": 48_399_999_999}}
            ),
            "size mismatch",
        ),
        (model_payload(sha="not-a-revision"), "revision"),
    ],
)
def test_rejects_unverifiable_metadata(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        query_hf_model.select_model_file(payload)
