from __future__ import annotations

import ast
import contextlib
import http.client
import io
import json
import plistlib
import re
import socket
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import mac_mini.home_context_analytics.receiver as receiver_module

from mac_mini.home_context_analytics.collector import collect_continuous_file
from mac_mini.home_context_analytics.ha_export_contract import (
    NON_OVERLAPPING_OBSERVER_MODES,
    PREDICTION_HELPERS,
    REVIEWED_OBSERVER_CONFIG_HASH,
    REVIEWED_OBSERVER_MODE,
    export_ready,
)
from mac_mini.home_context_analytics.fp300 import APPROVED_ENTITIES
from mac_mini.home_context_analytics.normalizer import REQUIRED_ENTITIES
from mac_mini.home_context_analytics.receiver import (
    MAX_BODY_BYTES,
    RECEIVER_PATH,
    SECRET_HEADER,
    ReceiverError,
    SnapshotReceiver,
    build_server,
    require_loopback_bind,
)
from mac_mini.home_context_analytics.diagnostic_transport import (
    CANONICAL_SOURCE_IDS,
    DIAGNOSTICS_PATH,
    DOWNSTREAM_ID,
    HELPER_CONFIG_ENTRY_ID,
    HELPER_CONFIG_SHA256,
    HELPER_ID,
    SIGNAL_METADATA,
    SOURCE_ID as DIAGNOSTIC_SOURCE_ID,
)
from mac_mini.home_context_analytics.report import build_report


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "mac_mini" / "fixtures" / "newark_snapshot_normal.json"
NOW = datetime(2026, 8, 12, 18, tzinfo=timezone.utc)
SECRET = "synthetic-test-secret-not-a-credential"


