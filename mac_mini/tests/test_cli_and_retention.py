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
from mac_mini.home_context_analytics.collector import collect_continuous_file, collect_jsonl
from mac_mini.home_context_analytics.report import build_report
from mac_mini.home_context_analytics.store import LocalStore


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "mac_mini" / "fixtures" / "synthetic_events.jsonl"


class CliAndRetentionTests(unittest.TestCase):
    def test_cli_exposes_only_local_ingest_and_report_commands(self) -> None:
        parser = build_parser()
        choices = next(action for action in parser._actions if action.dest == "command").choices
        self.assertEqual(
            set(choices), {"ingest", "ingest-continuous", "normalize-snapshot", "report"}
        )
        args = parser.parse_args(["ingest", "--input", "events.jsonl", "--database", "pilot.sqlite3"])
        self.assertEqual(args.retention_days, 45)
        self.assertEqual(args.drift_window_days, 14)

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
                    drift_window_days=3,
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
            collision["activity"] = "Cooking"
            with self.assertRaisesRegex(ValueError, "collision"):
                collect_jsonl(
                    io.StringIO(json.dumps(collision) + "\n"),
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )

    def test_retention_requires_drift_margin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory, self.assertRaisesRegex(
            ValueError, "greater than twice"
        ):
            with FIXTURE.open("r", encoding="utf-8") as stream:
                collect_jsonl(
                    stream,
                    Path(temporary_directory) / "episodes.sqlite3",
                    retention_days=28,
                    drift_window_days=14,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )

    def test_report_enforces_stored_retention_margin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with FIXTURE.open("r", encoding="utf-8") as stream:
                collect_jsonl(
                    stream,
                    database,
                    retention_days=30,
                    drift_window_days=14,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                )
            with self.assertRaisesRegex(ValueError, "retention"):
                build_report(
                    database,
                    as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
                    window_days=15,
                )

    def test_continuous_bad_record_does_not_block_later_data_and_quarantine_is_visible(self) -> None:
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        bad = json.dumps({"kind": "service_call", "service": "light.turn_on"})
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "events.jsonl"
            database = root / "episodes.sqlite3"
            input_path.write_text(lines[0] + "\n" + bad + "\n" + bad + "\n", encoding="utf-8")
            first = collect_continuous_file(
                input_path,
                database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(first["episodes_inserted"], 1)
            self.assertEqual(first["rejected_records"], 2)
            self.assertEqual(first["quarantined_distinct"], 1)

            with input_path.open("a", encoding="utf-8") as stream:
                stream.write(lines[2] + "\n")
            second = collect_continuous_file(
                input_path,
                database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(second["episodes_inserted"], 1)
            self.assertEqual(second["rejected_records"], 0)
            third = collect_continuous_file(
                input_path,
                database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(third["episodes_inserted"], 0)
            report = build_report(
                database, as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc)
            )
            self.assertEqual(report["episodes"], 2)
            self.assertEqual(
                report["rejected_records"],
                {
                    "scope": "database_lifetime",
                    "active_distinct": 1,
                    "pruned_distinct": 0,
                    "total_distinct": 1,
                    "active_occurrences": 2,
                    "pruned_occurrences": 0,
                    "total_occurrences": 2,
                },
            )
            self.assertNotIn(bad.encode("utf-8"), database.read_bytes())

    def test_continuous_waits_for_complete_final_line(self) -> None:
        line = FIXTURE.read_text(encoding="utf-8").splitlines()[0]
        split_at = len(line) // 2
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "events.jsonl"
            database = root / "episodes.sqlite3"
            input_path.write_text(line[:split_at], encoding="utf-8")
            first = collect_continuous_file(
                input_path,
                database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(first["episodes_inserted"], 0)
            self.assertEqual(first["rejected_records"], 0)
            with input_path.open("a", encoding="utf-8") as stream:
                stream.write(line[split_at:] + "\n")
            second = collect_continuous_file(
                input_path,
                database,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(second["episodes_inserted"], 1)

    def test_quarantine_pruning_preserves_lifetime_totals(self) -> None:
        bad_one = json.dumps({"kind": "service_call", "service": "light.turn_on"})
        bad_two = json.dumps({"kind": "service_call", "service": "lock.unlock"})
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "events.jsonl"
            database = root / "episodes.sqlite3"
            input_path.write_text(bad_one + "\n" + bad_two + "\n", encoding="utf-8")
            counts = collect_continuous_file(
                input_path,
                database,
                max_quarantine_distinct=1,
                as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(counts["quarantine_pruned"], 1)
            report = build_report(
                database, as_of=datetime(2026, 8, 12, 18, tzinfo=timezone.utc)
            )
            self.assertEqual(report["rejected_records"]["active_distinct"], 1)
            self.assertEqual(report["rejected_records"]["pruned_distinct"], 1)
            self.assertEqual(report["rejected_records"]["total_distinct"], 2)
            self.assertEqual(report["rejected_records"]["total_occurrences"], 2)

    def test_schema_one_feedback_migrates_to_append_only_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "episodes.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.executescript(
                    """
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    INSERT INTO metadata VALUES ('schema_version', '1');
                    CREATE TABLE episodes (
                        episode_id TEXT PRIMARY KEY, source_event_id TEXT NOT NULL UNIQUE,
                        occurred_at TEXT NOT NULL, mode TEXT NOT NULL, activity TEXT NOT NULL,
                        confidence INTEGER NOT NULL, active_rooms_json TEXT NOT NULL,
                        resident_bucket TEXT NOT NULL, signals_json TEXT NOT NULL,
                        observer_version TEXT NOT NULL
                    );
                    INSERT INTO episodes VALUES (
                        'legacy-episode', 'legacy-prediction', '2026-08-01T12:00:00Z',
                        'Active', 'Working', 80, '[]', 'one', '{}', 'legacy-version'
                    );
                    CREATE TABLE feedback (
                        episode_id TEXT PRIMARY KEY, source_event_id TEXT NOT NULL UNIQUE,
                        occurred_at TEXT NOT NULL, outcome TEXT NOT NULL,
                        corrected_activity TEXT
                    );
                    INSERT INTO feedback VALUES (
                        'legacy-episode', 'legacy-feedback', '2026-08-01T12:01:00Z',
                        'confirm', NULL
                    );
                    """
                )
            with LocalStore(database) as store:
                version = store.connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()[0]
                migrated = store.connection.execute(
                    """
                    SELECT outcome, audit_consistent, audit_issues_json
                    FROM feedback_events WHERE source_event_id = 'legacy-feedback'
                    """
                ).fetchone()
                legacy_table = store.connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'feedback'"
                ).fetchone()
            self.assertEqual(version, "4")
            self.assertEqual(tuple(migrated), ("confirm", 1, "[]"))
            self.assertIsNone(legacy_table)

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
