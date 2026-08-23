from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from mac_mini.home_context_analytics.diagnostics import (
    DiagnosticError,
    DiagnosticReplay,
    IssueCode,
    IssueStatus,
    detect_signal_issues,
    diagnostic_report_payload,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "mac_mini" / "fixtures" / "garage_signal_replay.json"


class DiagnosticTests(unittest.TestCase):
    def replay_payload(self) -> dict[str, object]:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_offline_garage_replay_proposes_exact_source_replacement(self) -> None:
        replay = DiagnosticReplay.from_payload(self.replay_payload())
        findings = detect_signal_issues(replay)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.status, IssueStatus.REPAIR_PROPOSED)
        self.assertEqual(finding.helper_entity_id, "binary_sensor.garage_occupied")
        self.assertEqual(finding.suspect_age_seconds, 2160)
        self.assertIn(IssueCode.STUCK_ACTIVE, finding.issue_codes)
        self.assertIn(IssueCode.SIBLING_DISAGREEMENT, finding.issue_codes)
        self.assertIn(IssueCode.DERIVED_ACTIVE_WITHOUT_CANONICAL_INPUT, finding.issue_codes)
        self.assertIn(IssueCode.HEALTHIER_SAME_DEVICE_CANDIDATE, finding.issue_codes)
        self.assertIsNotNone(finding.proposal)
        proposal = finding.proposal
        assert proposal is not None
        self.assertEqual(
            proposal.replacement_source,
            "binary_sensor.pir_motion_sensor_2_sensor_state_motion",
        )
        self.assertIn(proposal.replacement_source, proposal.proposed_template)
        self.assertNotIn(proposal.suspect_source, proposal.proposed_template)
        self.assertIn("binary_sensor.gdo1_motion", proposal.proposed_template)
        self.assertIn("binary_sensor.grgdo1_motion", proposal.proposed_template)
        self.assertEqual(proposal.preserved_consumers, ("sensor.home_active_room",))

    def test_report_payload_excludes_raw_transition_history(self) -> None:
        replay = DiagnosticReplay.from_payload(self.replay_payload())
        payload = diagnostic_report_payload(replay, detect_signal_issues(replay))
        serialized = json.dumps(payload, sort_keys=True)
        self.assertEqual(payload["schema_version"], 5)
        self.assertFalse(payload["privacy"]["network_used"])
        self.assertNotIn("transitions", serialized)
        self.assertNotIn("occurred_at", serialized)

    def test_detection_never_opens_network_socket(self) -> None:
        replay = DiagnosticReplay.from_payload(self.replay_payload())
        with patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
            findings = detect_signal_issues(replay)
        self.assertEqual(len(findings), 1)

    def test_name_only_candidate_is_not_considered(self) -> None:
        payload = self.replay_payload()
        payload["signals"][1]["device_id"] = "different-device"
        findings = detect_signal_issues(DiagnosticReplay.from_payload(payload))
        self.assertEqual(findings, ())

    def test_one_clear_cycle_is_not_enough_evidence(self) -> None:
        payload = self.replay_payload()
        payload["signals"][1]["transitions"] = payload["signals"][1]["transitions"][:2]
        findings = detect_signal_issues(DiagnosticReplay.from_payload(payload))
        self.assertEqual(findings, ())

    def test_stale_candidate_is_not_enough_evidence(self) -> None:
        payload = self.replay_payload()
        payload["signals"][1]["last_updated"] = "2026-08-23T13:00:00Z"
        findings = detect_signal_issues(DiagnosticReplay.from_payload(payload))
        self.assertEqual(findings, ())

    def test_ambiguous_candidates_remain_investigate_without_proposal(self) -> None:
        payload = self.replay_payload()
        second = deepcopy(payload["signals"][1])
        second["entity_id"] = "binary_sensor.garage_pir_secondary_state"
        payload["signals"].append(second)
        finding = detect_signal_issues(DiagnosticReplay.from_payload(payload))[0]
        self.assertEqual(finding.status, IssueStatus.INVESTIGATE)
        self.assertIsNone(finding.proposal)
        self.assertEqual(len(finding.ambiguous_candidates), 2)

    def test_active_source_below_timeout_is_not_flagged(self) -> None:
        payload = self.replay_payload()
        payload["signals"][0]["last_changed"] = "2026-08-23T13:30:00Z"
        findings = detect_signal_issues(DiagnosticReplay.from_payload(payload))
        self.assertEqual(findings, ())

    def test_required_missing_source_is_investigate_without_repair(self) -> None:
        payload = self.replay_payload()
        payload["signals"][2]["state"] = "unavailable"
        finding = detect_signal_issues(DiagnosticReplay.from_payload(payload))[0]
        self.assertEqual(finding.status, IssueStatus.INVESTIGATE)
        self.assertEqual(finding.issue_codes, (IssueCode.REQUIRED_SOURCE_UNHEALTHY,))
        self.assertIsNone(finding.proposal)

    def test_required_source_age_is_enforced_only_when_configured(self) -> None:
        payload = self.replay_payload()
        payload["signals"][2]["last_updated"] = "2026-08-23T12:00:00Z"
        self.assertTrue(
            any(
                finding.status == IssueStatus.REPAIR_PROPOSED
                for finding in detect_signal_issues(DiagnosticReplay.from_payload(payload))
            )
        )
        payload["signals"][2]["max_age_seconds"] = 300
        findings = detect_signal_issues(DiagnosticReplay.from_payload(payload))
        unhealthy = [
            finding
            for finding in findings
            if finding.issue_codes == (IssueCode.REQUIRED_SOURCE_UNHEALTHY,)
        ]
        self.assertEqual(len(unhealthy), 1)
        self.assertEqual(unhealthy[0].suspect_source, "binary_sensor.gdo1_motion")

    def test_active_helper_with_all_sources_off_is_a_standalone_contradiction(self) -> None:
        payload = self.replay_payload()
        payload["signals"][0]["state"] = "off"
        payload["signals"][0]["last_changed"] = "2026-08-23T13:33:00Z"
        payload["signals"][0]["last_updated"] = "2026-08-23T13:33:00Z"
        findings = detect_signal_issues(DiagnosticReplay.from_payload(payload))
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].issue_codes,
            (IssueCode.DERIVED_ACTIVE_WITHOUT_CANONICAL_INPUT,),
        )
        self.assertEqual(findings[0].status, IssueStatus.INVESTIGATE)
        self.assertIsNone(findings[0].proposal)

    def test_report_has_explicit_healthy_status_when_no_issue_exists(self) -> None:
        payload = self.replay_payload()
        payload["helper"]["state"] = "off"
        payload["signals"][0]["state"] = "off"
        payload["signals"][0]["last_changed"] = "2026-08-23T13:33:00Z"
        payload["signals"][0]["last_updated"] = "2026-08-23T13:33:00Z"
        replay = DiagnosticReplay.from_payload(payload)
        report = diagnostic_report_payload(replay, detect_signal_issues(replay))
        self.assertEqual(report["overall_status"], "Healthy")
        self.assertEqual(report["issue_count"], 0)

    def test_windows_and_minimum_cycles_must_be_safe(self) -> None:
        replay = DiagnosticReplay.from_payload(self.replay_payload())
        with self.assertRaises(DiagnosticError):
            detect_signal_issues(replay, active_timeout=timedelta(0))
        with self.assertRaises(DiagnosticError):
            detect_signal_issues(replay, minimum_clear_cycles=0)

    def test_replay_rejects_sensitive_or_unknown_fields(self) -> None:
        payload = self.replay_payload()
        payload["signals"][0]["person_name"] = "private"
        with self.assertRaises(DiagnosticError):
            DiagnosticReplay.from_payload(payload)


if __name__ == "__main__":
    unittest.main()
