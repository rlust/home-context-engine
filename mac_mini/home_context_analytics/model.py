"""Strict input models for whitelisted Home Context transition episodes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


MODES = frozenset(
    {
        "Active",
        "Away",
        "Entertaining",
        "Relaxing",
        "Sleeping",
        "Unknown",
        "Waking",
    }
)

ACTIVITIES = frozenset(
    {
        "Away",
        "Cooking",
        "Daily Life",
        "Dining",
        "Entertaining",
        "Listening to Music",
        "Sleeping",
        "Unknown",
        "Watching TV",
        "Working",
    }
)

ROOMS = frozenset(
    {
        "Basement Landing",
        "Basement",
        "Family Room",
        "Foyer",
        "Garage",
        "Kitchen",
        "Master Bath",
        "Master Bedroom",
        "Office",
        "Shop",
        "Theater",
        "Upstairs Hall",
    }
)

SIGNALS = frozenset(
    {
        "exterior_door",
        "music_playing",
        "observer_health",
        "recent_arrival",
        "resident_presence",
        "room_presence",
        "tv_active",
    }
)

SIGNAL_STATES = frozenset({"active", "inactive", "stale", "missing"})
RESIDENT_BUCKETS = frozenset({"none", "one", "multiple", "unknown"})
FEEDBACK_OUTCOMES = frozenset({"confirm", "wrong", "unsure"})

_EPISODE_KEYS = frozenset(
    {
        "kind",
        "source_event_id",
        "episode_id",
        "occurred_at",
        "mode",
        "activity",
        "confidence",
        "active_rooms",
        "resident_bucket",
        "signals",
        "observer_version",
    }
)

_FEEDBACK_KEYS = frozenset(
    {
        "kind",
        "source_event_id",
        "episode_id",
        "occurred_at",
        "outcome",
        "corrected_activity",
    }
)

_SENSITIVE_KEY_PARTS = (
    "audio",
    "camera",
    "credential",
    "gps",
    "latitude",
    "longitude",
    "message",
    "password",
    "person",
    "secret",
    "token",
)


class ValidationError(ValueError):
    """Raised when a record crosses the pilot's data boundary."""


def parse_timestamp(value: Any, field: str = "occurred_at") -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValidationError(f"{field} must be a non-empty string up to 128 characters")
    if any(character.isspace() for character in value):
        raise ValidationError(f"{field} must not contain whitespace")
    return value


def _reject_sensitive_keys(payload: Mapping[str, Any]) -> None:
    for key in payload:
        lowered = str(key).lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            raise ValidationError(f"sensitive field is not allowed: {key}")


def _require_exact_keys(payload: Mapping[str, Any], allowed: frozenset[str]) -> None:
    _reject_sensitive_keys(payload)
    unknown = set(payload) - allowed
    if unknown:
        raise ValidationError(f"unapproved fields: {', '.join(sorted(unknown))}")


@dataclass(frozen=True)
class Episode:
    source_event_id: str
    episode_id: str
    occurred_at: str
    mode: str
    activity: str
    confidence: int
    active_rooms: tuple[str, ...]
    resident_bucket: str
    signals: tuple[tuple[str, str], ...]
    observer_version: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Episode":
        _require_exact_keys(payload, _EPISODE_KEYS)
        if payload.get("kind") != "prediction":
            raise ValidationError("episode kind must be prediction")

        mode = payload.get("mode")
        if mode not in MODES:
            raise ValidationError(f"mode is not whitelisted: {mode!r}")
        activity = payload.get("activity")
        if activity not in ACTIVITIES:
            raise ValidationError(f"activity is not whitelisted: {activity!r}")

        confidence = payload.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
            raise ValidationError("confidence must be an integer from 0 to 100")

        rooms = payload.get("active_rooms")
        if not isinstance(rooms, list) or not all(isinstance(room, str) for room in rooms):
            raise ValidationError("active_rooms must be a list of room names")
        unknown_rooms = set(rooms) - ROOMS
        if unknown_rooms:
            raise ValidationError(f"rooms are not whitelisted: {', '.join(sorted(unknown_rooms))}")

        resident_bucket = payload.get("resident_bucket")
        if resident_bucket not in RESIDENT_BUCKETS:
            raise ValidationError(f"resident_bucket is not whitelisted: {resident_bucket!r}")

        raw_signals = payload.get("signals")
        if not isinstance(raw_signals, Mapping):
            raise ValidationError("signals must be an object")
        _reject_sensitive_keys(raw_signals)
        unknown_signals = set(raw_signals) - SIGNALS
        if unknown_signals:
            raise ValidationError(f"signals are not whitelisted: {', '.join(sorted(unknown_signals))}")
        omitted_signals = SIGNALS - set(raw_signals)
        if omitted_signals:
            raise ValidationError(
                f"signals must explicitly mark active, inactive, stale, or missing: {', '.join(sorted(omitted_signals))}"
            )
        invalid_states = {state for state in raw_signals.values() if state not in SIGNAL_STATES}
        if invalid_states:
            raise ValidationError("signal states must be active, inactive, stale, or missing")

        observer_version = payload.get("observer_version")
        if not isinstance(observer_version, str) or not observer_version or len(observer_version) > 128:
            raise ValidationError("observer_version must be a non-empty string up to 128 characters")

        return cls(
            source_event_id=_require_identifier(payload.get("source_event_id"), "source_event_id"),
            episode_id=_require_identifier(payload.get("episode_id"), "episode_id"),
            occurred_at=parse_timestamp(payload.get("occurred_at")),
            mode=mode,
            activity=activity,
            confidence=confidence,
            active_rooms=tuple(sorted(set(rooms))),
            resident_bucket=resident_bucket,
            signals=tuple(sorted((str(name), str(state)) for name, state in raw_signals.items())),
            observer_version=observer_version,
        )


@dataclass(frozen=True)
class Feedback:
    source_event_id: str
    episode_id: str
    occurred_at: str
    outcome: str
    corrected_activity: str | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Feedback":
        _require_exact_keys(payload, _FEEDBACK_KEYS)
        if payload.get("kind") != "feedback":
            raise ValidationError("feedback kind must be feedback")
        outcome = payload.get("outcome")
        if outcome not in FEEDBACK_OUTCOMES:
            raise ValidationError(f"feedback outcome is not whitelisted: {outcome!r}")
        corrected_activity = payload.get("corrected_activity")
        if outcome == "wrong":
            if corrected_activity not in ACTIVITIES:
                raise ValidationError("wrong feedback requires a whitelisted corrected_activity")
        elif corrected_activity is not None:
            raise ValidationError("corrected_activity is only allowed for wrong feedback")

        return cls(
            source_event_id=_require_identifier(payload.get("source_event_id"), "source_event_id"),
            episode_id=_require_identifier(payload.get("episode_id"), "episode_id"),
            occurred_at=parse_timestamp(payload.get("occurred_at")),
            outcome=outcome,
            corrected_activity=corrected_activity,
        )


def parse_record(payload: Any) -> Episode | Feedback:
    if not isinstance(payload, Mapping):
        raise ValidationError("each JSONL record must be an object")
    kind = payload.get("kind")
    if kind == "prediction":
        return Episode.from_payload(payload)
    if kind == "feedback":
        return Feedback.from_payload(payload)
    raise ValidationError("kind must be prediction or feedback; HA service events are never accepted")
