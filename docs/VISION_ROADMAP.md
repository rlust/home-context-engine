# Home Context Engine — Vision & Roadmap

## The vision

Build a home that understands what is happening and offers the right help,
without becoming unpredictable or taking control away from its occupants.

User-approved direction, September 13, 2026: **fewer unnecessary interactions,
fewer wrong actions, and more trust**, not more automations. Classification and
adaptation are means to that outcome. Collect only the evidence needed for
useful household context; do not expand personal monitoring for its own sake.

## Standing principles

1. **Observe before acting.** `ai_actions_enabled` is the safety gate; it stays OFF until accuracy is proven.
2. **Richer sensing over more rules.** Per-room, per-activity awareness beats another hardcoded condition.
3. **Confidence is not permission.** Require fresh evidence, validated accuracy,
   explicit scope, safety guards and approval. Abstain on conflicting evidence.
4. **Investigate before removing.** "Dead-looking" config has repeatedly turned out to be load-bearing; a broken-looking helper is more often bugged than unused.
5. **Validate every sensor against history before trusting it.** A sensor that is always "on" is worse than no sensor — it silently pins a room to occupied.
6. **Specific beats generic.** Order activity branches most-specific first; require sustained presence + corroboration so passing through a room does not become an activity.
7. **Keep the plan document living.**
8. **Earn each phase.** Measurement justifies suggestion; suggestion justifies action.

## Outcomes and measurement

| Goal | Evidence of progress |
| --- | --- |
| Understand household and room activity | Session-based precision, missed transitions and transition delay, broken down by activity and rule version |
| Admit uncertainty | Stale/missing/conflicting signals visibly produce uncertainty; zero action eligibility with required evidence missing or stale |
| Learn from feedback | Reviews trace to the actual prediction and verified rule version; candidate changes are evaluated on subsequent, separate observations |
| Help without taking over | No unapproved or unexplained actions; manual changes win; track overrides, unwanted suggestions and repeated prompts |
| Make the system understandable | Compact Apple-style dashboard shows activity, room, evidence, uncertainty, proposed action, feedback receipt and safety state |
| Reduce household effort | Track accepted useful suggestions versus dismissals and corrections; establish a baseline before claiming time or effort saved |

Acceptance measures usefulness, not classification accuracy. Confidence is a
rule score until calibrated, not a measured probability. Repeated taps on the
same episode are not independent reviews. Missing evidence is unknown, not zero.

Existing device-action advancement gates remain: at least 50 scored reviewed
episodes overall, at least 20 for the exact target activity, observed target
precision at least 90%, overall calibration error at most 10 percentage points,
and separately verified stale-signal rejection, circuit breaker and manual
override. These are necessary, not sufficient; review provenance, current-rule
coverage and explicit deployment approval also matter. Do not relax thresholds
or increase confidence scores merely to pass a gate.

## Roadmap

Through-line: **awareness → measurement → suggestion → adaptation.**

- **Phase 1 — Situational awareness** ✅ observe-only mode + activity classification
- **Phase 1.5 — Room-level awareness** ✅ per-room occupancy + active-room sensor
- **Phase 1.6 — Extended room coverage** ✅ 11 rooms; sleep corroborated by Master mmWave
- **Phase 2 — Activity vocabulary** ✅ Working / Cooking / Listening to Music / Watching TV
- **Phase 3 — Measurement before action** ◀ context logging, dwell time, a "that was wrong" correction path (engine-stall monitoring added)
- **Phase 4 — Suggest, then adapt** — suggestion layer started (observe-only): measure usefulness separately from accuracy; progress to one explicitly approved, bounded action only after the gates pass. Never expand into locks, alarms, climate or other consequential domains without separate sign-off.
- **Phase 5 — Learn patterns** — learned typicals replace hardcoded windows; handle guests, travel, seasons

Phase labels above describe implemented capabilities, not blanket validation of
every activity. Automatic rule learning or self-deployment is not authorized.

## Execution order adopted September 13, 2026

1. **Trustworthy review provenance.** Verify the exporter's fixed observer
   fingerprint against a documented canonical representation of the deployed
   rules. Test rule changes, missing fingerprints and mismatches. Preserve
   historical labels; do not reattribute old reviews to new rules.
2. **Prospective measurement.** Collect independent post-change TV start, stop,
   vacancy and conflicting-signal reviews. Report coverage and latency alongside
   accuracy; evaluate calibration without fitting and testing on the same data.
3. **Live read-only explanation.** Bring evidence and review readiness into the
   existing Context view, with fresh/stale indicators and a persistent receipt.
   Distinguish classifier confidence from measured performance. Verify desktop
   and mobile; keep simulated preview approvals out of scored feedback.
4. **Server-side shadow trial.** Prepare a single Family Room lamp proposal at
   the user-selected 11%. Preserve warmth and leave an off lamp off as proposed
   conservative defaults. No device calls. Test session-bound, expiring,
   single-use approval; restart invalidation; manual-change cancellation;
   cross-client duplicate rejection; and fail-closed safety gates.
5. **One approved live trial.** After evidence and shadow checks pass, request
   explicit approval for the exact light/settings. Verify readback and guarded
   Undo. Do not enable the global gate if that also unlocks unrelated consumers.
6. **Expand only on demonstrated benefit.** Evaluate usefulness and unwanted
   interventions before adding another room or routine. Each scope earns its
   own validation and authorization.

Each milestone records implementation, tests, backup, deployment and live
validation separately. A local prototype is not a deployed capability.

## Latest evidence, not a fresh live audit

September 10 review: 89 scored episodes; 20 confirmed TV episodes across 15 UTC
dates; overall calibration error 12.3 points. Only one TV review followed the
latest restart at that review. All non-restored automation/script IDs were
reconciled; runtime and dynamic/external consumer limitations remain. The
exporter's supplied version fingerprint still needs verification. AI Actions
was last verified off on September 10, not rechecked by this planning update.

See `operations/WATCHING_TV_AUDIT_FOLLOWUP_2026_09_10.md`. Next work item is
milestone 1, followed by a fresh aggregate review; September 10 counts must not
be displayed as current live metrics. No future review is scheduled by this file.

## Sensor coverage

The home spans multiple floors and ~30 areas. Rooms with presence sensing wired
into the engine: Family Room, Kitchen, Office, Foyer, Master Bedroom, Master
Bath, Basement, Basement Landing, Theater, Shop, Upstairs Hall.

**Doors** (front, garage-entry, deck) and the two vehicle garage covers feed
arrival/departure awareness.

**Blind spots / wishlist hardware:** a dining-room presence sensor (would unlock
the "Dining" activity), kitchen appliance-power monitoring (would turn "Cooking"
from inference into evidence), and a living-room sensor. Master humidity could
drive shower detection via a trend helper; a dryer signal exists for a possible
"Laundry" activity.
