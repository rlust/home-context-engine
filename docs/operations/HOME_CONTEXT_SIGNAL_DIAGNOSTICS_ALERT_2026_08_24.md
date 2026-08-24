---
title: "Home Context Signal Diagnostics Alert 2026-08-24"
tags: [home-context, newark, home-assistant, diagnostics, alerting]
status: active
created: 2026-08-24
---

# Home Context Signal Diagnostics Alert

Randy authorized one deduplicated, observe-only alert after a diagnostics fault
persists for five minutes. The live Newark automation is
`automation.home_context_signal_diagnostics_alert` with configuration hash
`a861c7e72cf94995`.

It waits five continuous minutes for `Investigate`, `Repair proposed`,
`Approval needed`, `Verifying`, `unavailable`, or `unknown`. It then creates or
updates one local Home Assistant persistent notification using the fixed ID
`home_context_signal_diagnostics_alert`. The message presents the status,
sanitized evidence, dashboard link, and bounded proposal when available. It
explicitly states that AI Actions is OFF and no repair or device command ran.

`Healthy` or `Resolved` immediately dismisses only that fixed notification.
There is no mobile push, device service, repair action, automation reload,
Home Assistant restart, or Mac receiver change.

## Live proof

- The complete managed-API readback contained six fault triggers with
  `for: 5 minutes`, two immediate recovery triggers, and only
  `persistent_notification.create` plus `persistent_notification.dismiss`.
- Two canary creates using the same temporary ID produced exactly one active
  canary containing the second message. Dismissing that ID removed the canary.
- After cleanup, the canary and real diagnostics alert were absent because the
  live diagnostics state remained Healthy. The unrelated utility-meter
  notification was preserved.
- The automation remained ON in `single` mode with current run count zero.
  Signal Diagnostics remained Healthy on schema 5 with zero issues; AI Actions
  remained OFF; Observer and Snapshot Push remained ON.

## Rollback

Remove only `automation.home_context_signal_diagnostics_alert` through the
managed Home Assistant automation API, then dismiss
`home_context_signal_diagnostics_alert` if it is present. No restart is needed.
The repository copy of the exact deployed configuration is
`automations/home_context_signal_diagnostics_alert.json`.
