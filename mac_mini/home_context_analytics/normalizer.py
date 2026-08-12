"""Transport-neutral Newark snapshot normalization with deterministic append output."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .model import (
    ACTIVITIES,
    FEEDBACK_OUTCOMES,
    MODES,
    ValidationError,
    normalize_ha_active_rooms,
    normalize_ha_confidence,
    parse_record,
    parse_timestamp,
)


MODE = "input_select.home_context_mode"
ACTIVITY = "input_select.home_current_activity"
CONFIDENCE = "input_number.home_context_confidence"
ACTIVE_ROOMS = "sensor.home_active_room"
SUMMARY = "input_text.home_context_summary"
NEXT_ACTIVITY = "input_text.home_next_likely_activity"
AI_ACTIONS = "input_boolean.ai_actions_enabled"
OBSERVER_AGE = "sensor.home_context_observer_age"
OBSERVER_STALLED = "binary_sensor.home_context_engine_stalled"
RESIDENTS = "binary_sensor.residents_home"
ROOM_PRESENCE = "binary_sensor.home_room_presence"
TV = "binary_sensor.tv_active"
MUSIC = "binary_sensor.music_playing"
DOOR = "binary_sensor.exterior_door_open"
ARRIVAL = "binary_sensor.recent_arrival"
CONFIRM = "input_button.home_context_confirm"
WRONG = "input_button.home_context_mark_wrong"
UNSURE = "input_button.home_context_mark_unsure"
CORRECTED = "input_select.home_context_corrected_activity"
CONFIRMATIONS = "counter.home_context_confirmations"
CORRECTIONS = "counter.home_context_corrections"
UNSURE_COUNT = "counter.home_context_unsure"

REQUIRED_ENTITIES = frozenset(
    {
        MODE,
        ACTIVITY,
        CONFIDENCE,
        ACTIVE_ROOMS,
        SUMMARY,
        NEXT_ACTIVITY,
        AI_ACTIONS,
        OBSERVER_AGE,
        OBSERVER_STALLED,
        RESIDENTS,
        ROOM_PRESENCE,
        TV,
        MUSIC,
        DOOR,
        ARRIVAL,
        CONFIRM,
        WRONG,
        UNSURE,
        CORRECTED,
        CONFIRMATIONS,
        CORRECTIONS,
        UNSURE_COUNT,
    }
)

_SNAPSHOT_KEYS = frozenset({"snapshot_at", "observer_config", "entities"})
_ENTITY_KEYS = frozenset({"state", "last_changed"})
_OBSERVER_KEYS = frozenset({"automation_id", "config_sha256", "version"})
_FORBIDDEN_TOP_LEVEL = frozenset({"event", "service", "services", "url", "token", "websocket", "mcp"})

SIGNAL_ENTITY = {
    "exterior_door": DOOR,
    "music_playing": MUSIC,
    "observer_health": OBSERVER_STALLED,
    "recent_arrival": ARRIVAL,
    "resident_presence": RESIDENTS,
    "room_presence": ROOM_PRESENCE,
    "tv_active": TV,
}

FRESHNESS_SECONDS = {
    "exterior_door": 900,
    "music_playing": 900,
    "observer_health": 900,
    "recent_arrival": 900,
    "resident_presence": 1800,
    "room_presence": 900,
    "tv_active": 900,
}

_SUMMARY_FLAGS = {
    "conflict": "summary_conflict",
    "door": "summary_door",
    "media": "summary_media",
    "missing": "summary_missing",
    "recent arrival": "summary_recent_arrival",
    "stale": "summary_stale",
}


class SnapshotError(ValidationError):
    """Raised when a supplied snapshot crosses the normalizer boundary."""


def _exact_keys(payload: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = set(payload)
    unknown = actual - expected
    missing = expected - actual
    forbidden = actual & _FORBIDDEN_TOP_LEVEL
    if forbidden:
        raise SnapshotError(f"{label} contains forbidden transport/service fields")
    if unknown:
        raise SnapshotError(f"{label} contains unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise SnapshotError(f"{label} is missing required fields: {', '.join(sorted(missing))}")


def _parse_time(value: Any, label: str) -> datetime:
    normalized = parse_timestamp(value, label)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _observer_digest(observer_config: Any) -> str:
    if not isinstance(observer_config, Mapping):
        raise SnapshotError("observer_config must be a reviewed structured object")
    _exact_keys(observer_config, _OBSERVER_KEYS, "observer_config")
    if observer_config["automation_id"] != "automation.home_context_evening_observer":
        raise SnapshotError("observer_config automation_id is not the reviewed observer")
    for field in ("config_sha256", "version"):
        value = observer_config[field]
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise SnapshotError(f"observer_config.{field} must be a lowercase SHA-256 digest")
    serialized = json.dumps(observer_config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _entity(snapshot: Mapping[str, Any], entity_id: str) -> Mapping[str, str]:
    entity = snapshot["entities"][entity_id]
    if not isinstance(entity, Mapping):
        raise SnapshotError(f"{entity_id} must be an object")
    _exact_keys(entity, _ENTITY_KEYS, entity_id)
    if not isinstance(entity["state"], str):
        raise SnapshotError(f"{entity_id}.state must be a string")
    _parse_time(entity["last_changed"], f"{entity_id}.last_changed")
    return entity


def _binary_signal(entity: Mapping[str, str], now: datetime, threshold: int) -> str:
    state = entity["state"].strip().lower()
    if state in {"unknown", "unavailable"}:
        return "missing"
    changed = _parse_time(entity["last_changed"], "last_changed")
    age = (now - changed).total_seconds()
    if age < 0:
        raise SnapshotError("entity last_changed cannot be after snapshot_at")
    if age > threshold:
        return "stale"
    if state == "on":
        return "active"
    if state == "off":
        return "inactive"
    raise SnapshotError("binary entity state must be on, off, unknown, or unavailable")


def _observer_signal(snapshot: Mapping[str, Any], now: datetime) -> str:
    stalled = _binary_signal(_entity(snapshot, OBSERVER_STALLED), now, FRESHNESS_SECONDS["observer_health"])
    if stalled in {"missing", "stale"}:
        return stalled
    if stalled == "active":
        return "missing"
    age_state = _entity(snapshot, OBSERVER_AGE)["state"].strip().lower()
    if age_state in {"unknown", "unavailable"}:
        return "missing"
    try:
        age_minutes = float(age_state)
    except ValueError as exc:
        raise SnapshotError("observer age must be numeric, unknown, or unavailable") from exc
    return "stale" if age_minutes > 10 else "active"


def _summary_flags(value: str) -> tuple[str, ...]:
    lowered = value.lower()
    return tuple(sorted(flag for phrase, flag in _SUMMARY_FLAGS.items() if phrase in lowered))


def _next_activity(value: str) -> str | None:
    stripped = value.strip()
    return stripped if stripped in ACTIVITIES else None


def _opaque_digest(namespace: str, *parts: str) -> str:
    framed = json.dumps([namespace, *parts], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def _transition_key(prediction: Mapping[str, Any]) -> str:
    semantic = {
        "mode": prediction["mode"],
        "activity": prediction["activity"],
        "confidence_band": prediction["confidence"] // 5,
        "active_rooms": prediction["active_rooms"],
        "resident_bucket": prediction["resident_bucket"],
        "signals": prediction["signals"],
        "context_flags": prediction["context_flags"],
        "next_activity": prediction["next_activity"],
        "observer_version": prediction["observer_version"],
    }
    return hashlib.sha256(
        json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class NormalizerState:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS normalizer_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                transition_key TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                snapshot_at TEXT NOT NULL,
                feedback_cursors_json TEXT NOT NULL,
                counter_snapshot_json TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        os.chmod(path, 0o600)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "NormalizerState":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def load(self) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM normalizer_state WHERE singleton = 1").fetchone()

    def save(
        self,
        *,
        transition_key: str,
        episode_id: str,
        snapshot_at: str,
        feedback_cursors: Mapping[str, str],
        counters: Mapping[str, int],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO normalizer_state(
                singleton, transition_key, episode_id, snapshot_at,
                feedback_cursors_json, counter_snapshot_json
            ) VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
                transition_key = excluded.transition_key,
                episode_id = excluded.episode_id,
                snapshot_at = excluded.snapshot_at,
                feedback_cursors_json = excluded.feedback_cursors_json,
                counter_snapshot_json = excluded.counter_snapshot_json
            """,
            (
                transition_key,
                episode_id,
                snapshot_at,
                json.dumps(feedback_cursors, sort_keys=True, separators=(",", ":")),
                json.dumps(counters, sort_keys=True, separators=(",", ":")),
            ),
        )
        self.connection.commit()


