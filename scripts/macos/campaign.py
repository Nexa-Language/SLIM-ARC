#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


SCHEMA_VERSION = 1
TERMINATION_GRACE_SECONDS = 30


class CampaignExpired(RuntimeError):
    """Raised when no campaign time remains for a new process."""


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")


@dataclass(frozen=True)
class CampaignWindow:
    started_at: datetime
    deadline_at: datetime

    @classmethod
    def start(cls, hours: int, now: datetime | None = None) -> CampaignWindow:
        if hours <= 0:
            raise ValueError("campaign hours must be positive")
        start_time = now or datetime.now(timezone.utc)
        _require_aware(start_time)
        return cls(
            started_at=start_time, deadline_at=start_time + timedelta(hours=hours)
        )

    @classmethod
    def load(cls, path: Path) -> CampaignWindow:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported campaign schema version")
        started_at = datetime.fromisoformat(payload["started_at"])
        deadline_at = datetime.fromisoformat(payload["deadline_at"])
        _require_aware(started_at)
        _require_aware(deadline_at)
        if deadline_at <= started_at:
            raise ValueError("campaign deadline must follow start time")
        return cls(started_at=started_at, deadline_at=deadline_at)

    def save(self, path: Path) -> None:
        _require_aware(self.started_at)
        _require_aware(self.deadline_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "started_at": self.started_at.isoformat(),
            "deadline_at": self.deadline_at.isoformat(),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(path, flags, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")

    def remaining_seconds(self, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        _require_aware(current)
        return max(0, int((self.deadline_at - current).total_seconds()))


def load_or_start(
    path: Path, hours: int, now: datetime | None = None
) -> CampaignWindow:
    if path.exists():
        return CampaignWindow.load(path)
    window = CampaignWindow.start(hours=hours, now=now)
    window.save(path)
    return window


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_with_deadline(
    argv: Sequence[str], window: CampaignWindow, now: datetime | None = None
) -> int:
    if not argv:
        raise ValueError("command argv must not be empty")
    remaining = window.remaining_seconds(now)
    if remaining <= 0:
        raise CampaignExpired("campaign deadline has passed")

    process = subprocess.Popen(list(argv), start_new_session=True)
    try:
        return process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        return 124


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist and enforce the SLIM-ARC overnight campaign deadline."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--hours", type=int, required=True)
    start_parser.add_argument("--state", type=Path, required=True)

    remaining_parser = subparsers.add_parser("remaining")
    remaining_parser.add_argument("--state", type=Path, required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--state", type=Path, required=True)
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.action == "start":
        window = load_or_start(args.state, hours=args.hours)
        print(
            json.dumps(
                {
                    "started_at": window.started_at.isoformat(),
                    "deadline_at": window.deadline_at.isoformat(),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.action == "remaining":
        print(CampaignWindow.load(args.state).remaining_seconds())
        return 0

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    try:
        return run_with_deadline(command, CampaignWindow.load(args.state))
    except CampaignExpired as exc:
        print(str(exc), file=sys.stderr)
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
