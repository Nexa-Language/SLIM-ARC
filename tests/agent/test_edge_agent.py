from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "agent" / "edge_agent.py"
SPEC = importlib.util.spec_from_file_location("edge_agent", MODULE_PATH)
assert SPEC and SPEC.loader
edge_agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = edge_agent
SPEC.loader.exec_module(edge_agent)


class FakeClient:
    def __init__(self, replies: list[edge_agent.GenerationResult]) -> None:
        self.replies = replies
        self.requests: list[tuple[list[dict[str, str]], int]] = []

    def generate(self, messages: list[dict[str, str]], max_tokens: int) -> edge_agent.GenerationResult:
        self.requests.append((messages, max_tokens))
        return self.replies.pop(0)


def generation(payload: dict[str, object], *, tps: float = 10.0) -> edge_agent.GenerationResult:
    text = json.dumps(payload)
    tokens = max(1, (len(text) + 3) // 4)
    return edge_agent.GenerationResult(text, tokens / tps + 0.1, 0.1, tokens)


def test_context_policy_keeps_prefix_and_latest_messages() -> None:
    policy = edge_agent.ContextPolicy(max_context_chars=256, max_observation_chars=64)
    messages = [
        {"role": "system", "content": "stable"},
        {"role": "user", "content": "old" * 100},
        {"role": "tool", "content": "x" * 200},
        {"role": "user", "content": "latest"},
    ]

    compacted = policy.compact(messages)

    assert compacted[0] == messages[0]
    assert compacted[-1] == messages[-1]
    assert sum(len(item["content"]) for item in compacted) <= 256
    assert any("truncated" in item["content"] for item in compacted if item["role"] == "tool")


def test_restricted_shell_runs_allowed_command(tmp_path: Path) -> None:
    shell = edge_agent.RestrictedShell(tmp_path, ["pwd"], timeout_seconds=1, max_output_bytes=128)

    result = shell.run(["pwd"])

    assert result.returncode == 0
    assert result.output.strip() == str(tmp_path)
    assert not result.truncated


@pytest.mark.parametrize("argv", [["sh", "-c", "id"], ["cat", "/etc/passwd"], ["cat", "../secret"]])
def test_restricted_shell_rejects_unsafe_commands(tmp_path: Path, argv: list[str]) -> None:
    shell = edge_agent.RestrictedShell(tmp_path, ["cat"], timeout_seconds=1, max_output_bytes=128)

    with pytest.raises(ValueError):
        shell.run(argv)


def test_restricted_shell_limits_npu_smi_to_info(tmp_path: Path) -> None:
    shell = edge_agent.RestrictedShell(tmp_path, ["npu-smi"], timeout_seconds=1, max_output_bytes=128)

    with pytest.raises(ValueError):
        shell.run(["npu-smi", "set", "-t", "power-limit", "-i", "0", "-c", "300"])


def test_restricted_shell_truncates_output(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("x" * 1000, encoding="utf-8")
    shell = edge_agent.RestrictedShell(tmp_path, ["cat"], timeout_seconds=1, max_output_bytes=32)

    result = shell.run(["cat", "large.txt"])

    assert result.truncated
    assert "tool output truncated" in result.output


def test_slow_output_reduces_next_token_budget() -> None:
    budget = edge_agent.AdaptiveTokenBudget(initial=200, minimum=50, slow_tps=2.0)

    budget.observe(1.0)
    assert budget.current == 130
    budget.observe(0.5)
    assert budget.current == 84
    budget.observe(0.5)
    assert budget.current == 54
    budget.observe(0.5)
    assert budget.current == 50
    budget.observe(4.0)
    assert budget.current == 50


def test_agent_completes_shell_round_trip(tmp_path: Path) -> None:
    client = FakeClient([generation({"tool": "shell", "args": ["pwd"]}, tps=1.0), generation({"final": "done"})])
    agent = edge_agent.EdgeAgent(
        client,
        edge_agent.RestrictedShell(tmp_path, ["pwd"], timeout_seconds=1, max_output_bytes=128),
        edge_agent.ContextPolicy(1024, 256),
        edge_agent.AdaptiveTokenBudget(128, 32, slow_tps=2.0),
        max_steps=3,
        total_timeout_seconds=5,
    )

    answer = agent.run("show cwd")

    assert answer == "done"
    assert [event["event"] for event in agent.metrics] == ["model", "tool", "model"]
    assert client.requests[0][1] == 128
    assert client.requests[1][1] == 83
    assert any(item["role"] == "tool" and str(tmp_path) in item["content"] for item in client.requests[1][0])


def test_model_action_requires_exactly_one_variant() -> None:
    with pytest.raises(RuntimeError):
        edge_agent._parse_action('{"tool":"shell","final":"no"}')
