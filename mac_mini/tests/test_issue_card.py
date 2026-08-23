from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from mac_mini.home_context_analytics.diagnostics import DiagnosticReplay, detect_signal_issues
from mac_mini.home_context_analytics.issue_card import IssueCardState, build_issue_card_payload


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "mac_mini" / "fixtures" / "garage_signal_replay.json"
PREVIEW = ROOT / "dashboard" / "home_context_signal_issues_preview.json"


class IssueCardTests(unittest.TestCase):
    def finding(self):
        replay = DiagnosticReplay.from_payload(json.loads(FIXTURE.read_text(encoding="utf-8")))
        return detect_signal_issues(replay)[0]

    def test_payload_distinguishes_every_lifecycle_stage_and_safety_boundary(self) -> None:
        updated_at = datetime(2026, 8, 23, 14, tzinfo=timezone.utc)
        for stage in (
            "detected", "proposal_ready", "approval_pending", "verifying",
            "verification_failed", "resolved", "rolled_back",
        ):
            kwargs = {}
            if stage in {"verifying", "verification_failed", "resolved"}:
                kwargs["approval_reference"] = "owner-event-123"
            if stage in {"verification_failed", "resolved"}:
                kwargs["verification_result"] = "ON and clear transitions verified"
            if stage == "rolled_back":
                kwargs["rollback_result"] = "exact backup restored"
            with self.subTest(stage=stage):
                payload = build_issue_card_payload(
                    IssueCardState(self.finding(), stage, updated_at, **kwargs)
                )
                self.assertEqual(len(payload["lifecycle"]), 6)
                self.assertEqual(payload["safety"]["ai_actions"], "OFF")
                self.assertFalse(payload["safety"]["device_controls_available"])
                self.assertTrue(payload["safety"]["dry_run_default"])

    def test_stale_canary_is_verification_failed_with_corrective_path_visible(self) -> None:
        payload = build_issue_card_payload(
            IssueCardState(
                self.finding(),
                "verification_failed",
                datetime(2026, 8, 23, 14, 28, 23, tzinfo=timezone.utc),
                approval_reference="2d96ca3999d046fa875eeec77a3cb554fd5592e5ea4767061a9fe02512446598",
                verification_result="Replacement source was stale at canary time; no end-to-end transition propagated.",
            )
        )
        lifecycle = {item["key"]: item["state"] for item in payload["lifecycle"]}
        self.assertEqual(payload["state"], "Verification failed")
        self.assertTrue(payload["verification"]["failed"])
        self.assertEqual(lifecycle["verifying"], "failed")
        self.assertEqual(lifecycle["resolved"], "not_reached")
        self.assertEqual(lifecycle["rolled_back"], "available")
        self.assertIsNotNone(payload["proposed_mutation"])
        self.assertTrue(payload["rollback_available"])

    def test_verification_and_resolution_require_explicit_approval(self) -> None:
        updated_at = datetime(2026, 8, 23, 14, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "approval"):
            IssueCardState(self.finding(), "verifying", updated_at)
        with self.assertRaisesRegex(ValueError, "verification result"):
            IssueCardState(self.finding(), "resolved", updated_at, approval_reference="owner-event")

    def test_apply_is_enabled_only_for_an_explicitly_approved_pending_issue(self) -> None:
        updated_at = datetime(2026, 8, 23, 14, tzinfo=timezone.utc)
        pending = build_issue_card_payload(
            IssueCardState(self.finding(), "approval_pending", updated_at)
        )
        approved = build_issue_card_payload(
            IssueCardState(
                self.finding(),
                "approval_pending",
                updated_at,
                approval_reference="owner-event-123",
            )
        )
        verifying = build_issue_card_payload(
            IssueCardState(
                self.finding(),
                "verifying",
                updated_at,
                approval_reference="owner-event-123",
            )
        )
        self.assertFalse(pending["approval"]["apply_enabled"])
        self.assertTrue(approved["approval"]["apply_enabled"])
        self.assertFalse(verifying["approval"]["apply_enabled"])

    def test_card_is_full_width_responsive_and_has_no_service_action(self) -> None:
        view = json.loads(PREVIEW.read_text(encoding="utf-8"))
        self.assertEqual(view["type"], "sections")
        self.assertEqual(view["max_columns"], 4)
        self.assertEqual(view["sections"][0]["column_span"], 4)
        wrapper = view["sections"][0]["cards"][0]
        self.assertEqual(wrapper["type"], "vertical-stack")
        self.assertEqual(wrapper["grid_options"]["columns"], "full")
        serialized = json.dumps(view)
        self.assertIn("Detection", serialized)
        self.assertIn("Proposal", serialized)
        self.assertIn("Approval", serialized)
        self.assertIn("Verification", serialized)
        self.assertIn("Resolution", serialized)
        self.assertIn("Rollback", serialized)
        self.assertIn("AI Actions: **OFF**", serialized)
        self.assertIn("Diagnostics unavailable", serialized)
        self.assertIn("No healthy result is inferred", serialized)
        self.assertNotIn("perform-action", serialized)
        self.assertNotIn("tap_action", serialized)
        self.assertNotIn("service:", serialized)


if __name__ == "__main__":
    unittest.main()
