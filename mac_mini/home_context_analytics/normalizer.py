"""Transport-neutral Newark snapshot normalization with deterministic append output."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .fp300 import FP300Error, SOURCE_ID as FP300_SOURCE_ID, normalize_fp300
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

_SNAPSHOT_KEYS = frozenset({"snapshot_at", "observer_config", "entities", "source_context"})
_LEGACY_SNAPSHOT_KEYS = frozenset({"snapshot_at", "observer_config", "entities"})
_ENTITY_KEYS = frozenset({"state", "last_changed", "last_reported"})
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

POSITIVE_EVIDENCE_SECONDS = {
    "recent_arrival": 900,
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
    _parse_time(entity["last_reported"], f"{entity_id}.last_reported")
    return entity


def _binary_signal(
    entity: Mapping[str, str], now: datetime, threshold: int | None
) -> tuple[str, datetime]:
    state = entity["state"].strip().lower()
    if state in {"unknown", "unavailable"}:
        return "missing", _parse_time(entity["last_changed"], "last_changed")
    changed = _parse_time(entity["last_changed"], "last_changed")
    if state == "off":
        return "inactive", changed
    if state == "on":
        if threshold is None:
            return "active", changed
        reported = _parse_time(entity["last_reported"], "last_reported")
        stale_at = reported + timedelta(seconds=threshold)
        if now > stale_at:
            return "stale", stale_at
        return "active", changed
    raise SnapshotError("binary entity state must be on, off, unknown, or unavailable")


def _observer_signal(snapshot: Mapping[str, Any], now: datetime) -> tuple[str, datetime]:
    stalled_entity = _entity(snapshot, OBSERVER_STALLED)
    stalled_state = stalled_entity["state"].strip().lower()
    stalled_changed = _parse_time(stalled_entity["last_changed"], f"{OBSERVER_STALLED}.last_changed")
    if stalled_state in {"unknown", "unavailable", "on"}:
        return "missing", stalled_changed
    if stalled_state != "off":
        raise SnapshotError("Observer stalled state must be on, off, unknown, or unavailable")
    age_entity = _entity(snapshot, OBSERVER_AGE)
    age_state = age_entity["state"].strip().lower()
    age_changed = _parse_time(age_entity["last_changed"], f"{OBSERVER_AGE}.last_changed")
    if age_state in {"unknown", "unavailable"}:
        return "missing", age_changed
    try:
        age_minutes = float(age_state)
    except ValueError as exc:
        raise SnapshotError("observer age must be numeric, unknown, or unavailable") from exc
    return ("stale" if age_minutes > 10 else "active"), age_changed


def _summary_flags(value: str) -> tuple[str, ...]:
    lowered = value.lower()
    return tuple(sorted(flag for phrase, flag in _SUMMARY_FLAGS.items() if phrase in lowered))


def _next_activity(value: str) -> str | None:
    stripped = value.strip()
    return stripped if stripped in ACTIVITIES else None


def _opaque_digest(namespace: str, *parts: str) -> str:
    framed = json.dumps([namespace, *parts], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def _transition_components(prediction: Mapping[str, Any]) -> dict[str, Any]:
    return {
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


def _transition_key(semantic: Mapping[str, Any]) -> str:
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
                transition_time TEXT NOT NULL DEFAULT '',
                transition_components_json TEXT NOT NULL DEFAULT '{}',
                feedback_cursors_json TEXT NOT NULL,
                counter_snapshot_json TEXT NOT NULL
            )
            """
        )
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(normalizer_state)").fetchall()
        }
        if "transition_time" not in columns:
            self.connection.execute(
                "ALTER TABLE normalizer_state ADD COLUMN transition_time TEXT NOT NULL DEFAULT ''"
            )
        if "transition_components_json" not in columns:
            self.connection.execute(
                "ALTER TABLE normalizer_state ADD COLUMN transition_components_json TEXT NOT NULL DEFAULT '{}'"
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
        transition_time: str,
        transition_components: Mapping[str, Any],
        feedback_cursors: Mapping[str, str | None],
        counters: Mapping[str, int],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO normalizer_state(
                singleton, transition_key, episode_id, snapshot_at,
                transition_time, transition_components_json,
                feedback_cursors_json, counter_snapshot_json
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
                transition_key = excluded.transition_key,
                episode_id = excluded.episode_id,
                snapshot_at = excluded.snapshot_at,
                transition_time = excluded.transition_time,
                transition_components_json = excluded.transition_components_json,
                feedback_cursors_json = excluded.feedback_cursors_json,
                counter_snapshot_json = excluded.counter_snapshot_json
            """,
            (
                transition_key,
                episode_id,
                snapshot_at,
                transition_time,
                json.dumps(transition_components, sort_keys=True, separators=(",", ":")),
                json.dumps(feedback_cursors, sort_keys=True, separators=(",", ":")),
                json.dumps(counters, sort_keys=True, separators=(",", ":")),
            ),
        )
        self.connection.commit()


def validate_snapshot(snapshot: Any) -> Mapping[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise SnapshotError("snapshot must be an object")
    snapshot_keys = set(snapshot)
    if snapshot_keys not in {_SNAPSHOT_KEYS, _LEGACY_SNAPSHOT_KEYS}:
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
        entity = _entity(snapshot, entity_id)
        for timestamp_field in ("last_changed", "last_reported"):
            if _parse_time(entity[timestamp_field], f"{entity_id}.{timestamp_field}") > _parse_time(
                snapshot["snapshot_at"], "snapshot_at"
            ):
                raise SnapshotError(f"{entity_id}.{timestamp_field} cannot be after snapshot_at")
    if "source_context" in snapshot:
        source_context = snapshot["source_context"]
        if not isinstance(source_context, Mapping) or set(source_context) != {FP300_SOURCE_ID}:
            raise SnapshotError(f"source_context must contain only {FP300_SOURCE_ID}")
        try:
            normalize_fp300(
                source_context[FP300_SOURCE_ID],
                _parse_time(snapshot["snapshot_at"], "snapshot_at"),
            )
        except FP300Error as exc:
            raise SnapshotError(str(exc)) from exc
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
    signal_results = {
        name: _binary_signal(
            _entity(snapshot, entity_id), snapshot_time, POSITIVE_EVIDENCE_SECONDS.get(name)
        )
        for name, entity_id in SIGNAL_ENTITY.items()
        if name != "observer_health"
    }
    signal_results["observer_health"] = _observer_signal(snapshot, snapshot_time)
    signals = {name: result[0] for name, result in signal_results.items()}
    if room_state in {"missing", "inactive"}:
        signals["room_presence"] = room_state
        signal_results["room_presence"] = (
            room_state,
            _parse_time(
                _entity(snapshot, ACTIVE_ROOMS)["last_changed"], f"{ACTIVE_ROOMS}.last_changed"
            ),
        )

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
        "fp300_context": (
            normalize_fp300(snapshot["source_context"][FP300_SOURCE_ID], snapshot_time)
            if "source_context" in snapshot
            else None
        ),
    }
    semantic = _transition_components(prediction)
    transition_key = _transition_key(semantic)
    prior = state.load()
    if prior and snapshot_time < _parse_time(prior["snapshot_at"], "prior snapshot"):
        raise SnapshotError("snapshot_at cannot move backward")
    records: list[dict[str, Any]] = []
    new_transition = prior is None or prior["transition_key"] != transition_key
    if new_transition:
        prior_semantic = json.loads(prior["transition_components_json"]) if prior else {}
        component_times = {
            "mode": _parse_time(_entity(snapshot, MODE)["last_changed"], f"{MODE}.last_changed"),
            "activity": _parse_time(_entity(snapshot, ACTIVITY)["last_changed"], f"{ACTIVITY}.last_changed"),
            "confidence_band": _parse_time(_entity(snapshot, CONFIDENCE)["last_changed"], f"{CONFIDENCE}.last_changed"),
            "active_rooms": _parse_time(_entity(snapshot, ACTIVE_ROOMS)["last_changed"], f"{ACTIVE_ROOMS}.last_changed"),
            "resident_bucket": signal_results["resident_presence"][1],
            "context_flags": _parse_time(_entity(snapshot, SUMMARY)["last_changed"], f"{SUMMARY}.last_changed"),
            "next_activity": _parse_time(_entity(snapshot, NEXT_ACTIVITY)["last_changed"], f"{NEXT_ACTIVITY}.last_changed"),
            "observer_version": snapshot_time,
        }
        changed_times = [
            component_times[name]
            for name in component_times
            if prior is None or prior_semantic.get(name) != semantic[name]
        ]
        prior_signals = prior_semantic.get("signals", {})
        changed_times.extend(
            signal_results[name][1]
            for name in signals
            if prior is None or prior_signals.get(name) != signals[name]
        )
        transition_datetime = max(changed_times, default=snapshot_time)
        transition_time = transition_datetime.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        current_episode_id = _opaque_digest("episode", observer_version, transition_key, transition_time)
        prediction["episode_id"] = current_episode_id
        prediction["source_event_id"] = _opaque_digest("prediction", current_episode_id, transition_time)
        prediction["occurred_at"] = transition_time
        parse_record(prediction)
        records.append(prediction)
    else:
        current_episode_id = prior["episode_id"]
        transition_time = prior["transition_time"] or prior["snapshot_at"]

    previous_cursors = json.loads(prior["feedback_cursors_json"]) if prior else {}
    current_cursors: dict[str, str | None] = {}
    emitted_feedback_outcomes: list[str] = []
    feedback_specs = (
        ("confirm", CONFIRM, None),
        ("wrong", WRONG, _entity(snapshot, CORRECTED)["state"]),
        ("unsure", UNSURE, None),
    )
    for outcome, entity_id, corrected_activity in feedback_specs:
        entity = _entity(snapshot, entity_id)
        raw_cursor = entity["state"].strip()
        if raw_cursor.lower() in {"unknown", "unavailable"}:
            current_cursors[outcome] = previous_cursors.get(outcome)
            continue
        cursor = parse_timestamp(raw_cursor, f"{entity_id}.state")
        if _parse_time(cursor, "feedback cursor") > snapshot_time:
            raise SnapshotError("feedback button state timestamp cannot be after snapshot_at")
        current_cursors[outcome] = cursor
        if previous_cursors.get(outcome) == cursor:
            continue
        if prior is None:
            continue
        if _parse_time(cursor, "feedback cursor") <= _parse_time(prior["snapshot_at"], "prior snapshot"):
            continue
        feedback_episode_id = current_episode_id
        if new_transition and _parse_time(cursor, "feedback cursor") < _parse_time(
            transition_time, "transition time"
        ):
            feedback_episode_id = prior["episode_id"]
        audit_issues: list[str] = []
        if outcome == "wrong":
            corrected_changed = _parse_time(
                _entity(snapshot, CORRECTED)["last_changed"], f"{CORRECTED}.last_changed"
            )
            if corrected_changed <= _parse_time(prior["snapshot_at"], "prior snapshot"):
                audit_issues.append("corrected_activity_stale")
            if corrected_changed > _parse_time(cursor, "feedback cursor"):
                audit_issues.append("corrected_activity_after_press")
        feedback = {
            "kind": "feedback",
            "source_event_id": _opaque_digest("feedback", feedback_episode_id, outcome, cursor),
            "episode_id": feedback_episode_id,
            "occurred_at": cursor,
            "outcome": outcome,
            "corrected_activity": corrected_activity if outcome == "wrong" else None,
            "audit_consistent": not audit_issues,
            "audit_issues": audit_issues,
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
        "feedback_audit_failures": sum(
            not record["audit_consistent"]
            for record in records
            if record["kind"] == "feedback"
        ),
        "pending_state": {
            "transition_key": transition_key,
            "episode_id": current_episode_id,
            "snapshot_at": snapshot_at,
            "transition_time": transition_time,
            "transition_components": semantic,
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
