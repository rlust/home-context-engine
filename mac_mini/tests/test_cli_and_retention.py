from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from mac_mini.home_context_analytics.cli import build_parser, main
from mac_mini.home_context_analytics.collector import collect_jsonl


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "mac_mini" / "fixtures" / "synthetic_events.jsonl"


class CliAndRetentionTests(unittest.TestCase):
    def test_cli_exposes_only_local_ingest_and_report_commands(self) -> None:
        parser = build_parser()
        choices = next(action for action in parser._actions if action.dest == "command").choices
        self.assertEqual(set(choices), {"ingest", "report"})

    def test_cli_writes_private_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = root / "episodes.sqlite3"
            report_path = root / "report.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "ingest",
                        "--input",
                        str(FIXTURE),
                        "--database",
                        str(database),
                        "--as-of",
                        "2026-08-12T18:00:00Z",
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["episodes_inserted"], 7)
            self.assertEqual(os.stat(database).st_mode & 0o777, 0o600)

            self.assertEqual(
                main(
                    [
                        "report",
                        "--database",
                        str(database),
                        "--as-of",
                        "2026-08-12T18:00:00Z",
                        "--output",
                        str(report_path),
                    ]
                ),
                0,
            )
            self.assertEqual(os.stat(report_path).st_mode & 0o777, 0o600)

    def test_retention_deletes_old_local_episodes_and_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with FIXTURE.open("r", encoding="utf-8") as stream:
                counts = collect_jsonl(
                    stream,
                    database,
                    retention_days=7,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            self.assertEqual(counts["purged"], 4)

    def test_reingest_is_idempotent_but_identifier_collision_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with FIXTURE.open("r", encoding="utf-8") as stream:
                collect_jsonl(
                    stream,
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            with FIXTURE.open("r", encoding="utf-8") as stream:
                counts = collect_jsonl(
                    stream,
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            self.assertEqual(counts["duplicates"], 13)

            collision = json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[0])
            collision["source_event_id"] = "different-source-event"
            with self.assertRaisesRegex(ValueError, "collision"):
                collect_jsonl(
                    io.StringIO(json.dumps(collision) + "\n"),
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )

    def test_invalid_record_rolls_back_entire_input_batch(self) -> None:
        valid_line = FIXTURE.read_text(encoding="utf-8").splitlines()[0]
        invalid_line = json.dumps({"kind": "service_call", "service": "light.turn_on"})
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with self.assertRaisesRegex(ValueError, "line 2"):
                collect_jsonl(
                    io.StringIO(valid_line + "\n" + invalid_line + "\n"),
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
