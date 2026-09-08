# Home Context operational checkpoint — 2026-09-08

This is a sanitized record of changes verified during the September 8 session,
not a continuously refreshed status report or a deployable production export.
Home Assistant remains authoritative. Private locations, device identifiers,
raw feedback, camera receipts, network addresses, and dashboard backups are
intentionally excluded.

## Dashboard changes applied and verified

- Feedback instructions now precede exterior monitoring. The guidance asks for
  one rating per distinct session and distinguishes Confirm, Wrong, and Unsure.
- Guidance checks observer age and stalled state before recommending a rating.
  Refreshing a browser is explicitly not described as refreshing the observer.
- Activity-change time is labeled separately from observer freshness. The
  headline no longer presents activity age as an ambiguous update age.
- Person badges and the People panel use the same canonical person entities,
  rather than mixing a wearable tracker with a phone-backed person state.
- People rows are expanded to one column. Location evidence shows the tracking
  source and its supplied location-sample timestamp, with an explicit unknown
  state when no source is assigned. Entity update time is not a GPS guarantee.
- Exterior activity and metadata-only camera trial receipts have clearer,
  read-only presentation. Camera event totals are not accuracy scores and the
  isolated trial does not affect occupancy, recommendations, or devices.
- The aggregate-confirmation progress bar was removed. Readiness now lists
  activity-level evidence requirements and the distinction between current
  diagnostics and historical coverage.

The written view was read back, and desktop and mobile renders were checked.
The original view was retained locally for rollback. Existing feedback actions,
room tools, and safety controls were preserved; no device command was issued.

## Measurement work recorded this session

- Feedback timestamps retain seconds, as documented in the earlier observation
  update.
- Confirmation logging now suppresses a repeated confirmation for the same
  mode/activity within 30 minutes of the last confirmed receipt. This is a
  limited duplicate guard, not a durable episode identifier or proof that
  sessions are independent.
- The existing private snapshot path gained a five-minute trigger through its
  observer-refresh branch. Configuration readback was verified; sustained
  diagnostic coverage still needs review over time.
- A local-only review archive was captured. Automatic recurring archiving was
  not established by this work, and no archive is included here.

## Remaining gates — not a claim of readiness

The dashboard does not yet have live, verified per-activity session counts.
Working, Watching TV, and Daily Life show pending review against a target of
20 independent reviewed sessions each. Pending does not mean zero. Aggregate
button counts must not be substituted for independent episodes or precision.

Before advancing, the private review must establish:

1. At least 50 reviewed outcomes overall and at least 20 independent reviewed
   samples for the exact activity proposed for a trial.
2. At least 90% precision for that activity, with confidence calibration error
   no greater than 10 percentage points.
3. Adequate required-signal health, diagnostic coverage, and drift evidence.
   A currently healthy report does not resolve earlier coverage gaps.
4. Separate approval for a bounded manual-approval trial. Any subsequent
   autonomous action requires its own approval and safety review.

AI Actions remained OFF at verification. These changes do not enable autonomous
control, broaden the camera trial, or export individual location history into
the private aggregate context pipeline.

## Repository boundary

This checkpoint updates documentation only. It does not synchronize production
HA storage, claim that older repository dashboard JSON matches the live view,
or deploy anything to Home Assistant. Live configuration backups and review
records remain private and local.
