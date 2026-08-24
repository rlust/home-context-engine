from __future__ import annotations

import json
import io
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from mac_mini.home_context_analytics.collector import collect_continuous_file, collect_jsonl
from mac_mini.home_context_analytics.report import build_report, report_json


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "mac_mini" / "fixtures" / "synthetic_events.jsonl"


class EndToEndTests(unittest.TestCase):
    def test_synthetic_collector_to_deterministic_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with FIXTURE.open("r", encoding="utf-8") as stream:
                counts = collect_jsonl(
                    stream,
                    database,
                    retention_days=30,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            self.assertEqual(
                counts,
                {"episodes_inserted": 7, "feedback_inserted": 6, "duplicates": 0, "purged": 0},
            )
            report = build_report(
                database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                window_days=7,
            )
            self.assertEqual(report["reviewed_denominator"], 6)
            self.assertEqual(report["feedback"]["confirmed"], 4)
            self.assertEqual(report["feedback"]["wrong"], 1)
            self.assertEqual(report["feedback"]["unsure"], 1)
            self.assertEqual(report["feedback"]["audit_consistent_scored"], 5)
            self.assertEqual(report["feedback"]["audit_inconsistent"], 0)
            self.assertEqual(report["feedback"]["scored_accuracy"], 0.8)
            self.assertEqual(report["per_activity_confusion"]["Daily Life"], {"Cooking": 1})
            self.assertEqual(report["signal_health"]["episodes_with_stale_or_missing"], 2)
            self.assertEqual(report["signal_health"]["episodes_with_missing"], 1)
            self.assertEqual(report["signal_health"]["episodes_with_stale"], 1)
            self.assertTrue(report["window_comparison"]["comparison_available"])
            self.assertFalse(report["window_comparison"]["drift_ready"])
            self.assertEqual(report["confidence_buckets"]["90-99"]["mean_predicted_confidence"], 0.935)
            self.assertEqual(report["confidence_buckets"]["90-99"]["absolute_calibration_gap"], 0.065)
            self.assertEqual(report["expected_calibration_error"], 0.232)

            first = report_json(report)
            second = report_json(
                build_report(
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                    window_days=7,
                )
            )
            self.assertEqual(first, second)

    def test_collection_and_reporting_never_open_network_socket(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory, patch.object(
            socket, "socket", side_effect=AssertionError("network access attempted")
        ):
            database = Path(temporary_directory) / "episodes.sqlite3"
            with FIXTURE.open("r", encoding="utf-8") as stream:
                collect_jsonl(
                    stream,
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            report = build_report(
                database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            self.assertFalse(report["privacy"]["network_used"])

    def test_continuous_collection_never_opens_network_socket(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "events.jsonl"
            input_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            with patch.object(socket, "socket", side_effect=AssertionError("network access attempted")):
                counts = collect_continuous_file(
                    input_path,
                    root / "episodes.sqlite3",
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            self.assertEqual(counts["episodes_inserted"], 7)

    def test_report_connection_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with FIXTURE.open("r", encoding="utf-8") as stream:
                collect_jsonl(
                    stream,
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            before = database.read_bytes()
            build_report(database, as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc))
            self.assertEqual(before, database.read_bytes())

    def test_as_of_excludes_future_episode_and_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with FIXTURE.open("r", encoding="utf-8") as stream:
                collect_jsonl(
                    stream,
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            report = build_report(
                database,
                as_of=datetime(2026, 7, 28, 13, 0, 30, tzinfo=timezone.utc),
            )
            self.assertEqual(report["episodes"], 1)
            self.assertEqual(report["reviewed_denominator"], 0)

    def test_latest_visible_feedback_revision_wins_with_event_id_tie_break(self) -> None:
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        revision_wrong = {
            "kind": "feedback",
            "source_event_id": "40000000-0000-4000-8000-000000000001",
            "episode_id": "20000000-0000-4000-8000-000000000001",
            "occurred_at": "2026-07-28T13:02:00Z",
            "outcome": "wrong",
            "corrected_activity": "Cooking",
            "audit_consistent": True,
            "audit_issues": [],
        }
        tie_break_confirm = {
            "kind": "feedback",
            "source_event_id": "50000000-0000-4000-8000-000000000001",
            "episode_id": "20000000-0000-4000-8000-000000000001",
            "occurred_at": "2026-07-28T13:03:00Z",
            "outcome": "confirm",
            "corrected_activity": None,
            "audit_consistent": True,
            "audit_issues": [],
        }
        tie_break_wrong = {
            "kind": "feedback",
            "source_event_id": "40000000-0000-4000-8000-000000000002",
            "episode_id": "20000000-0000-4000-8000-000000000001",
            "occurred_at": "2026-07-28T13:03:00Z",
            "outcome": "wrong",
            "corrected_activity": "Cooking",
            "audit_consistent": True,
            "audit_issues": [],
        }
        content = "\n".join(
            [
                lines[0],
                lines[1],
                json.dumps(revision_wrong),
                json.dumps(tie_break_wrong),
                json.dumps(tie_break_confirm),
            ]
        ) + "\n"
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            collect_jsonl(
                stream=io.StringIO(content),
                database=database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            before_revision = build_report(
                database, as_of=datetime(2026, 7, 28, 13, 1, 30, tzinfo=timezone.utc)
            )
            self.assertEqual(before_revision["feedback"]["confirmed"], 1)
            revised = build_report(
                database, as_of=datetime(2026, 7, 28, 13, 2, tzinfo=timezone.utc)
            )
            self.assertEqual(revised["feedback"]["confirmed"], 0)
            self.assertEqual(revised["feedback"]["wrong"], 1)
            tie_broken = build_report(
                database, as_of=datetime(2026, 7, 28, 13, 3, tzinfo=timezone.utc)
            )
            self.assertEqual(tie_broken["feedback"]["confirmed"], 1)
            self.assertEqual(tie_broken["feedback"]["wrong"], 0)
            mutated_replay = dict(tie_break_confirm)
            mutated_replay["outcome"] = "unsure"
            with self.assertRaisesRegex(ValueError, "collision"):
                collect_jsonl(
                    io.StringIO(json.dumps(mutated_replay) + "\n"),
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
