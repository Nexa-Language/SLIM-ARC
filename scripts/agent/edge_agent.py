#!/usr/bin/env python3
"""Minimal edge-oriented agent loop for a resident local LLM endpoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Sequence


DEFAULT_SYSTEM_PROMPT = """You are an edge-device operations assistant.
Keep reasoning and final answers concise. To run a command, emit only JSON:
{"tool":"shell","args":["command","arg"]}
To answer, emit only JSON: {"final":"answer"}
Never invent tool output and never emit both forms at once."""

DEFAULT_ALLOWED_COMMANDS = (
    "cat",
    "df",
    "du",
    "free",
    "grep",
    "head",
    "ls",
    "nproc",
    "npu-smi",
    "pwd",
    "tail",
    "uname",
    "wc",
)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    elapsed_seconds: float
    ttft_seconds: float
    estimated_output_tokens: int

    @property
    def estimated_tps(self) -> float:
        decode_seconds = max(self.elapsed_seconds - self.ttft_seconds, 1e-9)
        return self.estimated_output_tokens / decode_seconds


class ModelClient(Protocol):
    def generate(self, messages: Sequence[dict[str, str]], max_tokens: int) -> GenerationResult: ...


def _estimated_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


class OpenAIChatClient:
    def __init__(self, endpoint: str, model: str, timeout_seconds: float, api_key: str | None = None) -> None:
        endpoint = endpoint.rstrip("/")
        self._url = endpoint if endpoint.endswith("/v1/chat/completions") else f"{endpoint}/v1/chat/completions"
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key

    def generate(self, messages: Sequence[dict[str, str]], max_tokens: int) -> GenerationResult:
        payload = json.dumps(
            {"model": self._model, "messages": list(messages), "max_tokens": max_tokens, "temperature": 0, "stream": True}
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(self._url, data=payload, headers=headers, method="POST")
        started = time.monotonic()
        first_token_at: float | None = None
        chunks: list[str] = []
        usage_tokens: int | None = None
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    usage = event.get("usage") or {}
                    if isinstance(usage.get("completion_tokens"), int):
                        usage_tokens = usage["completion_tokens"]
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    content = (choices[0].get("delta") or {}).get("content")
                    if content:
                        first_token_at = first_token_at or time.monotonic()
                        chunks.append(content)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"model endpoint failed: {exc}") from exc
        finished = time.monotonic()
        text = "".join(chunks)
        if not text:
            raise RuntimeError("model endpoint returned no content")
        return GenerationResult(
            text=text,
            elapsed_seconds=finished - started,
            ttft_seconds=(first_token_at or finished) - started,
            estimated_output_tokens=usage_tokens or _estimated_tokens(text),
        )


class LlamaCliClient:
    """Compatibility path; unlike a resident endpoint, this reloads the model per step."""

    def __init__(self, binary: Path, model: Path, timeout_seconds: float) -> None:
        self._binary = binary
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, messages: Sequence[dict[str, str]], max_tokens: int) -> GenerationResult:
        prompt = "\n".join(f"{message['role'].upper()}: {message['content']}" for message in messages) + "\nASSISTANT:"
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [str(self._binary), "-m", str(self._model), "-n", str(max_tokens), "--temp", "0", "-p", prompt],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("llama-cli timed out") from exc
        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            raise RuntimeError(f"llama-cli failed with exit {completed.returncode}: {completed.stderr[-500:]}")
        text = completed.stdout.strip()
        if not text:
            raise RuntimeError("llama-cli returned no content")
        return GenerationResult(text, elapsed, elapsed, _estimated_tokens(text))


def _clip_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit < 32:
        return text[:limit]
    marker = "\n...[truncated]...\n"
    side = (limit - len(marker)) // 2
    return f"{text[:side]}{marker}{text[-side:]}"


class ContextPolicy:
    def __init__(self, max_context_chars: int, max_observation_chars: int) -> None:
        if max_context_chars < 256 or max_observation_chars < 64:
            raise ValueError("context limits are too small")
        self._max_context_chars = max_context_chars
        self._max_observation_chars = max_observation_chars

    def compact(self, messages: Sequence[dict[str, str]]) -> list[dict[str, str]]:
        if not messages or messages[0].get("role") != "system":
            raise ValueError("the first message must be the stable system prefix")
        system = dict(messages[0])
        if len(system["content"]) >= self._max_context_chars:
            raise ValueError("stable system prefix exceeds the context budget")
        budget = self._max_context_chars - len(system["content"])
        selected: list[dict[str, str]] = []
        for message in reversed(messages[1:]):
            content = message["content"]
            if message.get("role") == "tool":
                content = _clip_middle(content, self._max_observation_chars)
            content = _clip_middle(content, max(0, budget))
            cost = len(content) + len(message.get("role", ""))
            if cost <= 0:
                continue
            selected.append({"role": message["role"], "content": content})
            budget -= cost
            if budget <= 0:
                break
        return [system, *reversed(selected)]


@dataclass(frozen=True)
class ShellResult:
    argv: list[str]
    returncode: int
    elapsed_seconds: float
    output: str
    truncated: bool


class RestrictedShell:
    def __init__(self, cwd: Path, allowed_commands: Sequence[str], timeout_seconds: float, max_output_bytes: int) -> None:
        self._cwd = cwd.resolve(strict=True)
        self._allowed_commands = frozenset(allowed_commands)
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    def _validate(self, argv: Sequence[str]) -> list[str]:
        if not argv or not all(isinstance(item, str) and item and "\x00" not in item for item in argv):
            raise ValueError("shell args must be a non-empty string array")
        command = Path(argv[0]).name
        if argv[0] != command or command not in self._allowed_commands:
            raise ValueError(f"command is not allowed: {argv[0]}")
        if command == "npu-smi" and (len(argv) < 2 or argv[1] != "info"):
            raise ValueError("npu-smi is restricted to the read-only info command")
        for argument in argv[1:]:
            candidate = Path(argument)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"path escape is not allowed: {argument}")
            local_path = self._cwd / candidate
            if local_path.exists() and not local_path.resolve().is_relative_to(self._cwd):
                raise ValueError(f"symlink escape is not allowed: {argument}")
        return list(argv)

    def run(self, argv: Sequence[str]) -> ShellResult:
        checked = self._validate(argv)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                checked,
                cwd=self._cwd,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
                check=False,
                capture_output=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"tool timed out after {self._timeout_seconds:g}s") from exc
        elapsed = time.monotonic() - started
        raw = completed.stdout + completed.stderr
        truncated = len(raw) > self._max_output_bytes
        output = raw[: self._max_output_bytes].decode("utf-8", errors="replace")
        if truncated:
            output += "\n...[tool output truncated]"
        return ShellResult(checked, completed.returncode, elapsed, output, truncated)


class AdaptiveTokenBudget:
    def __init__(self, initial: int, minimum: int, slow_tps: float, reduction: float = 0.65) -> None:
        if minimum <= 0 or initial < minimum or not 0 < reduction < 1:
            raise ValueError("invalid token budget")
        self.current = initial
        self._minimum = minimum
        self._slow_tps = slow_tps
        self._reduction = reduction

    def observe(self, tps: float) -> None:
        if 0 < tps < self._slow_tps:
            self.current = max(self._minimum, int(self.current * self._reduction))


def _parse_action(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1])
            if stripped.lstrip().startswith("json"):
                stripped = stripped.lstrip()[4:].lstrip()
    try:
        action = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RuntimeError("model response is not a JSON action") from exc
    if not isinstance(action, dict) or ("tool" in action) == ("final" in action):
        raise RuntimeError("model action must contain exactly one of tool or final")
    return action


class EdgeAgent:
    def __init__(
        self,
        client: ModelClient,
        shell: RestrictedShell,
        context_policy: ContextPolicy,
        token_budget: AdaptiveTokenBudget,
        max_steps: int,
        total_timeout_seconds: float,
    ) -> None:
        self._client = client
        self._shell = shell
        self._context_policy = context_policy
        self._token_budget = token_budget
        self._max_steps = max_steps
        self._total_timeout_seconds = total_timeout_seconds
        self.metrics: list[dict[str, object]] = []

    def run(self, prompt: str) -> str:
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        deadline = time.monotonic() + self._total_timeout_seconds
        for step in range(1, self._max_steps + 1):
            if time.monotonic() >= deadline:
                raise RuntimeError("agent total timeout exceeded")
            compacted = self._context_policy.compact(messages)
            max_tokens = self._token_budget.current
            result = self._client.generate(compacted, max_tokens)
            self._token_budget.observe(result.estimated_tps)
            event: dict[str, object] = {
                "event": "model",
                "step": step,
                "context_chars": sum(len(item["content"]) for item in compacted),
                "max_tokens": max_tokens,
                "elapsed_seconds": result.elapsed_seconds,
                "ttft_seconds": result.ttft_seconds,
                "estimated_output_tokens": result.estimated_output_tokens,
                "estimated_tps": result.estimated_tps,
            }
            self.metrics.append(event)
            action = _parse_action(result.text)
            messages.append({"role": "assistant", "content": result.text})
            if "final" in action:
                if not isinstance(action["final"], str):
                    raise RuntimeError("final must be a string")
                return action["final"]
            if action.get("tool") != "shell" or not isinstance(action.get("args"), list):
                raise RuntimeError("only the shell tool with an args array is supported")
            tool_result = self._shell.run(action["args"])
            self.metrics.append(
                {
                    "event": "tool",
                    "step": step,
                    "argv": tool_result.argv,
                    "returncode": tool_result.returncode,
                    "elapsed_seconds": tool_result.elapsed_seconds,
                    "output_chars": len(tool_result.output),
                    "truncated": tool_result.truncated,
                }
            )
            observation = json.dumps(asdict(tool_result), ensure_ascii=False)
            messages.append({"role": "tool", "content": observation})
        raise RuntimeError("agent step limit exceeded")


def _write_metrics(path: Path, metrics: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in metrics:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--llama-cli", type=Path)
    parser.add_argument("--llama-model", type=Path)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--max-context-chars", type=int, default=8192)
    parser.add_argument("--max-observation-chars", type=int, default=2048)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--min-tokens", type=int, default=48)
    parser.add_argument("--slow-tps", type=float, default=2.0)
    parser.add_argument("--request-timeout", type=float, default=120)
    parser.add_argument("--tool-timeout", type=float, default=8)
    parser.add_argument("--total-timeout", type=float, default=300)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if bool(args.llama_cli) != bool(args.llama_model):
        raise SystemExit("--llama-cli and --llama-model must be provided together")
    if args.llama_cli:
        client: ModelClient = LlamaCliClient(args.llama_cli, args.llama_model, args.request_timeout)
    else:
        client = OpenAIChatClient(args.endpoint, args.model, args.request_timeout, os.environ.get(args.api_key_env))
    agent = EdgeAgent(
        client,
        RestrictedShell(args.cwd, DEFAULT_ALLOWED_COMMANDS, args.tool_timeout, 4096),
        ContextPolicy(args.max_context_chars, args.max_observation_chars),
        AdaptiveTokenBudget(args.max_tokens, args.min_tokens, args.slow_tps),
        args.max_steps,
        args.total_timeout,
    )
    try:
        answer = agent.run(args.prompt)
    finally:
        if args.metrics:
            _write_metrics(args.metrics, agent.metrics)
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
