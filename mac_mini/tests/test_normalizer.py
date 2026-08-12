from __future__ import annotations

import copy
import ast
import json
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from mac_mini.home_context_analytics.collector import collect_continuous_file
from mac_mini.home_context_analytics.normalizer import (
    ACTIVITY,
    AI_ACTIONS,
    CONFIRM,
    CONFIRMATIONS,
    CORRECTED,
    MODE,
    OBSERVER_AGE,
    OBSERVER_STALLED,
    ROOM_PRESENCE,
    SUMMARY,
    TV,
    WRONG,
    CORRECTIONS,
    NormalizerState,
    SnapshotError,
    append_records,
    normalize_and_append,
    normalize_snapshot,
)
from mac_mini.home_context_analytics.report import build_report


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_FIXTURE = ROOT / "mac_mini" / "fixtures" / "newark_snapshot_normal.json"


def load_snapshot() -> dict[str, object]:
    return json.loads(SNAPSHOT_FIXTURE.read_text(encoding="utf-8"))


def refresh(snapshot: dict[str, object], when: str) -> dict[str, object]:
    changed = copy.deepcopy(snapshot)
    changed["snapshot_at"] = when
    changed["entities"][OBSERVER_AGE]["state"] = "1"
    changed["entities"][OBSERVER_AGE]["last_changed"] = when
    changed["entities"][OBSERVER_STALLED]["last_changed"] = when
    for entity_id in (TV, ROOM_PRESENCE):
        changed["entities"][entity_id]["last_changed"] = when
    return changed


