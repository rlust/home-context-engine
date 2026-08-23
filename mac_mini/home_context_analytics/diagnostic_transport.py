"""Bounded Garage observations and sanitized diagnostics return payloads."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .diagnostics import DiagnosticReplay, detect_signal_issues, diagnostic_report_payload
from .issue_card import IssueCardState, build_issue_card_payload


SOURCE_ID = "garage-diagnostics-v1"
DIAGNOSTICS_PATH = "/v1/home-context/diagnostics"
MAX_REPORT_AGE_SECONDS = 600
MAX_REPORT_BYTES = 32_768

HELPER_ID = "binary_sensor.garage_occupied"
HELPER_CONFIG_ENTRY_ID = "01KZHASWE6S7W7NE177MHX89AF"
HELPER_NAME = "Garage Occupied"
HELPER_TEMPLATE = (
    "{{ is_state('binary_sensor.pir_motion_sensor_2_sensor_state_motion','on') "
    "or is_state('binary_sensor.gdo1_motion','on') "
    "or is_state('binary_sensor.grgdo1_motion','on') }}"
)
HELPER_CONFIG_SHA256 = "78ab0c78b8859d48eb13549eca77484db9e2036140272fccde20c797e74880dc"
DOWNSTREAM_ID = "sensor.home_active_room"

SIGNAL_METADATA: dict[str, dict[str, Any]] = {
    "binary_sensor.pir_motion_sensor_2_motion_detection": {
        "device_id": "9b912d57150b1ec3b24111935fe24a76",
        "device_class": "motion",
        "semantic": "event",
        "required": False,
        "max_age_seconds": None,
    },
    "binary_sensor.pir_motion_sensor_2_sensor_state_motion": {
        "device_id": "9b912d57150b1ec3b24111935fe24a76",
        "device_class": "motion",
        "semantic": "state",
        "required": True,
        # This Z-Wave state output reports transitions, not heartbeats. Availability
        # and endpoint freshness are enforced separately; elapsed state age alone is
        # not evidence of a failed source.
        "max_age_seconds": None,
    },
    "binary_sensor.gdo1_motion": {
        "device_id": "0f4a9d838ba99509628189e2c7fbbfec",
        "device_class": "motion",
        "semantic": "state",
        "required": True,
        "max_age_seconds": None,
    },
    "binary_sensor.grgdo1_motion": {
        "device_id": "7b9975133f3cf0f414bdc4f3f41eeb1e",
        "device_class": "motion",
        "semantic": "state",
        "required": True,
        "max_age_seconds": None,
    },
}
CANONICAL_SOURCE_IDS = (
    "binary_sensor.pir_motion_sensor_2_sensor_state_motion",
    "binary_sensor.gdo1_motion",
    "binary_sensor.grgdo1_motion",
)
_SAMPLE_KEYS = frozenset({"state", "last_changed", "last_reported"})
_HELPER_KEYS = frozenset(
    {"config_entry_id", "config_sha256", "entity_id", "device_class", "source_entity_ids", "state", "last_changed", "last_reported"}
)
_DOWNSTREAM_KEYS = frozenset({"entity_id", "state", "last_changed", "last_reported"})
_BINARY_STATES = frozenset({"on", "off", "unknown", "unavailable"})


class DiagnosticTransportError(ValueError):
    """A fail-closed diagnostics transport boundary error."""


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise DiagnosticTransportError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DiagnosticTransportError(f"{field} must be valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DiagnosticTransportError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _time_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sample(payload: Any, *, entity_id: str, observed_at: datetime) -> dict[str, str]:
    if not isinstance(payload, Mapping) or set(payload) != _SAMPLE_KEYS:
        raise DiagnosticTransportError(f"{entity_id} fields do not match the observation contract")
    state = payload.get("state")
    if state not in _BINARY_STATES:
        raise DiagnosticTransportError(f"{entity_id} state is not approved")
    changed = _time(payload.get("last_changed"), f"{entity_id}.last_changed")
    reported = _time(payload.get("last_reported"), f"{entity_id}.last_reported")
    if changed > observed_at or reported > observed_at:
        raise DiagnosticTransportError(f"{entity_id} timestamp cannot be after observed_at")
    return {
        "state": state,
        "last_changed": _time_text(changed),
        "last_reported": _time_text(reported),
    }


def validate_diagnostic_source(payload: Any, observed_at: datetime) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "helper", "signals", "downstream"}:
        raise DiagnosticTransportError("Garage diagnostic source fields do not match the approved contract")
    if payload.get("schema_version") != 1:
        raise DiagnosticTransportError("Garage diagnostic source requires schema_version 1")
    helper = payload.get("helper")
    if not isinstance(helper, Mapping) or set(helper) != _HELPER_KEYS:
        raise DiagnosticTransportError("Garage helper fields do not match the approved contract")
    expected_helper = {
        "config_entry_id": HELPER_CONFIG_ENTRY_ID,
        "config_sha256": HELPER_CONFIG_SHA256,
        "entity_id": HELPER_ID,
        "device_class": "occupancy",
        "source_entity_ids": list(CANONICAL_SOURCE_IDS),
    }
    for key, expected in expected_helper.items():
        if helper.get(key) != expected:
            raise DiagnosticTransportError(f"Garage helper {key} no longer matches the reviewed configuration")
    normalized_helper = dict(expected_helper)
    normalized_helper.update(
        _sample(
            {key: helper[key] for key in _SAMPLE_KEYS},
            entity_id=HELPER_ID,
            observed_at=observed_at,
        )
    )

    signals = payload.get("signals")
    if not isinstance(signals, Mapping) or set(signals) != set(SIGNAL_METADATA):
        raise DiagnosticTransportError("Garage diagnostic signals do not match the exact allowlist")
    normalized_signals = {
        entity_id: _sample(sample, entity_id=entity_id, observed_at=observed_at)
        for entity_id, sample in signals.items()
    }

    downstream = payload.get("downstream")
    if not isinstance(downstream, Mapping) or set(downstream) != _DOWNSTREAM_KEYS:
        raise DiagnosticTransportError("Garage downstream fields do not match the approved contract")
    if downstream.get("entity_id") != DOWNSTREAM_ID or not isinstance(downstream.get("state"), str):
        raise DiagnosticTransportError("Garage downstream entity no longer matches the reviewed consumer")
    downstream_changed = _time(downstream.get("last_changed"), f"{DOWNSTREAM_ID}.last_changed")
    downstream_reported = _time(downstream.get("last_reported"), f"{DOWNSTREAM_ID}.last_reported")
    if downstream_changed > observed_at or downstream_reported > observed_at:
        raise DiagnosticTransportError("Garage downstream timestamp cannot be after observed_at")
    return {
        "schema_version": 1,
        "observed_at": _time_text(observed_at),
        "helper": normalized_helper,
        "signals": normalized_signals,
        "downstream": {
            "entity_id": DOWNSTREAM_ID,
            "state": downstream["state"],
            "last_changed": _time_text(downstream_changed),
            "last_reported": _time_text(downstream_reported),
        },
    }


class DiagnosticObservationStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                entity_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                state TEXT NOT NULL,
                PRIMARY KEY(entity_id, occurred_at, state)
            );
            CREATE TABLE IF NOT EXISTS latest_observation (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                observed_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()
        os.chmod(path, 0o600)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "DiagnosticObservationStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def record(self, observation: Mapping[str, Any]) -> None:
        observed_at = observation["observed_at"]
        previous = self.connection.execute(
            "SELECT observed_at FROM latest_observation WHERE singleton = 1"
        ).fetchone()
        if previous and _time(observed_at, "observed_at") < _time(previous["observed_at"], "prior observed_at"):
            raise DiagnosticTransportError("diagnostic observed_at cannot move backward")
        for entity_id, sample in observation["signals"].items():
            latest = self.connection.execute(
                "SELECT state FROM observations WHERE entity_id = ? ORDER BY julianday(occurred_at) DESC LIMIT 1",
                (entity_id,),
            ).fetchone()
            if latest is None or latest["state"] != sample["state"]:
                self.connection.execute(
                    "INSERT OR IGNORE INTO observations(entity_id, occurred_at, state) VALUES (?, ?, ?)",
                    (entity_id, sample["last_changed"], sample["state"]),
                )
            self.connection.execute(
                """DELETE FROM observations WHERE entity_id = ? AND rowid NOT IN (
                       SELECT rowid FROM observations WHERE entity_id = ?
                       ORDER BY julianday(occurred_at) DESC LIMIT 64
                   )""",
                (entity_id, entity_id),
            )
        self.connection.execute(
            """INSERT INTO latest_observation(singleton, observed_at) VALUES (1, ?)
               ON CONFLICT(singleton) DO UPDATE SET observed_at = excluded.observed_at""",
            (observed_at,),
        )
        self.connection.commit()

    def transitions(self, entity_id: str) -> list[dict[str, str]]:
        return [
            {"occurred_at": row["occurred_at"], "state": row["state"]}
            for row in self.connection.execute(
                "SELECT occurred_at, state FROM observations WHERE entity_id = ? ORDER BY julianday(occurred_at)",
                (entity_id,),
            )
        ]


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_REPORT_BYTES:
        raise DiagnosticTransportError("sanitized diagnostics report exceeds its fixed size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def process_diagnostic_source(
    payload: Any,
    *,
    observed_at: datetime,
    database: Path,
    output: Path,
    generated_at: datetime,
) -> dict[str, Any]:
    observation = validate_diagnostic_source(payload, observed_at)
    with DiagnosticObservationStore(database) as store:
        store.record(observation)
        replay_payload = {
            "schema_version": 5,
            "observed_at": observation["observed_at"],
            "helper": {
                "config_entry_id": HELPER_CONFIG_ENTRY_ID,
                "entity_id": HELPER_ID,
                "name": HELPER_NAME,
                "device_class": "occupancy",
                "state": observation["helper"]["state"],
                "template": HELPER_TEMPLATE,
                "source_entity_ids": list(CANONICAL_SOURCE_IDS),
                "consumers": [DOWNSTREAM_ID],
            },
            "signals": [
                {
                    "entity_id": entity_id,
                    **SIGNAL_METADATA[entity_id],
                    "state": sample["state"],
                    "last_changed": sample["last_changed"],
                    "last_updated": sample["last_reported"],
                    "transitions": store.transitions(entity_id),
                }
                for entity_id, sample in observation["signals"].items()
            ],
        }
    replay = DiagnosticReplay.from_payload(replay_payload)
    findings = detect_signal_issues(replay)
    private_report = diagnostic_report_payload(replay, findings)
    issue_card = None
    if findings:
        finding = findings[0]
        stage = "proposal_ready" if finding.proposal else "detected"
        issue_card = build_issue_card_payload(IssueCardState(finding, stage, generated_at))
    result = {
        "schema_version": 5,
        "generated_at": _time_text(generated_at),
        "observed_at": private_report["observed_at"],
        "fresh_until": _time_text(generated_at + timedelta(seconds=MAX_REPORT_AGE_SECONDS)),
        "overall_status": private_report["overall_status"],
        "issue_count": private_report["issue_count"],
        "issue_card": issue_card,
        "safety": {
            "ai_actions": "OFF",
            "device_controls_available": False,
            "configuration_repair_only": True,
        },
        "privacy": private_report["privacy"],
    }
    _write_private_json(output, result)
    return result


def read_fresh_diagnostics(path: Path, *, now: datetime) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise DiagnosticTransportError("diagnostics output is not a regular private file")
        if metadata.st_mode & 0o077:
            raise DiagnosticTransportError("diagnostics output permissions are not private")
        if metadata.st_size < 1 or metadata.st_size > MAX_REPORT_BYTES:
            raise DiagnosticTransportError("diagnostics output size is invalid")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise DiagnosticTransportError("diagnostics output is unavailable") from exc
    required = {"schema_version", "generated_at", "observed_at", "fresh_until", "overall_status", "issue_count", "issue_card", "safety", "privacy"}
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != 5:
        raise DiagnosticTransportError("diagnostics output contract is invalid")
    if now.tzinfo is None:
        raise DiagnosticTransportError("diagnostics clock must include a timezone")
    now_utc = now.astimezone(timezone.utc)
    generated = _time(payload["generated_at"], "generated_at")
    fresh_until = _time(payload["fresh_until"], "fresh_until")
    if generated > now_utc + timedelta(seconds=60) or now_utc > fresh_until:
        raise DiagnosticTransportError("diagnostics output is stale")
    return payload
