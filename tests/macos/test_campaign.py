from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "macos" / "campaign.py"
SPEC = importlib.util.spec_from_file_location("slim_arc_campaign", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
campaign = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = campaign
SPEC.loader.exec_module(campaign)


def test_campaign_has_one_fixed_twelve_hour_deadline(tmp_path: Path) -> None:
    now = datetime(2026, 8, 11, 20, tzinfo=timezone.utc)
    window = campaign.CampaignWindow.start(hours=12, now=now)
    state_path = tmp_path / "campaign.json"
    window.save(state_path)

    loaded = campaign.CampaignWindow.load(state_path)

    assert loaded.deadline_at - loaded.started_at == timedelta(hours=12)
    assert loaded.remaining_seconds(now + timedelta(hours=1)) == 11 * 3600


def test_existing_campaign_is_not_extended(tmp_path: Path) -> None:
    state_path = tmp_path / "campaign.json"
    first_start = datetime(2026, 8, 11, 20, tzinfo=timezone.utc)
    first = campaign.load_or_start(state_path, hours=12, now=first_start)

    second = campaign.load_or_start(
        state_path, hours=12, now=first_start + timedelta(hours=2)
    )

    assert second.started_at == first.started_at
    assert second.deadline_at == first.deadline_at


def test_expired_campaign_refuses_new_process() -> None:
    start = datetime(2026, 8, 11, tzinfo=timezone.utc)
    window = campaign.CampaignWindow.start(hours=12, now=start)

    with pytest.raises(campaign.CampaignExpired):
        campaign.run_with_deadline(
            ["/usr/bin/true"], window, now=start + timedelta(hours=13)
        )


def test_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        campaign.CampaignWindow.start(hours=12, now=datetime(2026, 8, 11))


def test_rejects_non_positive_duration() -> None:
    with pytest.raises(ValueError, match="positive"):
        campaign.CampaignWindow.start(hours=0, now=datetime.now(timezone.utc))