class NormalizerTests(unittest.TestCase):
    def test_normalizer_has_no_transport_network_or_subprocess_imports(self) -> None:
        source_path = ROOT / "mac_mini" / "home_context_analytics" / "normalizer.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(
            imported.isdisjoint(
                {"aiohttp", "asyncio", "httpx", "requests", "socket", "subprocess", "urllib", "websocket"}
            )
        )
        source = source_path.read_text(encoding="utf-8")
        for forbidden in ("ha_call_service", "light.turn_on", "lock.unlock"):
            self.assertNotIn(forbidden, source)

    def test_exact_allowlist_and_privacy_rejections(self) -> None:
        cases = []
        unknown_entity = load_snapshot()
        unknown_entity["entities"]["person.synthetic_resident"] = {
            "state": "home",
            "last_changed": "2026-08-12T18:00:00Z",
        }
        cases.append(unknown_entity)
        extra_attribute = load_snapshot()
        extra_attribute["entities"][MODE]["attributes"] = {"friendly_name": "private"}
        cases.append(extra_attribute)
        service = load_snapshot()
        service["service"] = "light.turn_on"
        cases.append(service)
        missing = load_snapshot()
        del missing["entities"][ACTIVITY]
        cases.append(missing)
        observer_secret = load_snapshot()
        observer_secret["observer_config"]["token"] = "secret"
        cases.append(observer_secret)

        with tempfile.TemporaryDirectory() as temporary_directory:
            for index, snapshot in enumerate(cases):
                with self.subTest(index=index), NormalizerState(
                    Path(temporary_directory) / f"state-{index}.sqlite3"
                ) as state, self.assertRaises(SnapshotError):
                    normalize_snapshot(snapshot, state)

    def test_normal_snapshot_discards_raw_summary_and_anonymizes_residents(self) -> None:
        snapshot = load_snapshot()
        snapshot["entities"][SUMMARY]["state"] = "Media and recent arrival for Randy at a private place"
        with tempfile.TemporaryDirectory() as temporary_directory, NormalizerState(
            Path(temporary_directory) / "state.sqlite3"
        ) as state:
            records, _result = normalize_snapshot(snapshot, state)
        prediction = records[0]
        self.assertEqual(prediction["resident_bucket"], "unknown")
        self.assertEqual(prediction["active_rooms"], ["Family Room", "Office"])
        self.assertEqual(prediction["context_flags"], ["summary_media", "summary_recent_arrival"])
        self.assertNotIn("summary", prediction)
        self.assertNotIn("Randy", json.dumps(prediction))

    def test_freshness_boundary_unknown_unavailable_and_observer_stalled(self) -> None:
        boundary = load_snapshot()
        boundary["entities"][TV]["last_changed"] = "2026-08-12T17:45:00Z"
        with tempfile.TemporaryDirectory() as temporary_directory, NormalizerState(
            Path(temporary_directory) / "boundary.sqlite3"
        ) as state:
            records, _ = normalize_snapshot(boundary, state)
            self.assertEqual(records[0]["signals"]["tv_active"], "inactive")

        stale = load_snapshot()
        stale["entities"][TV]["last_changed"] = "2026-08-12T17:44:59Z"
        stale["entities"][ROOM_PRESENCE]["state"] = "unknown"
        stale["entities"]["sensor.home_active_room"]["state"] = "unavailable"
        stale["entities"][OBSERVER_STALLED]["state"] = "on"
        with tempfile.TemporaryDirectory() as temporary_directory, NormalizerState(
            Path(temporary_directory) / "stale.sqlite3"
        ) as state:
            records, _ = normalize_snapshot(stale, state)
            signals = records[0]["signals"]
            self.assertEqual(signals["tv_active"], "stale")
            self.assertEqual(signals["room_presence"], "missing")
            self.assertEqual(signals["observer_health"], "missing")

    def test_unchanged_refresh_does_not_duplicate_and_meaningful_change_does(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "events.jsonl"
            with NormalizerState(root / "state.sqlite3") as state:
                first = normalize_and_append(load_snapshot(), state, output)
                second = normalize_and_append(
                    refresh(load_snapshot(), "2026-08-12T18:05:00Z"), state, output
                )
                changed = refresh(load_snapshot(), "2026-08-12T18:06:00Z")
                changed["entities"][ACTIVITY]["state"] = "Cooking"
                changed["entities"][ACTIVITY]["last_changed"] = "2026-08-12T18:06:00Z"
                third = normalize_and_append(changed, state, output)
            self.assertTrue(first["prediction_created"])
            self.assertFalse(second["prediction_created"])
            self.assertTrue(third["prediction_created"])
            lines = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertNotEqual(json.loads(lines[0])["episode_id"], json.loads(lines[1])["episode_id"])

    def test_snapshot_time_cannot_move_backward(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with NormalizerState(root / "state.sqlite3") as state:
                normalize_and_append(load_snapshot(), state, root / "events.jsonl")
                older = refresh(load_snapshot(), "2026-08-12T17:59:59Z")
                with self.assertRaisesRegex(SnapshotError, "backward"):
                    normalize_snapshot(older, state)

    def test_feedback_revision_associates_to_existing_episode_and_counters_are_audit_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "events.jsonl"
            with NormalizerState(root / "state.sqlite3") as state:
                normalize_and_append(load_snapshot(), state, output)
                confirm = refresh(load_snapshot(), "2026-08-12T18:05:00Z")
                confirm["entities"][CONFIRM]["last_changed"] = "2026-08-12T18:04:00Z"
                confirm["entities"][CONFIRMATIONS]["state"] = "1"
                confirmed = normalize_and_append(confirm, state, output)
                wrong = refresh(confirm, "2026-08-12T18:06:00Z")
                wrong["entities"][WRONG]["last_changed"] = "2026-08-12T18:05:30Z"
                wrong["entities"][CORRECTED]["state"] = "Dining"
                wrong["entities"][CORRECTIONS]["state"] = "1"
                revised = normalize_and_append(wrong, state, output)
            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(confirmed["feedback_created"], 1)
            self.assertEqual(revised["feedback_created"], 1)
            self.assertTrue(revised["counter_audit_consistent"])
            self.assertEqual(records[1]["episode_id"], records[0]["episode_id"])
            self.assertEqual(records[2]["episode_id"], records[0]["episode_id"])
            self.assertEqual(records[2]["corrected_activity"], "Dining")

            counter_only = refresh(wrong, "2026-08-12T18:07:00Z")
            counter_only["entities"][CONFIRMATIONS]["state"] = "50"
            with NormalizerState(root / "state.sqlite3") as state:
                result = normalize_and_append(counter_only, state, output)
            self.assertEqual(result["feedback_created"], 0)
            self.assertFalse(result["counter_audit_consistent"])

    def test_stable_opaque_ids_replay_and_namespace_separation(self) -> None:
        snapshot = load_snapshot()
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            with NormalizerState(Path(first_directory) / "state.sqlite3") as state:
                first, _ = normalize_snapshot(snapshot, state)
            with NormalizerState(Path(second_directory) / "state.sqlite3") as state:
                second, _ = normalize_snapshot(snapshot, state)
        self.assertEqual(first, second)
        prediction = first[0]
        self.assertRegex(prediction["episode_id"], r"^[0-9a-f]{64}$")
        self.assertRegex(prediction["source_event_id"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(prediction["episode_id"], prediction["source_event_id"])

    def test_true_append_preserves_inode_prefix_and_rejects_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "events.jsonl"
            output.write_text("existing\n", encoding="utf-8")
            inode = output.stat().st_ino
            append_records(output, [], output_mode="append")
            self.assertEqual(output.stat().st_ino, inode)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing\n")
            with self.assertRaisesRegex(SnapshotError, "append"):
                append_records(output, [], output_mode="atomic-replace")
            output.write_text("incomplete", encoding="utf-8")
            with self.assertRaisesRegex(SnapshotError, "incomplete"):
                append_records(output, [], output_mode="append")
            output.unlink()
            target = Path(temporary_directory) / "target.jsonl"
            target.write_text("", encoding="utf-8")
            output.symlink_to(target)
            with self.assertRaisesRegex(SnapshotError, "regular file"):
                append_records(output, [], output_mode="append")

    def test_socket_blocked_snapshot_to_continuous_ingest_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory, patch.object(
            socket, "socket", side_effect=AssertionError("network attempted")
        ):
            root = Path(temporary_directory)
            output = root / "events.jsonl"
            with NormalizerState(root / "normalizer.sqlite3") as state:
                normalize_and_append(load_snapshot(), state, output)
            counts = collect_continuous_file(
                output,
                root / "analytics.sqlite3",
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            report = build_report(
                root / "analytics.sqlite3",
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
        self.assertEqual(counts["episodes_inserted"], 1)
        self.assertEqual(report["episodes"], 1)
        self.assertFalse(report["privacy"]["network_used"])

    def test_ai_actions_must_remain_off(self) -> None:
        snapshot = load_snapshot()
        snapshot["entities"][AI_ACTIONS]["state"] = "on"
        with tempfile.TemporaryDirectory() as temporary_directory, NormalizerState(
            Path(temporary_directory) / "state.sqlite3"
        ) as state, self.assertRaisesRegex(SnapshotError, "must be off"):
            normalize_snapshot(snapshot, state)


if __name__ == "__main__":
    unittest.main()
