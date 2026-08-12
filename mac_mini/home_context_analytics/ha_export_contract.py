"""Deterministic mirror of the review-only Home Assistant export gate.

Keep this gate synchronized with the observer and feedback branches in
``home_assistant/home_context_snapshot_push.yaml.example``. Structural tests
verify the shared helper set, freshness comparison, and inactive-Observer rule.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from .model import parse_timestamp


PREDICTION_HELPERS = (
    "input_select.home_context_mode",
    "input_select.home_current_activity",
    "input_number.home_context_confidence",
    "input_text.home_context_summary",
    "input_text.home_next_likely_activity",
)
REVIEWED_OBSERVER_CONFIG_HASH = "6b5fa7a109f6636a"
REVIEWED_OBSERVER_MODE = "restart"
NON_OVERLAPPING_OBSERVER_MODES = frozenset({"single", "restart"})


def export_ready(
    trigger_branch: str,
    *,
    observer_event_time: str | None,
    helper_last_reported: Mapping[str, str],
    observer_active: bool | None,
) -> bool:
    """Return the exact fail-closed decision mirrored by the HA draft."""

    if trigger_branch == "feedback":
        return observer_active is False
    if (
        trigger_branch != "observer"
        or observer_event_time is None
        or observer_active is not False
    ):
        return False
    if set(helper_last_reported) != set(PREDICTION_HELPERS):
        return False
    event_time = _datetime(observer_event_time, "observer_event_time")
    return all(
        _datetime(helper_last_reported[entity_id], f"{entity_id}.last_reported") >= event_time
        for entity_id in PREDICTION_HELPERS
    )


def _datetime(value: str, field: str) -> datetime:
    normalized = parse_timestamp(value, field)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
