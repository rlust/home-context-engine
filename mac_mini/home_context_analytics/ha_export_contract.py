"""Deterministic mirror of the review-only Home Assistant export gate."""

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


def export_ready(
    trigger_branch: str,
    *,
    observer_event_time: str | None,
    observer_context_id: str | None = None,
    helper_last_reported: Mapping[str, str],
    helper_context_ids: Mapping[str, str] | None = None,
    observer_active: bool = False,
) -> bool:
    """Return the exact fail-closed decision mirrored by the HA draft."""

    if trigger_branch == "feedback":
        return not observer_active
    if (
        trigger_branch != "observer"
        or observer_event_time is None
        or not observer_context_id
        or helper_context_ids is None
    ):
        return False
    if set(helper_last_reported) != set(PREDICTION_HELPERS) or set(helper_context_ids) != set(
        PREDICTION_HELPERS
    ):
        return False
    event_time = _datetime(observer_event_time, "observer_event_time")
    return all(
        _datetime(helper_last_reported[entity_id], f"{entity_id}.last_reported") >= event_time
        and helper_context_ids[entity_id] == observer_context_id
        for entity_id in PREDICTION_HELPERS
    )


def _datetime(value: str, field: str) -> datetime:
    normalized = parse_timestamp(value, field)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