def validate_snapshot(snapshot: Any) -> Mapping[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise SnapshotError("snapshot must be an object")
    _exact_keys(snapshot, _SNAPSHOT_KEYS, "snapshot")
    entities = snapshot["entities"]
    if not isinstance(entities, Mapping):
        raise SnapshotError("entities must be an object")
    actual_entities = set(entities)
    unknown = actual_entities - REQUIRED_ENTITIES
    missing = REQUIRED_ENTITIES - actual_entities
    if unknown:
        raise SnapshotError(f"snapshot contains entities outside allowlist: {', '.join(sorted(unknown))}")
    if missing:
        raise SnapshotError(f"snapshot is missing required entities: {', '.join(sorted(missing))}")
    _parse_time(snapshot["snapshot_at"], "snapshot_at")
    _observer_digest(snapshot["observer_config"])
    for entity_id in REQUIRED_ENTITIES:
        _entity(snapshot, entity_id)
    return snapshot


def normalize_snapshot(snapshot: Any, state: NormalizerState) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build records and pending state without writing output or advancing state."""
    snapshot = validate_snapshot(snapshot)
    snapshot_time = _parse_time(snapshot["snapshot_at"], "snapshot_at")
    snapshot_at = snapshot_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    mode = _entity(snapshot, MODE)["state"]
    activity = _entity(snapshot, ACTIVITY)["state"]
    if mode not in MODES:
        raise SnapshotError("mode is not whitelisted")
    if activity not in ACTIVITIES:
        raise SnapshotError("activity is not whitelisted")
    confidence = normalize_ha_confidence(_entity(snapshot, CONFIDENCE)["state"])
    rooms, room_state = normalize_ha_active_rooms(_entity(snapshot, ACTIVE_ROOMS)["state"])
    signals = {
        name: _binary_signal(_entity(snapshot, entity_id), snapshot_time, FRESHNESS_SECONDS[name])
        for name, entity_id in SIGNAL_ENTITY.items()
        if name != "observer_health"
    }
    signals["observer_health"] = _observer_signal(snapshot, snapshot_time)
    signals["room_presence"] = room_state if room_state in {"missing", "inactive"} else signals["room_presence"]

    resident_bucket = "none" if signals["resident_presence"] == "inactive" else "unknown"
    observer_version = _observer_digest(snapshot["observer_config"])
    actions_state = _entity(snapshot, AI_ACTIONS)["state"].strip().lower()
    if actions_state != "off":
        raise SnapshotError("ai_actions_enabled must be off for this observe-only pilot")
    summary = _entity(snapshot, SUMMARY)["state"]
    prediction: dict[str, Any] = {
        "kind": "prediction",
        "source_event_id": "",
        "episode_id": "",
        "occurred_at": snapshot_at,
        "mode": mode,
        "activity": activity,
        "confidence": confidence,
        "active_rooms": list(rooms),
        "resident_bucket": resident_bucket,
        "signals": dict(sorted(signals.items())),
        "observer_version": observer_version,
        "context_flags": list(_summary_flags(summary)),
        "next_activity": _next_activity(_entity(snapshot, NEXT_ACTIVITY)["state"]),
    }
    transition_key = _transition_key(prediction)
    prior = state.load()
    if prior and snapshot_time < _parse_time(prior["snapshot_at"], "prior snapshot"):
        raise SnapshotError("snapshot_at cannot move backward")
    records: list[dict[str, Any]] = []
    if prior is None or prior["transition_key"] != transition_key:
        current_episode_id = _opaque_digest("episode", observer_version, transition_key, snapshot_at)
        prediction["episode_id"] = current_episode_id
        prediction["source_event_id"] = _opaque_digest("prediction", current_episode_id, snapshot_at)
        parse_record(prediction)
        records.append(prediction)
    else:
        current_episode_id = prior["episode_id"]

    feedback_episode_id = prior["episode_id"] if prior else current_episode_id

    previous_cursors = json.loads(prior["feedback_cursors_json"]) if prior else {}
    current_cursors: dict[str, str] = {}
    emitted_feedback_outcomes: list[str] = []
    feedback_specs = (
        ("confirm", CONFIRM, None),
        ("wrong", WRONG, _entity(snapshot, CORRECTED)["state"]),
        ("unsure", UNSURE, None),
    )
    for outcome, entity_id, corrected_activity in feedback_specs:
        entity = _entity(snapshot, entity_id)
        cursor = parse_timestamp(entity["last_changed"], f"{entity_id}.last_changed")
        current_cursors[outcome] = cursor
        if previous_cursors.get(outcome) == cursor:
            continue
        if prior is None:
            continue
        if _parse_time(cursor, "feedback cursor") <= _parse_time(prior["snapshot_at"], "prior snapshot"):
            continue
        feedback = {
            "kind": "feedback",
            "source_event_id": _opaque_digest("feedback", feedback_episode_id, outcome, cursor),
            "episode_id": feedback_episode_id,
            "occurred_at": cursor,
            "outcome": outcome,
            "corrected_activity": corrected_activity if outcome == "wrong" else None,
        }
        parse_record(feedback)
        records.append(feedback)
        emitted_feedback_outcomes.append(outcome)

    counters = {}
    for label, entity_id in (
        ("confirm", CONFIRMATIONS),
        ("wrong", CORRECTIONS),
        ("unsure", UNSURE_COUNT),
    ):
        raw = _entity(snapshot, entity_id)["state"]
        try:
            value = int(raw)
        except ValueError as exc:
            raise SnapshotError(f"{entity_id} must be an integer counter") from exc
        if value < 0:
            raise SnapshotError(f"{entity_id} must be non-negative")
        counters[label] = value
    prior_counters = json.loads(prior["counter_snapshot_json"]) if prior else counters
    audit_consistent = all(counters[name] >= prior_counters.get(name, 0) for name in counters)
    if prior:
        emitted_counts = {
            outcome: emitted_feedback_outcomes.count(outcome) for outcome in FEEDBACK_OUTCOMES
        }
        audit_consistent = audit_consistent and all(
            counters[outcome] - prior_counters.get(outcome, 0) == emitted_counts[outcome]
            for outcome in emitted_counts
        )

    return records, {
        "records": len(records),
        "prediction_created": any(record["kind"] == "prediction" for record in records),
        "feedback_created": sum(record["kind"] == "feedback" for record in records),
        "counter_audit_consistent": audit_consistent,
        "pending_state": {
            "transition_key": transition_key,
            "episode_id": current_episode_id,
            "snapshot_at": snapshot_at,
            "feedback_cursors": current_cursors,
            "counters": counters,
        },
    }


def append_records(path: Path, records: list[dict[str, Any]], *, output_mode: str = "append") -> int:
    if output_mode != "append":
        raise SnapshotError("output_mode must be true append; atomic replace is forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise SnapshotError("append output must be a regular file, not a symlink or special file")
        if metadata.st_size and not _ends_with_newline(path):
            raise SnapshotError("append output has an incomplete final line; repair it before continuing")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if records:
            content = "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records)
            encoded = content.encode("utf-8")
            written = 0
            while written < len(encoded):
                written += os.write(descriptor, encoded[written:])
            os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    return len(records)


def _ends_with_newline(path: Path) -> bool:
    with path.open("rb") as stream:
        stream.seek(-1, os.SEEK_END)
        return stream.read(1) == b"\n"


def normalize_and_append(
    snapshot: Any,
    state: NormalizerState,
    output_path: Path,
    *,
    output_mode: str = "append",
) -> dict[str, Any]:
    """Append complete records before advancing normalization state."""

    if output_path.resolve() == state.path.resolve():
        raise SnapshotError("normalizer state database and append output must be different files")
    records, result = normalize_snapshot(snapshot, state)
    append_records(output_path, records, output_mode=output_mode)
    pending = result.pop("pending_state")
    state.save(**pending)
    return result
