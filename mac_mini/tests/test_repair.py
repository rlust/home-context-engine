from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from mac_mini.home_context_analytics.diagnostics import (
    DiagnosticReplay,
    IssueStatus,
    detect_signal_issues,
)
from mac_mini.home_context_analytics.repair import (
    ManagedHelper,
    RepairTransactionError,
    append_repair_audit,
    execute_helper_repair,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "mac_mini" / "fixtures" / "garage_signal_replay.json"


class FakeHelperClient:
    def __init__(self, replay: DiagnosticReplay, *, ai_actions: bool = False):
        self.replay = replay
        helper = replay.helper
        self.helper = ManagedHelper(
            config_entry_id=helper.config_entry_id,
            config_hash="hash-before",
            entity_id=helper.entity_id,
            name=helper.name,
            device_class=helper.device_class,
            template=helper.template,
            source_entity_ids=helper.source_entity_ids,
            consumers=helper.consumers,
        )
        self.ai_actions = ai_actions
        self.writes: list[tuple[str, str, str]] = []
        self.corrupt_first_readback = False
        self.raise_after_first_write = False
        self._corrupted = False

    def ai_actions_enabled(self) -> bool:
        return self.ai_actions

    def fetch_diagnostic_replay(self, helper_entity_id: str) -> DiagnosticReplay:
        if helper_entity_id != self.replay.helper.entity_id:
            raise AssertionError("wrong helper lookup")
        return self.replay

    def fetch_helper(self, config_entry_id: str) -> ManagedHelper:
        if config_entry_id != self.helper.config_entry_id:
            raise AssertionError("wrong config entry lookup")
        return self.helper

    def update_helper_template(self, config_entry_id: str, *, template: str, expected_hash: str) -> None:
        if config_entry_id != self.helper.config_entry_id:
            raise AssertionError("wrong config entry update")
        if expected_hash != self.helper.config_hash:
            raise AssertionError("stale expected hash")
        self.writes.append((config_entry_id, template, expected_hash))
        old = self.helper
        fixture = self.replay.helper
        proposed = detect_signal_issues(self.replay)[0].proposal
        assert proposed is not None
        if template == proposed.proposed_template:
            sources = tuple(
                proposed.replacement_source if item == proposed.suspect_source else item
                for item in old.source_entity_ids
            )
            name = "Unexpected changed name" if self.corrupt_first_readback and not self._corrupted else old.name
            self._corrupted = self.corrupt_first_readback or self._corrupted
        elif template == proposed.rollback_template:
            sources = fixture.source_entity_ids
            name = fixture.name
        else:
            raise AssertionError("unexpected template")
        self.helper = replace(
            old,
            config_hash=f"hash-{len(self.writes)}",
            name=name,
            template=template,
            source_entity_ids=sources,
        )
        if self.raise_after_first_write and len(self.writes) == 1:
            raise RuntimeError("simulated uncertain write")


class RepairTests(unittest.TestCase):
    def replay(self) -> DiagnosticReplay:
        return DiagnosticReplay.from_payload(json.loads(FIXTURE.read_text(encoding="utf-8")))

    def finding(self):
        return detect_signal_issues(self.replay())[0]

    def test_dry_run_is_default_and_captures_backup_without_write(self) -> None:
        replay = self.replay()
        client = FakeHelperClient(replay)
        result = execute_helper_repair(detect_signal_issues(replay)[0], client)
        self.assertEqual(result.status, IssueStatus.APPROVAL_NEEDED)
        self.assertTrue(result.dry_run)
        self.assertFalse(result.wrote_configuration)
        self.assertEqual(client.writes, [])
        self.assertEqual(result.backup.config_hash, "hash-before")
        self.assertEqual([event.stage for event in result.audit], [
            "proposal", "approval", "safety", "revalidation", "fetch_before_write", "write"
        ])

    def test_live_write_requires_exact_issue_approval_before_client_access(self) -> None:
        client = FakeHelperClient(self.replay())
        with self.assertRaisesRegex(RepairTransactionError, "exact issue ID"):
            execute_helper_repair(self.finding(), client, dry_run=False)
        self.assertEqual(client.writes, [])

    def test_live_write_requires_durable_approval_reference(self) -> None:
        finding = self.finding()
        client = FakeHelperClient(self.replay())
        with self.assertRaisesRegex(RepairTransactionError, "durable owner approval reference"):
            execute_helper_repair(
                finding,
                client,
                dry_run=False,
                approved_issue_id=finding.issue_id,
            )
        self.assertEqual(client.writes, [])

    def test_ai_actions_on_blocks_even_dry_run(self) -> None:
        client = FakeHelperClient(self.replay(), ai_actions=True)
        with self.assertRaisesRegex(RepairTransactionError, "must remain off"):
            execute_helper_repair(self.finding(), client)
        self.assertEqual(client.writes, [])

    def test_fresh_evidence_drift_blocks_write(self) -> None:
        original = self.replay()
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["signals"][1]["last_updated"] = "2026-08-23T13:00:00Z"
        client = FakeHelperClient(DiagnosticReplay.from_payload(payload))
        with self.assertRaisesRegex(RepairTransactionError, "no longer matches"):
            execute_helper_repair(
                detect_signal_issues(original)[0],
                client,
                dry_run=False,
                approved_issue_id=detect_signal_issues(original)[0].issue_id,
                approval_reference="owner-event-123",
            )
        self.assertEqual(client.writes, [])

    def test_approved_write_reads_back_and_stops_at_physical_canary(self) -> None:
        replay = self.replay()
        finding = detect_signal_issues(replay)[0]
        client = FakeHelperClient(replay)
        result = execute_helper_repair(
            finding,
            client,
            dry_run=False,
            approved_issue_id=finding.issue_id,
            approval_reference="owner-event-123",
        )
        self.assertEqual(result.status, IssueStatus.VERIFYING)
        self.assertEqual(result.approval_reference, "owner-event-123")
        self.assertTrue(result.wrote_configuration)
        self.assertFalse(result.rolled_back)
        self.assertEqual(len(client.writes), 1)
        self.assertEqual(client.writes[0][2], "hash-before")
        self.assertIn("Garage PIR", result.physical_canary)
        self.assertEqual(result.readback.entity_id, result.backup.entity_id)
        self.assertEqual(result.readback.name, result.backup.name)
        self.assertEqual(result.readback.device_class, result.backup.device_class)
        self.assertEqual(result.readback.consumers, result.backup.consumers)
        self.assertNotEqual(result.readback.config_hash, result.backup.config_hash)
        self.assertEqual([event.stage for event in result.audit][-2:], ["readback", "canary"])

    def test_unrelated_readback_change_automatically_rolls_back_exact_backup(self) -> None:
        replay = self.replay()
        finding = detect_signal_issues(replay)[0]
        client = FakeHelperClient(replay)
        client.corrupt_first_readback = True
        result = execute_helper_repair(
            finding,
            client,
            dry_run=False,
            approved_issue_id=finding.issue_id,
            approval_reference="owner-event-123",
        )
        self.assertEqual(result.status, IssueStatus.INVESTIGATE)
        self.assertTrue(result.rolled_back)
        self.assertEqual(len(client.writes), 2)
        self.assertEqual(result.readback.template, result.backup.template)
        self.assertEqual(result.readback.name, result.backup.name)
        self.assertEqual(result.readback.source_entity_ids, result.backup.source_entity_ids)
        self.assertEqual([event.stage for event in result.audit][-2:], ["rollback", "rollback"])
        self.assertEqual(result.audit[-1].result, "verified")

    def test_uncertain_write_error_reads_back_and_rolls_back_if_mutated(self) -> None:
        replay = self.replay()
        finding = detect_signal_issues(replay)[0]
        client = FakeHelperClient(replay)
        client.raise_after_first_write = True
        result = execute_helper_repair(
            finding,
            client,
            dry_run=False,
            approved_issue_id=finding.issue_id,
            approval_reference="owner-event-123",
        )
        self.assertTrue(result.rolled_back)
        self.assertEqual(len(client.writes), 2)
        self.assertEqual(result.readback.template, result.backup.template)
        self.assertEqual(result.audit[-1].stage, "rollback")
        self.assertEqual(result.audit[-1].result, "verified")

    def test_protocol_surface_has_no_device_service_method(self) -> None:
        allowed = {
            "ai_actions_enabled",
            "fetch_diagnostic_replay",
            "fetch_helper",
            "update_helper_template",
        }
        client_methods = {
            name for name in FakeHelperClient.__dict__ if not name.startswith("_")
        }
        self.assertEqual(client_methods, allowed)

    def test_audit_trail_appends_privately_without_helper_template(self) -> None:
        replay = self.replay()
        client = FakeHelperClient(replay)
        result = execute_helper_repair(detect_signal_issues(replay)[0], client)
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "private" / "repair-audit.jsonl"
            recorded_at = datetime(2026, 8, 23, 14, tzinfo=timezone.utc)
            append_repair_audit(path, result, recorded_at=recorded_at)
            append_repair_audit(path, result, recorded_at=recorded_at)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(lines[0])["transaction"]["status"], "Approval needed")
            self.assertNotIn("is_state(", lines[0])


if __name__ == "__main__":
    unittest.main()
