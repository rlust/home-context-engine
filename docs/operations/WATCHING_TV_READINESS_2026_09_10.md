# Watching TV: readiness review and proposed bounded trial

Decision: HOLD device-capable advancement. Continue measurement and prepare a
single-light, manually approved trial. No live rule, helper, gate or device
changes were made during this review.

## Verified evidence

Newark review around 18:27-18:31 EDT on September 10, 2026:

- AI Actions off; observer age 0 minutes; classification Relaxing / Watching TV.
- TV active and Family Room occupied both on. Diagnostics schema 5 Healthy,
  zero issues; generated 22:28:46Z, fresh until 22:38:46Z. This verifies a current
  report, not historical coverage or precision.
- Randy's person uses only device_tracker.iot2; Kim's only
  device_tracker.kim_iphone_12. Last-reported times: Randy person 17:46:03,
  source 17:44:50; Kim person 18:20:23, source 18:20:39 EDT. State-machine report
  times alone do not prove a fresh physical location sample.
- Recorder six-hour window returned complete pages for activity, TV active,
  Family Room occupancy and the two source trackers (has_more=false).
- Watching TV resumed at 14:34:30 before Family Room occupancy at 14:35:07.
  It remained selected across vacancies at 15:43:07-15:43:38 and
  16:39:06-16:40:32. These are observed evidence gaps, not confirmed false labels.
- TV active remained on throughout the queried window: no real TV-off transition
  was available to validate session termination. Initial boundary records are
  not actual transitions or fresh reports.
- Kim's tracker became unavailable at 17:31:36 and returned home at 18:20:23,
  overlapping the restart period. Post-repair clean departure/return validation
  for both residents remains incomplete. Raw locations are intentionally omitted.

## Gate assessment

- Overall 50 reviewed outcomes: unverified, not zero.
- Watching TV 20 independent reviewed sessions and >=90% precision: unverified.
- Calibration error <=10 percentage points: unverified.
- Historical required-signal coverage and adjacent-window drift: unverified.
- Private analytics host SSH timed out. Do not use August aggregate counts or
  confirmation-button totals as a current replacement.
- Global actions-gate consumer scan is pending/incomplete until separately
  confirmed; one inspected music approval consumer already exists.

## Action risks found

The observer TV branch accepts TV on AND (Family Room occupied OR any resident
home). Its confidence is a rule-derived score, not measured precision. A lighting
trial must require room occupancy independently and recheck it on approval.

Do not target light.family_room: it includes light.loft_wiz, violating the
promised room-only scope. The narrower light.family_room_lights group still
references missing light.tvled and unavailable light.family_walkway.

The existing Approve Denon Music Lighting automation targets that narrower
group at 45%, 2700 K. It is gated by AI Actions but shares the global Approve
button and has no TV-session identifier. Do not repurpose it or enable the
global gate just to test Watching TV.

Final consumer-scan result: partial=true. The time budget left 382 automations
unscanned, and two scripts could not be read through their config endpoints
(404). Zero returned matches is not proof that the gate has no consumers.
A final live read confirmed input_boolean.ai_actions_enabled remains off.

## Proposed trial contract (not deployed)

1. Start with light.family_room_lamp only: verified available, assigned to
   Family Room, supports brightness and 2200-6500 K. User selected 11%
   brightness on September 10, 2026. Proposed conservative defaults: preserve
   existing color/warmth and leave the lamp off if already off. These defaults
   are not user-selected settings. No live lighting change was made; readiness
   and explicit trial enablement remain required.
2. Dedicated Watching TV approval control and separate trial-enabled gate,
   default off; never share the music approval button. AI Actions stays off
   until readiness and all consumers are reviewed and enablement is approved.
3. Require Watching TV, fresh observer/diagnostics, actual TV availability/on,
   sustained Family Room presence, resident home, and sleep/guest/party off.
   Proposed dwell: two minutes; approval expires after two minutes. Recheck
   every condition at execution rather than trusting a displayed suggestion.
4. Bind approval to a unique session and one immutable target/brightness proposal.
   Apply at most once, never retry or reapply after a manual lighting change.
   A manual change cancels pending approval; no automatic adjustment loop.
