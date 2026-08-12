from __future__ import annotations

import json
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from mac_mini.home_context_analytics.collector import collect_jsonl
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
            self.assertEqual(report["feedback"], {"confirmed": 4, "wrong": 1, "unsure": 1, "scored_accuracy": 0.8})
            self.assertEqual(report["per_activity_confusion"]["Daily Life"], {"Cooking": 1})
            self.assertEqual(report["signal_health"]["episodes_with_stale_or_missing"], 2)
            self.assertEqual(report["signal_health"]["episodes_with_missing"], 1)
            self.assertEqual(report["signal_health"]["episodes_with_stale"], 1)
            self.assertTrue(report["window_comparison"]["comparison_available"])
            self.assertFalse(report["window_comparison"]["drift_ready"])

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


if __name__ == "__main__":
    unittest.main()
