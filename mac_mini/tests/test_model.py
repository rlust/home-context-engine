from __future__ import annotations

import unittest

from mac_mini.home_context_analytics.model import (
    ValidationError,
    normalize_ha_active_rooms,
    normalize_ha_confidence,
    parse_record,
)


class ModelTests(unittest.TestCase):
    def valid_prediction(self) -> dict[str, object]:
        return {
            "kind": "prediction",
            "source_event_id": "10000000-0000-4000-8000-000000000001",
            "episode_id": "20000000-0000-4000-8000-000000000001",
            "occurred_at": "2026-08-12T12:00:00-04:00",
            "mode": "Active",
            "activity": "Working",
            "confidence": 88,
            "active_rooms": ["Office"],
            "resident_bucket": "one",
            "signals": {
                "exterior_door": "inactive",
                "music_playing": "inactive",
                "observer_health": "active",
                "recent_arrival": "inactive",
                "resident_presence": "active",
                "room_presence": "active",
                "tv_active": "inactive",
            },
            "observer_version": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "context_flags": [],
            "next_activity": None,
        }

    def test_normalizes_timestamp_and_rooms(self) -> None:
        payload = self.valid_prediction()
        payload["active_rooms"] = ["Office", "Family Room", "Office"]
        record = parse_record(payload)
        self.assertEqual(record.occurred_at, "2026-08-12T16:00:00Z")
        self.assertEqual(record.active_rooms, ("Family Room", "Office"))

    def test_stale_and_missing_are_not_absence(self) -> None:
        for state in ("inactive", "stale", "missing"):
            payload = self.valid_prediction()
            payload["source_event_id"] = {
                "inactive": "10000000-0000-4000-8000-000000000011",
                "stale": "10000000-0000-4000-8000-000000000012",
                "missing": "10000000-0000-4000-8000-000000000013",
            }[state]
            payload["signals"] = dict(payload["signals"])
            payload["signals"]["room_presence"] = state
            record = parse_record(payload)
            self.assertEqual(dict(record.signals)["room_presence"], state)

    def test_rejects_sensitive_or_unapproved_fields(self) -> None:
        for key in ("person_name", "camera_url", "gps_latitude", "access_token", "message_text"):
            payload = self.valid_prediction()
            payload[key] = "private"
            with self.subTest(key=key), self.assertRaises(ValidationError):
                parse_record(payload)

    def test_rejects_service_events_and_unknown_signals(self) -> None:
        with self.assertRaisesRegex(ValidationError, "HA service events"):
            parse_record({"kind": "service_call", "service": "light.turn_on"})
        payload = self.valid_prediction()
        payload["signals"] = {"unreviewed_sensor": "active"}
        with self.assertRaisesRegex(ValidationError, "signals are not whitelisted"):
            parse_record(payload)

    def test_requires_explicit_signal_health(self) -> None:
        payload = self.valid_prediction()
        payload["signals"] = dict(payload["signals"])
        del payload["signals"]["room_presence"]
        with self.assertRaisesRegex(ValidationError, "explicitly mark"):
            parse_record(payload)

    def test_wrong_feedback_requires_corrected_activity(self) -> None:
        payload = {
            "kind": "feedback",
            "source_event_id": "30000000-0000-4000-8000-000000000001",
            "episode_id": "20000000-0000-4000-8000-000000000001",
            "occurred_at": "2026-08-12T16:01:00Z",
            "outcome": "wrong",
            "corrected_activity": None,
            "audit_consistent": True,
            "audit_issues": [],
        }
        with self.assertRaisesRegex(ValidationError, "requires"):
            parse_record(payload)

    def test_requires_opaque_ids(self) -> None:
        payload = self.valid_prediction()
        for field, value in (
            ("source_event_id", "sensor.office_presence"),
            ("episode_id", "randy-working"),
            ("observer_version", "observer-production"),
        ):
            changed = dict(payload)
            changed[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValidationError, "opaque"):
                parse_record(changed)

    def test_normalizes_integral_ha_decimal_without_rounding(self) -> None:
        self.assertEqual(normalize_ha_confidence("20.0"), 20)
        self.assertEqual(normalize_ha_confidence("100.000"), 100)
        for value in ("20.5", "NaN", "101", 20.0):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_ha_confidence(value)

    def test_normalizes_comma_separated_multi_room_state(self) -> None:
        self.assertEqual(
            normalize_ha_active_rooms("Family Room, Office, Kitchen, Foyer"),
            (("Family Room", "Foyer", "Kitchen", "Office"), "active"),
        )
        self.assertEqual(normalize_ha_active_rooms("None"), ((), "inactive"))
        self.assertEqual(normalize_ha_active_rooms("unknown"), ((), "missing"))
        self.assertEqual(normalize_ha_active_rooms("unavailable"), ((), "missing"))


if __name__ == "__main__":
    unittest.main()
