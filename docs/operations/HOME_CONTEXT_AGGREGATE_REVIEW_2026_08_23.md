---
title: "Newark Home Context Aggregate Review 2026-08-23"
tags: [newark, home-context, observe-only, measurement]
status: active
created: 2026-08-23
---

# Outcome

Completed the overdue privacy-safe aggregate review and kept Home Context in
observe-only measurement. The Phase 4 advancement gate does not pass. No device
action, Home Assistant restart, Tailscale change, service restart, secret access,
or raw household-data publication occurred.

# Live Newark evidence

Read from the Newark Home Assistant MCP endpoint on 2026-08-23:

- Home Assistant `2026.8.3`; Newark ha-mcp `8.3.0` current/latest.
- `light.smart_switch_kitchen` resolved to Newark `Kitchen Cans`.
- Observer ON, `mode: restart`, `current: 0`, hash
  `6b5fa7a109f6636a`; engine stalled OFF; observer age 2 minutes.
- Snapshot Push ON, `mode: queued`, `current: 0`, hash
  `48e5798fbb9f358e`.
- AI Actions OFF.
- HA feedback counters: 23 Confirmed, 1 Wrong, 0 Unsure since
  `2026-08-09 21:52:09`.

# Current Mac mini aggregate

Generated read-only from the deployed CLI at
`faa3c4836c9d22dab6ebb3ecf48a7b6d415caae3` against the existing private
`analytics.sqlite3`, as of `2026-08-23T13:25:00Z`:

- Schema 5; `network_used: false`; 4,827 episodes.
- 19 latest reviewed episode outcomes: 18 Confirmed, 1 Wrong, 0 Unsure.
- 4,808 episodes remain unreviewed.
- 20 append-only feedback events exist; one is a revision of an already
  reviewed episode, so the scoring denominator is 19.
- 0 rejected records for the database lifetime.
- Audit-consistent scored accuracy: 94.74%.
- Expected calibration error: 11.1%, above the 10-point gate.
- Signal issues: 320 episodes (6.63%): 299 missing, 21 stale.
- Drift is not ready: adjacent seven-day windows contain 6 and 13 reviewed
  episodes, below the required 20 in each.
- Per-activity scored samples: Daily Life 12, Working 4, Entertaining 2,
  Watching TV 1. Each observed branch has 100% branch precision, but no branch
  has the required 20 samples and no exact Phase 4 action target is designated.

The saved `report-first-live-20260813.json` is intentionally historical and
must not be used as the current aggregate. The deployed report command computes
review state, calibration, signal health, and drift directly from schema 5; a
missing `reviewed_at` column is not a schema gap because latest feedback is
joined by episode.

# HA-to-collector reconciliation

- HA click counters total 24 labels.
- The private database contains 20 append-only feedback events and 19 latest
  reviewed episode outcomes.
- The four-event click/event gap is consistent with HA measurement starting on
  August 9 while private collection begins on August 13; the database's first
  feedback event is August 13.
- One additional denominator difference is expected because one episode has a
  revised feedback event; reports score only the latest outcome per episode.
- Historical counters were preserved; no reset or synthetic label was created.

# Runtime and privacy proof

- Host: Randy's Mac mini, arm64.
- Receiver running on `127.0.0.1:8765`; it has never exited.
- Collector LaunchAgent is idle between runs with last exit `0`.
- Receiver and collector stderr logs are 0 bytes.
- Checked private artifacts are `0600`.
- BriefDash remains tailnet-only `8443 -> 127.0.0.1:8787`.
- Home Context remains tailnet-only `9443 -> 127.0.0.1:8765`.
- Funnel is absent.

# Advancement decision

| Gate | Required | Current | Result |
|---|---:|---:|---|
| Reviewed episodes | >=50 | 19 | Fail |
| Exact target activity | >=20 | best branch 12 | Fail |
| Target precision | >=90% | 100% for observed branches | Not eligible; sample gate fails |
| Calibration error | <=10 pp | 11.1 pp | Fail |
| Required-signal health | no stale/missing eligibility | 320 affected episodes | Fail |
| Drift readiness | >=20 reviewed in each adjacent window | 6 / 13 | Fail |

AI Actions must remain OFF and Hermes must not receive raw household data.

# Measurement-integrity repair

The only Wrong label read `predicted Daily Life, correct Daily Life`, which is
not a semantic correction. Live automation readback showed
`automation.home_context_mark_wrong` incremented the correction counter without
checking that the picker differed from the current prediction.

Applied a surgical config-API guard:

- Pre-change hash: `f367a4313c6af255`.
- Post-change hash: `64e97d34c85e5dec`.
- Same trigger, entity ID, `mode: queued`, and original valid-correction actions.
- A Wrong press now records a correction only when corrected activity differs
  from predicted activity.
- A same-activity press changes only the dashboard feedback text to explain
  that no correction was recorded.
- The live comparison template evaluated `false` for the current same-activity
  state before installation.
- Readback confirms the guard and valid/invalid branches; the automation is ON
  and idle. The existing correction counter and historical record remain 1.
- Observer and Snapshot Push hashes are unchanged; AI Actions remains OFF.

The cross-entity equality comparison has no native Home Assistant condition,
so the bounded Jinja comparison is the appropriate exception. No synthetic
button press was used for verification.

# Rollback

Write the pre-change description back and replace the outer `if` action with
its current `then` list through `ha_config_set_automation`, using a fresh config
hash. This restores the exact prior valid-correction action sequence without a
Home Assistant restart or full-system restore.

# Next milestone

Continue truthful feedback until the private report reaches at least 50 latest
reviewed episode outcomes. When using Wrong, select the actual different
activity first. Re-run this same aggregate review at 50 labels; do not enable a
device-capable Phase 4 pilot until every gate passes and the exact reversible
target, circuit breaker, and manual override are separately proven.
