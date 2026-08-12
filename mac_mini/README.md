# Mac mini read-only analytics pilot

This package is the smallest local Phase 3.2 learning lab for Newark Home
Context. It ingests **normalized transition episodes from a local JSONL stream**,
stores them in a private SQLite file, and produces deterministic aggregate
reports for human review or Hermes. It has no Home Assistant client, no network
client, and no device/service-call path. It requires Python 3.10 or newer and
uses only the Python standard library.

## Safety boundary

- Home Assistant remains the real-time observer and controller.
- `input_boolean.ai_actions_enabled` remains OFF. This package cannot read or
  change it.
- The accepted input is a strict whitelist. Service events and unknown fields
  are rejected; the whole input batch is rolled back on validation failure.
- Person names/IDs, camera, audio, messages, GPS, credentials, secrets, and
  tokens are rejected. Residents are reduced to `none`, `one`, `multiple`, or
  `unknown`.
- `stale` and `missing` are stored as distinct signal states from `inactive`.
- Raw episodes are removed after the configured retention period (30 days by
  default). Database and report files are mode `0600`.
- Reporting opens SQLite in read-only/query-only mode. Hermes receives only the
  report, never the raw database or JSONL feed.

The live HA adapter is intentionally **not part of this commit**. Adding a live
read-only event source requires Bumble review plus Randy's explicit credential
and access authorization. An adapter must map only these live helpers:

| Normalized field | Approved Newark source |
|---|---|
| `mode` | `input_select.home_context_mode` |
| `activity` | `input_select.home_current_activity` |
| `confidence` | `input_number.home_context_confidence` |
| `active_rooms` | `sensor.home_active_room` (12-room whitelist) |
| summary context | `input_text.home_context_summary` (derive approved flags; do not store raw text) |
| next prediction | `input_text.home_next_likely_activity` (future aggregate only; not stored in v1) |
| feedback | Confirm / Mark Wrong / Unsure buttons and corrected-activity selector |
| outcome audit | confirmation / correction / unsure counters and last-feedback helper |

## Normalized JSONL contract

Each episode is a `prediction` record. Feedback is a separate record linked by
anonymous `episode_id`. The synthetic fixture is the canonical example:
`mac_mini/fixtures/synthetic_events.jsonl`.

Every approved signal must appear in every prediction and be explicitly marked
`active`, `inactive`, `stale`, or `missing`; omission is rejected so an adapter
cannot silently turn unavailable evidence into absence. Non-response is not a
feedback record and remains explicitly unreviewed. A `wrong` record must provide
the corrected activity; `confirm` and `unsure` must not.

## Local proof commands

From the repository root:

```bash
python3 -m unittest discover -s mac_mini/tests -v

pilot_dir="$(mktemp -d)"
python3 -m mac_mini.home_context_analytics.cli ingest \
  --input mac_mini/fixtures/synthetic_events.jsonl \
  --database "$pilot_dir/episodes.sqlite3" \
  --retention-days 30 \
  --as-of 2026-08-12T18:00:00Z

python3 -m mac_mini.home_context_analytics.cli report \
  --database "$pilot_dir/episodes.sqlite3" \
  --as-of 2026-08-12T18:00:00Z \
  --window-days 7 \
  --format markdown
```

The report includes the reviewed denominator, Confirm/Wrong/Unsure counts,
unreviewed volume, per-activity confusion, confidence buckets, stale/missing
signal rate, and adjacent drift-ready windows. `Unsure` is reviewed but excluded
from scored accuracy.

## Pilot success and Phase 4 boundary

The implementation pilot succeeds when the same synthetic input always yields
the same report, invalid/private input is rejected atomically, network access is
absent, reporting cannot mutate SQLite, retention works, and a Mac mini manual
run reproduces the package tests. Those are software-safety criteria, **not**
evidence that the household classifier is accurate.

The report marks a drift comparison ready only when both adjacent windows have
at least 20 reviewed episodes. Any later Phase 4 proposal still needs the agreed
human evidence gate: at least 50 reviewed episodes overall, at least 20 for the
exact target activity, target-branch precision of at least 90%, confidence
calibration error within 10 percentage points, zero eligibility when required
signals are stale/missing, and a separately demonstrated circuit breaker and
manual override. This package cannot enable or perform an action.

## Reviewed launch path (not deployed)

1. Review and commit this implementation; run the full package tests on the Mac
   mini checkout.
2. Obtain Randy's approval for a narrowly scoped, read-only HA event/export
   credential. Build and separately review the normalizer; it may emit only the
   documented JSONL fields and may not expose any service-call method.
3. Choose private local paths outside synced folders, create them mode `0700`,
   and validate a manual one-shot ingest plus report first.
4. Copy `launchd/xyz.buzz.home-context-analytics.plist.example` to
   `~/Library/LaunchAgents/xyz.buzz.home-context-analytics.plist`, replace every
   placeholder with an explicit local path, run `plutil -lint`, and only then
   bootstrap it with `launchctl bootstrap gui/$(id -u) ...`.
5. Verify that stopping the job changes no HA helper, observer, automation, or
   device state. Verify the generated report against the counters shown in the
   Home Context dashboard.

## Rollback

No rollback is needed in HA because this pilot does not change HA. On the Mac
mini, unload the optional job with:

```bash
launchctl bootout gui/$(id -u) \
  "$HOME/Library/LaunchAgents/xyz.buzz.home-context-analytics.plist"
```

Move the plist aside to prevent relaunch. Keep the SQLite file for review, or
delete it only after Randy explicitly approves removal. The local database and
reports contain no credentials, but they do contain private household-derived
aggregates and must remain local.
