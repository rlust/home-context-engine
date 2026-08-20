"""Strict, read-only normalization for Newark's Family Room Aqara FP300."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

SOURCE_ID = "fp300-context-v1"

EVIDENCE_ENTITIES = frozenset(
    {
        "binary_sensor.family_room_aqara_presence_multi_sensor_fp300",
        "binary_sensor.family_room_aqara_presence_multi_sensor_fp300_pir_detection",
        "sensor.aqara_lumi_sensor_occupy_agl8_illuminance",
        "sensor.aqara_lumi_sensor_occupy_agl8_humidity",
        "sensor.aqara_lumi_sensor_occupy_agl8_temperature",
        "sensor.family_room_aqara_presence_multi_sensor_fp300_target_distance",
    }
)

HEALTH_ENTITIES = frozenset(
    {
        "sensor.aqara_lumi_sensor_occupy_agl8_battery",
        "sensor.family_room_aqara_presence_multi_sensor_fp300_battery",
        "sensor.family_room_aqara_presence_multi_sensor_fp300_battery_voltage",
        "update.aqara_lumi_sensor_occupy_agl8_firmware",
    }
)

AUDIT_ENTITIES = frozenset(
    {
        "button.aqara_lumi_sensor_occupy_agl8_identify",
        "button.family_room_aqara_presence_multi_sensor_fp300_ai_spatial_learning",
        "button.family_room_aqara_presence_multi_sensor_fp300_restart_device",
        "button.family_room_aqara_presence_multi_sensor_fp300_track_target_distance",
        "number.family_room_aqara_presence_multi_sensor_fp300_absence_delay",
        "number.family_room_aqara_presence_multi_sensor_fp300_pir_detection_interval",
        "number.family_room_aqara_presence_multi_sensor_fp300_light_report_threshold",
        "number.family_room_aqara_presence_multi_sensor_fp300_light_sampling_period",
        "number.family_room_aqara_presence_multi_sensor_fp300_light_report_interval",
        "number.family_room_aqara_presence_multi_sensor_fp300_temperature_report_threshold",
        "number.family_room_aqara_presence_multi_sensor_fp300_humidity_report_interval",
        "number.family_room_aqara_presence_multi_sensor_fp300_temperature_and_humidity_sampling_period",
        "number.family_room_aqara_presence_multi_sensor_fp300_temperature_report_interval",
        "number.family_room_aqara_presence_multi_sensor_fp300_humidity_report_threshold",
        "number.family_room_aqara_presence_multi_sensor_fp300_detection_range",
        "select.family_room_aqara_presence_multi_sensor_fp300_presence_detection_mode",
        "select.family_room_aqara_presence_multi_sensor_fp300_presence_sensitivity",
        "select.family_room_aqara_presence_multi_sensor_fp300_light_sampling",
        "select.family_room_aqara_presence_multi_sensor_fp300_light_report_mode",
        "select.family_room_aqara_presence_multi_sensor_fp300_humidity_report_mode",
        "select.family_room_aqara_presence_multi_sensor_fp300_temperature_and_humidity_sampling",
        "select.family_room_aqara_presence_multi_sensor_fp300_temperature_report_mode",
        "select.family_room_aqara_presence_multi_sensor_fp300_led_trigger_indicator_off_start_time",
        "select.family_room_aqara_presence_multi_sensor_fp300_led_trigger_indicator_off_end_time",
        "switch.family_room_aqara_presence_multi_sensor_fp300_ai_interference_source_self_identification",
        "switch.family_room_aqara_presence_multi_sensor_fp300_ai_adaptive_sensitivity",
        "switch.family_room_aqara_presence_multi_sensor_fp300_led_trigger_indicator_off_schedule",
    }
)

APPROVED_ENTITIES = EVIDENCE_ENTITIES | HEALTH_ENTITIES | AUDIT_ENTITIES
ENTITY_KEYS = frozenset({"state", "last_changed", "last_reported"})
SOURCE_KEYS = frozenset({"entities"})
NORMALIZED_KEYS = frozenset({"schema", "entities"})
NORMALIZED_ENTITY_KEYS = frozenset({"state", "observed_at", "freshness", "role"})
TARGET_DISTANCE = "sensor.family_room_aqara_presence_multi_sensor_fp300_target_distance"


class FP300Error(ValueError):
    """Raised when FP300 input crosses the reviewed read-only boundary."""


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise FP300Error(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FP300Error(f"{label} must be valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise FP300Error(f"{label} must include a timezone")
    return parsed


def normalize_fp300(source: Any, snapshot_at: datetime) -> dict[str, Any]:
    """Validate all state-backed FP300 entities and attach role/freshness metadata.

    Button/number/select/switch values are retained for audit only. This module has
    no service-call path and cannot command the device.
    """

    if not isinstance(source, Mapping) or set(source) != SOURCE_KEYS:
        raise FP300Error("fp300-context-v1 must contain only entities")
    entities = source["entities"]
    if not isinstance(entities, Mapping):
        raise FP300Error("fp300-context-v1.entities must be an object")
    actual = set(entities)
    unknown = actual - APPROVED_ENTITIES
    missing = APPROVED_ENTITIES - actual
    if unknown:
        raise FP300Error(f"FP300 entities are not approved: {', '.join(sorted(unknown))}")
    if missing:
        raise FP300Error(f"FP300 entities are missing: {', '.join(sorted(missing))}")

    normalized: dict[str, Any] = {}
    for entity_id in sorted(APPROVED_ENTITIES):
        entity = entities[entity_id]
        if not isinstance(entity, Mapping) or set(entity) != ENTITY_KEYS:
            raise FP300Error(f"{entity_id} must contain state, last_changed, and last_reported")
        state = entity["state"]
        if not isinstance(state, str):
            raise FP300Error(f"{entity_id}.state must be a string")
        changed = _time(entity["last_changed"], f"{entity_id}.last_changed")
        reported = _time(entity["last_reported"], f"{entity_id}.last_reported")
        if changed > snapshot_at or reported > snapshot_at:
            raise FP300Error(f"{entity_id} timestamp cannot be after snapshot_at")
        role = (
            "evidence"
            if entity_id in EVIDENCE_ENTITIES
            else "health"
            if entity_id in HEALTH_ENTITIES
            else "audit_only"
        )
        freshness_seconds = 120 if entity_id == TARGET_DISTANCE else 900
        normalized[entity_id] = {
            "state": state,
            "observed_at": reported.isoformat().replace("+00:00", "Z"),
            "freshness": (
                "missing"
                if state.strip().lower() in {"unknown", "unavailable"}
                else "fresh"
                if snapshot_at <= reported + timedelta(seconds=freshness_seconds)
                else "stale"
            ),
            "role": role,
        }
    return {"schema": SOURCE_ID, "entities": normalized}


def validate_normalized_fp300(context: Any) -> Mapping[str, Any]:
    """Revalidate normalized records at the independent JSONL ingest boundary."""

    if not isinstance(context, Mapping) or set(context) != NORMALIZED_KEYS:
        raise FP300Error("fp300_context must contain only schema and entities")
    if context["schema"] != SOURCE_ID or not isinstance(context["entities"], Mapping):
        raise FP300Error("fp300_context must use the reviewed fp300-context-v1 schema")
    entities = context["entities"]
    if set(entities) != APPROVED_ENTITIES:
        raise FP300Error("fp300_context must contain the exact reviewed FP300 entity set")
    for entity_id in APPROVED_ENTITIES:
        entity = entities[entity_id]
        if not isinstance(entity, Mapping) or set(entity) != NORMALIZED_ENTITY_KEYS:
            raise FP300Error(f"{entity_id} normalized fields are invalid")
        if (
            not isinstance(entity["state"], str)
            or len(entity["state"]) > 128
            or any(character in entity["state"] for character in "\r\n")
        ):
            raise FP300Error(f"{entity_id}.state must be a short single-line string")
        _time(entity["observed_at"], f"{entity_id}.observed_at")
        if entity["freshness"] not in {"fresh", "stale", "missing"}:
            raise FP300Error(f"{entity_id}.freshness is invalid")
        expected_role = (
            "evidence"
            if entity_id in EVIDENCE_ENTITIES
            else "health"
            if entity_id in HEALTH_ENTITIES
            else "audit_only"
        )
        if entity["role"] != expected_role:
            raise FP300Error(f"{entity_id}.role is invalid")
    return context