5. Capture pre-action light state for explicit Undo. Undo must not overwrite an
   intervening user change. No automatic restoration on TV-off or vacancy.
6. Validate offline failure cases: unavailable TV/light, missing presence,
   stale reports, restarts, expired/duplicate approval, manual override, group
   scope drift and disabled gates. Then shadow-test with no device services.

Next safe steps: recover current private aggregate access, gather independent
Watching TV reviews, confirm the lamp settings, and finish the gate-consumer
audit. Next review target September 11, 2026, or when aggregate evidence is
available. This date does not create a scheduled automation.

## Follow-up: current aggregates and offline rehearsal, 19:00 EDT

The earlier LAN SSH timeout was not an analytics outage. The private Tailscale
hostname was reachable. Ran the installed report CLI read-only against the Mac
mini analytics database as of 2026-09-10T23:00:19Z, without exporting raw events
or changing services. Supersedes the earlier unverified-count limitation:

- 89 audit-consistent scored episodes; 88 confirmations, one wrong, one
  additional unsure episode (90 reviewed total). Overall scored accuracy 98.88%.
- Watching TV: 20 reviewed predicted-TV episodes, all confirmed; observed
  precision 100%. Meets the 20-sample and 90% observed-precision thresholds,
  not proof of general accuracy, recall or independence of viewing sessions.
- Overall expected calibration error 12.3 percentage points: does NOT meet
  the existing at-most-10-point gate. Do not silently substitute a favorable
  confidence bucket for this gate.
- 965 of 12,611 retained episodes have stale or missing signals. This is
  historical evidence, not proof that 965 actions would have been eligible.
- Adjacent 14-day windows have enough reviews for the report's drift check.
  Signal issue rate increased from 6.09% to 9.73%; investigate rather than
  interpreting current Healthy diagnostics as a clean historical record.

Read complete automations.yaml (465 top-level id blocks), scripts.yaml and
configuration.yaml through the read-only file API. Only the Observer description
and Denon music approval block mention ai_actions_enabled in automations.yaml;
no literal references were found in scripts.yaml. The Observer is not a device
consumer. The configured automation/script includes point to those files.
This improves the earlier timed-out scan but does NOT finish the loaded-consumer
audit: live state inventory contains 506 automation entities, including restored
entities and 12 non-restored IDs not matched by the textual file-ID extraction.
There are also 230 script entities not yet fully reconciled against file keys.
The config-get tool is unavailable on the current tool surface. Dynamic service
references, blueprint expansion, and external consumers remain unproven.

AI Actions was re-read as off. The Family Room lamp already reported brightness
28/255 (approximately 11%); this review did not set it.

Built dashboard/tv-preview as a local-only browser rehearsal with synthetic
signals, fixed lamp scope, user-selected 11%, two-minute expiration, single-use
preview approval and invalidation on guard/session/lamp changes. It cannot call
HA services, persist approvals or submit scored feedback. It is NOT installed
in the HA dashboard and is NOT a live action implementation. All 28 Node tests
pass. The page loaded in the Codex browser and its accessibility tree confirmed
the approval control, countdown, scenario selector and dated readiness metrics.
Mobile visual verification and live integration validation remain outstanding.

Next safe steps: reconcile remaining loaded consumers and review the calibration
and signal-health gaps. Keep AI Actions off. Next review target remains
September 11, 2026; no new schedule or restart was created.

## Subsequent reconciliation

See WATCHING_TV_AUDIT_FOLLOWUP_2026_09_10.md for the completed identifier
reconciliation and activity-level calibration analysis. All 472 non-restored
automation and 228 non-restored script IDs match the parsed YAML; the earlier
gaps were textual-extraction errors, not missing definitions. Forty of 41
referenced blueprint files were read; one absent blueprint has four unavailable
consumers. Dynamic/external and runtime-equivalence limitations remain.
TV's mean-confidence gap is 4.9 points, but the overall 12.3-point gate is
unchanged. Only one TV review follows the latest restart; the fixed exported
observer fingerprint still needs provenance verification. Keep AI Actions off.
