---
title: "Home Context Signal Diagnostics and Repair"
tags: [newark, home-context, diagnostics, repair, dashboard]
status: active
created: 2026-08-23
---

# Objective

Use the Newark Garage occupancy incident as the pilot for a reusable Home
Context workflow that detects contradictory or stale source signals, explains
the downstream effect, proposes a bounded repair, and verifies an approved
repair without enabling autonomous device actions.

# Pilot incident

`binary_sensor.garage_occupied` remained on because its template referenced
`binary_sensor.pir_motion_sensor_2_motion_detection`, an event-style output
that latched on. The same physical device's state-style output,
`binary_sensor.pir_motion_sensor_2_sensor_state_motion`, cleared normally.
The stale derived helper caused Garage to remain in `sensor.home_active_room`.

The production helper is already repaired. The detector must learn from a
recorded or synthetic replay of this incident; it must not reintroduce the bad
source into live Newark for testing.

# Detection model

The Mac-mini collector/reporting layer should evaluate each Home Context source
and derived helper for these issue classes:

1. A binary source remains active beyond a configurable duration while its
   reporting device or sibling state source has continued to update.
2. Same-device motion outputs disagree: an event/detection output remains on
   while a state/occupancy output has completed a repeatable on-to-off cycle.
3. Every canonical input to a derived helper is inactive, unavailable, or
   stale, but the derived helper remains active.
4. A required source is missing, unknown, unavailable, or older than its
   allowed freshness window.
5. A helper dependency has a healthier same-device candidate with compatible
   device class and observed clearing behavior.

Candidate replacements must never be selected by entity name alone. A repair
proposal requires same-device identity, compatible semantics/device class,
fresh history, repeatable on-to-off behavior, and a search of all known
consumers. Ambiguous candidates remain `Investigate`; they are not repairable.

# Dashboard feedback

Add an issue panel to Newark `home-command/context` with these states:

- `Healthy`
- `Investigate`
- `Repair proposed`
- `Approval needed`
- `Verifying`
- `Resolved`

Each issue must show the affected helper, suspect source, age/last transition,
comparison source, downstream effect, proposed mutation, confidence and why,
rollback, and the last verification result. The Garage replay should read like:

> Garage falsely active: PIR detection output stayed on after the device's
> state-motion output cleared. Proposed repair: replace only the stale source
> reference in Garage Occupied. Preserve its entity ID, device class, and both
> garage-door inputs.

The panel may offer `Review repair` and `Apply approved repair`. It must not
expose a generic device-control action, and it must visibly state that Home
Context AI Actions remains off.

# Repair transaction

An executable repair is allowed only after explicit owner approval for the
specific issue:

1. Fetch the current helper definition and config hash immediately before the
   write.
2. Save the exact rollback definition.
3. Revalidate the issue and replacement candidate against fresh state/history.
4. Apply one surgical helper reference change through the HA-managed config or
   Options Flow; no YAML file edit or restart.
5. Read back the complete helper definition and confirm unrelated inputs,
   entity ID, name, and device class are unchanged.
6. Verify the stale source has no unintended consumers and the replacement has
   the expected single consumer.
7. Run a state-transition canary. If physical motion is required, show the
   exact owner gate and keep the issue in `Verifying` until observed.
8. Roll back automatically if readback or non-physical verification fails.

This executor is configuration-repair only. It must never call a light, lock,
cover, climate, or other device service. `input_boolean.ai_actions_enabled`
must remain off.

# Deliverables and proof

- Typed diagnostic finding and repair-proposal artifacts in the schema-5
  private reporting path, excluding raw sensitive household data.
- Unit tests for every issue class, ambiguity/false-positive handling, stale
  history, consumer preservation, and rollback.
- A Garage incident replay proving detection and the exact proposed repair.
- Dashboard update with fetch-before-write backup, fresh config hash/readback,
  and desktop plus mobile visual QA.
- Approval-gated repair executor with dry-run as the default and an audit trail
  for proposal, approval, write, readback, canary, and rollback.
- Live Newark readback proving Observer healthy and AI Actions off before and
  after deployment.

# Ownership and rollout

Codex Builder M5 is accountable for repository discovery, implementation,
tests, and the deployment-ready handoff. Ralph Reporter reviews issue language,
evidence completeness, false-alarm presentation, and desktop/mobile dashboard
reporting. Bumble coordinates safety gates, live Newark verification, and the
final owner handoff.

Rollout order: offline Garage replay, private report output, dashboard
read-only issue card, then one separately approved helper-repair canary. No
general automatic repair mode is authorized by this plan.

# Rollback

Keep the current dashboard surgical backup and make a new pre-edit dashboard
backup before deployment. Dashboard rollback restores only the prior
`home-command/context` view. Helper rollback reapplies the exact fetched helper
definition through the same HA-managed flow. Neither rollback should require a
Home Assistant restart.
