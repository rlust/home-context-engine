from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
ALERT = ROOT / "automations" / "home_context_signal_diagnostics_alert.json"


class SignalDiagnosticsAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(ALERT.read_text(encoding="utf-8"))

    def test_faults_wait_five_minutes_and_recovery_is_immediate(self) -> None:
        triggers = {trigger["id"]: trigger for trigger in self.config["triggers"]}
        fault_ids = {
            "investigate", "repair_proposed", "approval_needed",
            "verifying", "unavailable", "unknown",
        }
        self.assertEqual(fault_ids, set(triggers) - {"healthy", "resolved"})
        for trigger_id in fault_ids:
            self.assertEqual(triggers[trigger_id]["for"], {"minutes": 5})
        self.assertNotIn("for", triggers["healthy"])
        self.assertNotIn("for", triggers["resolved"])

    def test_actions_are_deduplicated_observe_only_notifications(self) -> None:
        serialized = json.dumps(self.config)
        self.assertEqual(serialized.count("persistent_notification.create"), 1)
        self.assertEqual(serialized.count("persistent_notification.dismiss"), 1)
        self.assertEqual(serialized.count("home_context_signal_diagnostics_alert"), 2)
        self.assertIn("AI Actions remains OFF", serialized)
        self.assertIn("/home-command/context#hc-signals", serialized)
        self.assertNotIn("notify.mobile_app", serialized)
        for forbidden in ("light.turn_", "switch.turn_", "lock.", "cover.", "button.press"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