def snapshot_bytes(snapshot: dict[str, object] | None = None) -> bytes:
    payload = snapshot or json.loads(FIXTURE.read_text(encoding="utf-8"))
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ReceiverHarness:
    def __init__(self, root: Path):
        self.root = root
        self.receiver = SnapshotReceiver(
            secret=SECRET,
            replay_database=root / "replay.sqlite3",
            normalizer_database=root / "normalizer.sqlite3",
            output=root / "events.jsonl",
            diagnostics_database=root / "diagnostics.sqlite3",
            diagnostics_output=root / "signal-diagnostics.json",
            now=lambda: NOW,
        )
        self.server = build_server("127.0.0.1", 0, self.receiver)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.receiver.close()

    def request(
        self,
        *,
        method: str = "POST",
        path: str = RECEIVER_PATH,
        body: bytes | None = None,
        secret: str | None = SECRET,
        content_type: str = "application/json",
        declared_length: int | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Content-Type": content_type}
        if secret is not None:
            headers[SECRET_HEADER] = secret
        if declared_length is not None:
            headers["Content-Length"] = str(declared_length)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload


def diagnostic_snapshot() -> dict[str, object]:
    snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snapshot["source_context"] = {
        DIAGNOSTIC_SOURCE_ID: {
            "schema_version": 1,
            "helper": {
                "config_entry_id": HELPER_CONFIG_ENTRY_ID,
                "config_sha256": HELPER_CONFIG_SHA256,
                "entity_id": HELPER_ID,
                "device_class": "occupancy",
                "source_entity_ids": list(CANONICAL_SOURCE_IDS),
                "state": "off",
                "last_changed": "2026-08-12T17:59:00Z",
                "last_reported": "2026-08-12T17:59:00Z",
            },
            "signals": {
                entity_id: {
                    "state": "off",
                    "last_changed": "2026-08-12T17:59:00Z",
                    "last_reported": "2026-08-12T17:59:00Z",
                }
                for entity_id in SIGNAL_METADATA
            },
            "downstream": {
                "entity_id": DOWNSTREAM_ID,
                "state": "Family Room, Office",
                "last_changed": "2026-08-12T17:59:00Z",
                "last_reported": "2026-08-12T17:59:00Z",
            },
        }
    }
    return snapshot


class ReceiverTests(unittest.TestCase):
    def test_authenticated_diagnostics_get_is_sanitized_and_unauthenticated_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            harness = ReceiverHarness(Path(temporary_directory))
            try:
                post_status, _ = harness.request(body=snapshot_bytes(diagnostic_snapshot()))
                get_status, payload = harness.request(
                    method="GET", path=DIAGNOSTICS_PATH, body=None
                )
                denied_status, denied = harness.request(
                    method="GET", path=DIAGNOSTICS_PATH, body=None, secret=None
                )
            finally:
                harness.close()
        self.assertEqual(post_status, 202)
        self.assertEqual(get_status, 200)
        self.assertEqual(payload["schema_version"], 5)
        self.assertEqual(payload["overall_status"], "Healthy")
        self.assertEqual(payload["safety"]["ai_actions"], "OFF")
        self.assertFalse(payload["safety"]["device_controls_available"])
        serialized = json.dumps(payload, sort_keys=True)
        for forbidden in ("transitions", "occurred_at", SECRET, "service", "token"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(
            (denied_status, denied),
            (401, {"status": "rejected", "reason": "authentication_failed"}),
        )

    def test_diagnostics_get_fails_closed_when_report_is_missing_or_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            harness = ReceiverHarness(Path(temporary_directory))
            try:
                missing = harness.request(method="GET", path=DIAGNOSTICS_PATH, body=None)
                harness.request(body=snapshot_bytes(diagnostic_snapshot()))
                harness.receiver._now = lambda: NOW + timedelta(minutes=11)
                stale = harness.request(method="GET", path=DIAGNOSTICS_PATH, body=None)
            finally:
                harness.close()
        expected = (503, {"status": "unavailable", "reason": "diagnostics_unavailable"})
        self.assertEqual(missing, expected)
        self.assertEqual(stale, expected)

    def test_diagnostic_source_rejects_helper_drift_before_writing_report(self) -> None:
        snapshot = diagnostic_snapshot()
        snapshot["source_context"][DIAGNOSTIC_SOURCE_ID]["helper"]["config_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            harness = ReceiverHarness(root)
            try:
                result = harness.request(body=snapshot_bytes(snapshot))
            finally:
                harness.close()
            self.assertFalse((root / "signal-diagnostics.json").exists())
        self.assertEqual(result, (422, {"status": "rejected", "reason": "invalid_snapshot"}))
    def test_receiver_has_no_ha_mcp_subprocess_or_service_call_capability(self) -> None:
        source_path = ROOT / "mac_mini" / "home_context_analytics" / "receiver.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.isdisjoint({"requests", "subprocess", "websocket", "aiohttp"}))
        for forbidden in ("ha_call_service", "mcp__", "light.turn_on", "lock.unlock"):
            self.assertNotIn(forbidden, source)

    def test_loopback_bind_enforced(self) -> None:
        self.assertEqual(require_loopback_bind("127.0.0.1"), "127.0.0.1")
        for host in ("::1", "0.0.0.0", "192.0.2.1", "localhost", ""):
            with self.subTest(host=host), self.assertRaises(ReceiverError):
                require_loopback_bind(host)

    def test_receiver_storage_paths_must_be_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            shared = Path(temporary_directory) / "shared"
            with self.assertRaisesRegex(ReceiverError, "distinct"):
                SnapshotReceiver(
                    secret=SECRET,
                    replay_database=shared,
                    normalizer_database=shared,
                    output=Path(temporary_directory) / "events.jsonl",
                )

    def test_receiver_rejects_empty_and_short_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for secret in ("", "x" * 31):
                with self.subTest(length=len(secret)), self.assertRaisesRegex(
                    ReceiverError, "at least 32 bytes"
                ):
                    SnapshotReceiver(
                        secret=secret,
                        replay_database=root / f"replay-{len(secret)}.sqlite3",
                        normalizer_database=root / f"state-{len(secret)}.sqlite3",
                        output=root / f"events-{len(secret)}.jsonl",
                    )

    def test_observer_coherence_gate_is_fail_closed_but_feedback_can_export(self) -> None:
        event_time = "2026-08-12T18:00:00Z"
        complete = {entity_id: "2026-08-12T18:00:01Z" for entity_id in PREDICTION_HELPERS}
        partial = dict(complete)
        partial.pop(PREDICTION_HELPERS[-1])
        stale = dict(complete)
        stale[PREDICTION_HELPERS[-1]] = "2026-08-12T17:59:59Z"
        self.assertFalse(
            export_ready(
                "observer",
                observer_event_time=event_time,
                helper_last_reported=partial,
                observer_active=False,
            )
        )
        self.assertFalse(
            export_ready(
                "observer",
                observer_event_time=event_time,
                helper_last_reported=stale,
                observer_active=False,
            )
        )
        for observer_active in (True, None):
            with self.subTest(observer_active=observer_active):
                self.assertFalse(
                    export_ready(
                        "observer",
                        observer_event_time=event_time,
                        helper_last_reported=complete,
                        observer_active=observer_active,
                    )
                )
        # Live Newark preserves old/mixed state contexts for unchanged values.
        # Contexts are intentionally absent from this gate; completion plus all
        # five fresh last_reported cursors proves the reviewed sole-writer run.
        self.assertTrue(
            export_ready(
                "observer",
                observer_event_time=event_time,
                helper_last_reported=complete,
                observer_active=False,
            )
        )
        self.assertTrue(
            export_ready(
                "feedback",
                observer_event_time=None,
                helper_last_reported={},
                observer_active=False,
            )
        )
        self.assertFalse(
            export_ready(
                "feedback",
                observer_event_time=None,
                helper_last_reported={},
                observer_active=True,
            )
        )
        self.assertFalse(
            export_ready(
                "feedback",
                observer_event_time=None,
                helper_last_reported={},
                observer_active=None,
            )
        )

    def test_ha_draft_renders_only_allowlist_and_remains_observe_only(self) -> None:
        draft = (
            ROOT / "mac_mini" / "home_assistant" / "home_context_snapshot_push.yaml.example"
        ).read_text(encoding="utf-8")
        rendered_entities = set(re.findall(r"^\s+'([^']+)': \{'state':", draft, re.MULTILINE))
        self.assertEqual(rendered_entities, set(REQUIRED_ENTITIES))
        rendered_fp300_entities = set(
            re.findall(r'^\s+"([^"]+)": \{\'state\':', draft, re.MULTILINE)
        )
        self.assertEqual(
            rendered_fp300_entities,
            set(APPROVED_ENTITIES) | set(SIGNAL_METADATA),
        )
        for required in (
            "verify_ssl: true",
            "timeout: 5",
            "https://randys-mac-mini.tail1f233.ts.net:9443/v1/home-context/snapshot",
            "!secret home_context_receiver_secret",
            "continue_on_error: true",
            "observer_event_time",
            "observer_context_id",
            'timeout: "00:00:10"',
            "Observer helper coherence proof did not complete; no snapshot was posted.",
            "Observer was active or its completion state was unavailable; no snapshot was posted.",
            "state_attr('automation.home_context_evening_observer', 'current')",
            "home_context_analytics/ha_export_contract.py",
            f"Observer config hash {REVIEWED_OBSERVER_CONFIG_HASH}",
            f"mode {REVIEWED_OBSERVER_MODE}",
            "https://randys-mac-mini.tail1f233.ts.net:9443/v1/home-context/diagnostics",
            "unique_id: home_context_signal_diagnostics",
            "scan_interval: 60",
            "garage-diagnostics-v1",
            HELPER_CONFIG_ENTRY_ID,
            HELPER_CONFIG_SHA256,
            "minutes: \"/5\"",
        ):
            self.assertIn(required, draft)
        self.assertNotIn("REPLACE_WITH_", draft)
        self.assertIn(
            "bc406e98598bebbc20c0efcb963c0443facc203b71ba7a9cfedfca21e8ca20e6",
            draft,
        )
        self.assertIn(
            "0b7554c973b019865c6962a69d687559251f3e2d00f56767e7f2de5c9f880470",
            draft,
        )
        self.assertNotIn(":8443/", draft)
        self.assertIn(REVIEWED_OBSERVER_MODE, NON_OVERLAPPING_OBSERVER_MODES)
        for entity_id in PREDICTION_HELPERS:
            self.assertGreaterEqual(draft.count(f"states.{entity_id}.last_reported"), 3)
        self.assertNotIn(".context.id == observer_context_id", draft)
        self.assertGreaterEqual(
            draft.count("state_attr('automation.home_context_evening_observer', 'current')"), 4
        )
        for forbidden in ("light.turn_on", "lock.unlock", "ai_actions_enabled.turn_on"):
            self.assertNotIn(forbidden, draft)
        self.assertEqual(draft.count("X-Home-Context-Secret: !secret home_context_receiver_secret"), 2)
        self.assertGreaterEqual(draft.count("id: diagnostics"), 2)

    def test_ha_draft_observer_gate_structurally_matches_python_mirror(self) -> None:
        draft = (
            ROOT / "mac_mini" / "home_assistant" / "home_context_snapshot_push.yaml.example"
        ).read_text(encoding="utf-8")
        observer_branch = draft.split(
            '- conditions: "{{ trigger.id == \'observer\' }}"', 1
        )[1].split('- conditions: "{{ trigger.id in [\'feedback\', \'diagnostics\'] }}"', 1)[0]
        gate_expressions = re.findall(
            r"(?:wait_template|value_template): >-\n\s+\{\{\n(.*?)\n\s+\}\}",
            observer_branch,
            re.DOTALL,
        )
        self.assertEqual(len(gate_expressions), 2)
        helper_pattern = re.compile(
            r"states\.([a-z0-9_]+\.[a-z0-9_]+)\.last_reported"
            r"\s*>=\s*as_datetime\(observer_event_time\)"
        )
        for expression in gate_expressions:
            self.assertEqual(tuple(helper_pattern.findall(expression)), PREDICTION_HELPERS)
            self.assertEqual(
                expression.count(
                    "state_attr('automation.home_context_evening_observer', 'current') is not none"
                ),
                1,
            )
            self.assertEqual(
                expression.count(
                    "state_attr('automation.home_context_evening_observer', 'current') | int == 0"
                ),
                1,
            )

    def test_unexpected_exception_is_value_free_and_server_remains_operable(self) -> None:
        private_marker = "SYNTHETIC_PRIVATE_MARKER_DO_NOT_LOG"
        with tempfile.TemporaryDirectory() as temporary_directory:
            harness = ReceiverHarness(Path(temporary_directory))
            original = harness.receiver._receive_locked
            calls = 0

            def fail_once(body: bytes):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError(private_marker)
                return original(body)

            harness.receiver._receive_locked = fail_once
            captured_stderr = io.StringIO()
            try:
                with contextlib.redirect_stderr(captured_stderr):
                    failure_status, failure = harness.request(body=snapshot_bytes())
                    success_status, success = harness.request(body=snapshot_bytes())
                    try:
                        raise RuntimeError(private_marker)
                    except RuntimeError:
                        harness.server.handle_error(object(), ("127.0.0.1", 0))
            finally:
                harness.close()

        self.assertEqual(failure_status, 500)
        self.assertEqual(failure, {"status": "unavailable", "reason": "internal_error"})
        self.assertEqual(success_status, 202)
        self.assertEqual(success["status"], "accepted")
        self.assertNotIn(private_marker, json.dumps(failure))
        self.assertNotIn(private_marker, captured_stderr.getvalue())

    def test_launch_and_serve_templates_keep_receiver_private(self) -> None:
        plist_path = (
            ROOT / "mac_mini" / "launchd" / "xyz.buzz.home-context-receiver.plist.example"
        )
        with plist_path.open("rb") as stream:
            plist = plistlib.load(stream)
        arguments = plist["ProgramArguments"]
        self.assertEqual(arguments[arguments.index("--bind") + 1], "127.0.0.1")
        self.assertNotIn("0.0.0.0", arguments)
        self.assertFalse(any(SECRET in str(value) for value in arguments))
        self.assertEqual(plist["Umask"], 0o77)
        analytics_plist_path = (
            ROOT / "mac_mini" / "launchd" / "xyz.buzz.home-context-analytics.plist.example"
        )
        with analytics_plist_path.open("rb") as stream:
            analytics_plist = plistlib.load(stream)
        self.assertEqual(analytics_plist["Umask"], 0o77)
        commands = (
            ROOT / "mac_mini" / "tailscale" / "serve.commands.example"
        ).read_text(encoding="utf-8")
        executable_lines = [
            line.strip() for line in commands.splitlines() if line.strip() and not line.startswith("#")
        ]
        self.assertTrue(any("http://127.0.0.1:8765" in line for line in executable_lines))
        self.assertIn("tailscale serve --https=9443 off", executable_lines)
        self.assertGreater(
            executable_lines.index("tailscale serve --bg --https=9443 http://127.0.0.1:8765"),
            executable_lines.index(
                "tailscale serve status --json > REPLACE_WITH_PRIVATE_REVIEW_DIRECTORY/serve-before.json"
            ),
        )
        self.assertFalse(
            any(re.search(r"(?:^|\s)tailscale\s+funnel(?:\s|$)", line, re.I) for line in executable_lines)
        )
        self.assertFalse(
            any(
                re.search(r"(?:^|\s)tailscale\s+serve\s+reset(?:\s|$)", line, re.I)
                for line in executable_lines
            )
        )
        off_commands = [line for line in executable_lines if re.search(r"(?:^|\s)off(?:\s|$)", line)]
        self.assertEqual(off_commands, ["tailscale serve --https=9443 off"])
        self.assertFalse(any("--https=8443" in line for line in executable_lines))
        self.assertTrue(
            any(
                "8443 is reserved by the existing BriefDash mapping" in line
                for line in commands.splitlines()
            )
        )

    def test_incomplete_body_times_out_without_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory, patch.object(
            receiver_module, "READ_TIMEOUT_SECONDS", 0.05
        ):
            harness = ReceiverHarness(Path(temporary_directory))
            try:
                client = socket.create_connection(("127.0.0.1", harness.server.server_port), timeout=1)
                client.sendall(
                    (
                        f"POST {RECEIVER_PATH} HTTP/1.1\r\n"
                        "Host: 127.0.0.1\r\n"
                        "Content-Type: application/json\r\n"
                        f"{SECRET_HEADER}: {SECRET}\r\n"
                        "Content-Length: 10\r\n\r\n"
                        "{}"
                    ).encode()
                )
                chunks = []
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                response = b"".join(chunks)
                client.close()
            finally:
                harness.close()
        self.assertIn(b"408 Request Timeout", response)
        self.assertIn(b'"status":"unavailable"', response)
        self.assertNotIn(SECRET.encode(), response)

    def test_authenticated_accept_duplicate_and_no_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            harness = ReceiverHarness(Path(temporary_directory))
            try:
                first_status, first = harness.request(body=snapshot_bytes())
                replay_status, replay = harness.request(body=snapshot_bytes())
                refreshed = json.loads(FIXTURE.read_text(encoding="utf-8"))
                refreshed["snapshot_at"] = "2026-08-12T18:05:00Z"
                refreshed["entities"]["sensor.home_context_observer_age"]["state"] = "1"
                refreshed["entities"]["sensor.home_context_observer_age"]["last_changed"] = "2026-08-12T18:05:00Z"
                refreshed["entities"]["sensor.home_context_observer_age"]["last_reported"] = "2026-08-12T18:05:00Z"
                no_change_status, no_change = harness.request(body=snapshot_bytes(refreshed))
            finally:
                harness.close()
        self.assertEqual((first_status, first["status"]), (202, "accepted"))
        self.assertEqual((replay_status, replay), (200, {"status": "duplicate", "reason": "replay"}))
        self.assertEqual(
            (no_change_status, no_change),
            (200, {"status": "duplicate", "reason": "no_transition"}),
        )

    def test_auth_method_path_content_type_and_size_rejections_are_value_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            harness = ReceiverHarness(Path(temporary_directory))
            try:
                cases = (
                    harness.request(body=snapshot_bytes(), secret=None),
                    harness.request(method="GET", body=None),
                    harness.request(method="POST", path=DIAGNOSTICS_PATH, body=b"{}"),
                    harness.request(path="/wrong", body=snapshot_bytes()),
                    harness.request(body=snapshot_bytes(), content_type="text/plain"),
                    harness.request(body=b"{}", declared_length=MAX_BODY_BYTES + 1),
                )
            finally:
                harness.close()
        self.assertEqual([status for status, _ in cases], [401, 405, 405, 404, 415, 413])
        rendered = json.dumps(cases)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn("Working", rendered)

    def test_stale_and_allowlist_rejections_are_generic(self) -> None:
        stale = json.loads(FIXTURE.read_text(encoding="utf-8"))
        stale["snapshot_at"] = "2026-08-12T17:49:59Z"
        private = json.loads(FIXTURE.read_text(encoding="utf-8"))
        private["entities"]["person.synthetic"] = {
            "state": "home",
            "last_changed": "2026-08-12T18:00:00Z",
            "last_reported": "2026-08-12T18:00:00Z",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            harness = ReceiverHarness(Path(temporary_directory))
            try:
                responses = (
                    harness.request(body=snapshot_bytes(stale)),
                    harness.request(body=snapshot_bytes(private)),
                )
            finally:
                harness.close()
        for status, payload in responses:
            self.assertEqual(status, 422)
            self.assertEqual(payload, {"status": "rejected", "reason": "invalid_snapshot"})

    def test_backpressure_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            receiver = SnapshotReceiver(
                secret=SECRET,
                replay_database=Path(temporary_directory) / "replay.sqlite3",
                normalizer_database=Path(temporary_directory) / "state.sqlite3",
                output=Path(temporary_directory) / "events.jsonl",
                now=lambda: NOW,
            )
            receiver._request_lock.acquire()
            try:
                code, payload = receiver.receive(supplied_secret=SECRET, body=snapshot_bytes())
            finally:
                receiver._request_lock.release()
                receiver.close()
        self.assertEqual((code, payload), (503, {"status": "unavailable", "reason": "backpressure"}))

    def test_feedback_audit_failure_is_accepted_but_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            receiver = SnapshotReceiver(
                secret=SECRET,
                replay_database=root / "replay.sqlite3",
                normalizer_database=root / "state.sqlite3",
                output=root / "events.jsonl",
                now=lambda: NOW,
            )
            try:
                first_code, _first = receiver.receive(
                    supplied_secret=SECRET, body=snapshot_bytes()
                )
                wrong = json.loads(FIXTURE.read_text(encoding="utf-8"))
                wrong["snapshot_at"] = "2026-08-12T18:05:00Z"
                wrong_button = wrong["entities"]["input_button.home_context_mark_wrong"]
                wrong_button["state"] = "2026-08-12T18:04:00Z"
                wrong_button["last_changed"] = "2026-08-12T18:04:00Z"
                wrong_button["last_reported"] = "2026-08-12T18:04:00Z"
                wrong["entities"]["counter.home_context_corrections"]["state"] = "1"
                code, payload = receiver.receive(
                    supplied_secret=SECRET, body=snapshot_bytes(wrong)
                )
            finally:
                receiver.close()
        self.assertEqual(first_code, 202)
        self.assertEqual(code, 202)
        self.assertEqual(payload["feedback_created"], 1)
        self.assertTrue(payload["audit_visible"])

    def test_loopback_socket_end_to_end_receiver_normalizer_ingest_report_and_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            harness = ReceiverHarness(root)
            original_create_connection = socket.create_connection

            def loopback_only(address, *args, **kwargs):
                self.assertEqual(address[0], "127.0.0.1")
                return original_create_connection(address, *args, **kwargs)

            try:
                with patch("socket.create_connection", side_effect=loopback_only):
                    status, payload = harness.request(body=snapshot_bytes())
            finally:
                harness.close()
            self.assertFalse(harness.thread.is_alive())
            counts = collect_continuous_file(
                root / "events.jsonl", root / "analytics.sqlite3", as_of=NOW
            )
            report = build_report(root / "analytics.sqlite3", as_of=NOW)
            self.assertEqual(status, 202)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(counts["episodes_inserted"], 1)
            self.assertEqual(report["episodes"], 1)
            self.assertFalse(report["privacy"]["network_used"])
            for path in (
                root / "replay.sqlite3",
                root / "normalizer.sqlite3",
                root / "events.jsonl",
                root / "analytics.sqlite3",
            ):
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(SECRET.encode(), (root / "replay.sqlite3").read_bytes())

    def test_shutdown_waits_for_inflight_handler_before_closing_replay_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            harness = ReceiverHarness(Path(temporary_directory))
            entered = threading.Event()
            release = threading.Event()
            client_errors: list[BaseException] = []
            original_receive = harness.receiver.receive

            def blocked_receive(**kwargs):
                entered.set()
                release.wait(timeout=2)
                return original_receive(**kwargs)

            harness.receiver.receive = blocked_receive

            def make_request() -> None:
                try:
                    harness.request(body=snapshot_bytes())
                except BaseException as exc:
                    client_errors.append(exc)

            client = threading.Thread(target=make_request)
            client.start()
            self.assertTrue(entered.wait(timeout=1))
            closer = threading.Thread(target=harness.close)
            closer.start()
            time.sleep(0.05)
            self.assertTrue(closer.is_alive())
            release.set()
            closer.join(timeout=2)
            client.join(timeout=2)
            self.assertFalse(closer.is_alive())
            self.assertFalse(client.is_alive())
            self.assertFalse(harness.thread.is_alive())
            self.assertEqual(client_errors, [])


if __name__ == "__main__":
    unittest.main()
