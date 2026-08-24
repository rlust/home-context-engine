from __future__ import annotations

import json
import os
import tempfile
import unittest
import ast
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path

from mac_mini.home_context_analytics.diagnostic_transport import (
    CANONICAL_SOURCE_IDS,
    DOWNSTREAM_ID,
    HELPER_CONFIG_ENTRY_ID,
    HELPER_CONFIG_SHA256,
    HELPER_ID,
    MAX_REPORT_AGE_SECONDS,
    SIGNAL_METADATA,
    DiagnosticTransportError,
    process_diagnostic_source,
    read_fresh_diagnostics,
    validate_diagnostic_source,
)


NOW = datetime(2026, 8, 23, 15, tzinfo=timezone.utc)


def observation(*, candidate_state: str = "off", candidate_time: str = "2026-08-23T14:59:30Z") -> dict[str, object]:
    signals = {
        entity_id: {
            "state": "off",
            "last_changed": "2026-08-23T14:59:00Z",
            "last_reported": "2026-08-23T14:59:00Z",
        }
        for entity_id in SIGNAL_METADATA
    }
    candidate = CANONICAL_SOURCE_IDS[0]
    signals[candidate] = {
        "state": candidate_state,
        "last_changed": candidate_time,
        "last_reported": candidate_time,
    }
    return {
        "schema_version": 1,
        "helper": {
            "config_entry_id": HELPER_CONFIG_ENTRY_ID,
            "config_sha256": HELPER_CONFIG_SHA256,
            "entity_id": HELPER_ID,
            "device_class": "occupancy",
            "source_entity_ids": list(CANONICAL_SOURCE_IDS),
            "state": candidate_state,
            "last_changed": candidate_time,
            "last_reported": candidate_time,
        },
        "signals": signals,
        "downstream": {
            "entity_id": DOWNSTREAM_ID,
            "state": "None" if candidate_state == "off" else "Garage",
            "last_changed": candidate_time,
            "last_reported": candidate_time,
        },
    }


class DiagnosticTransportTests(unittest.TestCase):
    def test_transport_has_no_external_client_subprocess_or_device_control_capability(self) -> None:
        source_path = Path(__file__).resolve().parents[1] / "home_context_analytics" / "diagnostic_transport.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(
            imported.isdisjoint(
                {"aiohttp", "httpx", "requests", "socket", "subprocess", "urllib", "websocket"}
            )
        )
        for forbidden in ("ha_call_service", "light.turn_on", "lock.unlock"):
            self.assertNotIn(forbidden, source)

    def test_exact_live_contract_is_accepted_but_unknown_fields_are_rejected(self) -> None:
        normalized = validate_diagnostic_source(observation(), NOW)
        self.assertEqual(set(normalized["signals"]), set(SIGNAL_METADATA))
        private = observation()
        private["person_name"] = "not allowed"
        with self.assertRaises(DiagnosticTransportError):
            validate_diagnostic_source(private, NOW)

    def test_reviewed_helper_hash_is_derived_from_the_exact_live_options(self) -> None:
        options = {
            "device_class": "occupancy",
            "name": "Garage Occupied",
            "state": "{{ is_state('binary_sensor.pir_motion_sensor_2_sensor_state_motion','on') or is_state('binary_sensor.gdo1_motion','on') or is_state('binary_sensor.grgdo1_motion','on') }}",
            "template_type": "binary_sensor",
        }
        digest = hashlib.sha256(
            json.dumps(options, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(digest, HELPER_CONFIG_SHA256)

    def test_private_report_is_atomic_0600_bounded_and_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "signal-diagnostics.json"
            result = process_diagnostic_source(
                observation(), observed_at=NOW, database=root / "diagnostics.sqlite3",
                output=output, generated_at=NOW
            )
            readback = read_fresh_diagnostics(output, now=NOW + timedelta(minutes=9))
            self.assertEqual(result, readback)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(root / "diagnostics.sqlite3").st_mode & 0o777, 0o600)
            self.assertLessEqual(output.stat().st_size, 32_768)
            serialized = json.dumps(readback, sort_keys=True)
            self.assertNotIn("transitions", serialized)
            self.assertNotIn("occurred_at", serialized)

    def test_stale_report_is_unavailable_after_fixed_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "signal-diagnostics.json"
            process_diagnostic_source(
                observation(), observed_at=NOW, database=root / "diagnostics.sqlite3",
                output=output, generated_at=NOW
            )
            with self.assertRaisesRegex(DiagnosticTransportError, "stale"):
                read_fresh_diagnostics(
                    output, now=NOW + timedelta(seconds=MAX_REPORT_AGE_SECONDS + 1)
                )

    def test_unavailable_required_source_surfaces_investigate_without_control(self) -> None:
        payload = observation()
        required = CANONICAL_SOURCE_IDS[1]
        payload["signals"][required]["state"] = "unavailable"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report = process_diagnostic_source(
                payload, observed_at=NOW, database=root / "diagnostics.sqlite3",
                output=root / "signal-diagnostics.json", generated_at=NOW
            )
        self.assertEqual(report["overall_status"], "Investigate")
        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(report["issue_card"]["stage"], "detected")
        self.assertFalse(report["issue_card"]["safety"]["device_controls_available"])


if __name__ == "__main__":
    unittest.main()
