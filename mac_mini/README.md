# Mac mini read-only analytics pilot

This package is the smallest local Phase 3.2 learning lab for Newark Home
Context. It ingests **normalized transition episodes from a local JSONL stream**,
stores them in a private SQLite file, and produces deterministic aggregate
reports for human review or Hermes. It has no Home Assistant client, no network
client, and no device/service-call path. It requires Python 3.10 or newer and
uses only the Python standard library.

Phase 3.3 adds a **transport-neutral snapshot normalizer**. It accepts one
complete JSON object supplied by a separate future transport, converts only the
approved Newark states into the Phase 3.2 JSONL contract, and true-appends the
records locally. It contains no HA URL/token, REST/WebSocket/MCP client,
subprocess fetch, network import, or service-call capability.

The unresolved next decision is the read-only snapshot transport: a later,
separately reviewed component must obtain these exact entities from Newark and
write the complete local snapshot file. This phase does not choose REST versus
WebSocket/MCP, create a credential, or authorize a connection. Building that
transport and deploying it are separate approval gates.

## Safety boundary

- Home Assistant remains the real-time observer and controller.
- `input_boolean.ai_actions_enabled` remains OFF. This package cannot read or
  change it.
- The accepted input is a strict whitelist. Service events and unknown fields
  are rejected. One-shot `ingest` is atomic; persistent `ingest-continuous`
  checkpoints each complete line and quarantines a bad line without blocking
  later records.
- Person names/IDs, camera, audio, messages, GPS, credentials, secrets, and
  tokens are rejected. Residents are reduced to `none`, `one`, `multiple`, or
  `unknown`.
- `stale` and `missing` are stored as distinct signal states from `inactive`.
- Raw episodes are removed after the configured retention period (45 days by
  default). Retention must be greater than twice the drift window. Database and
  report files are mode `0600`.
- Reporting opens SQLite in read-only/query-only mode. Hermes receives only the
  report, never the raw database or JSONL feed.

The live HA adapter is intentionally **not part of this commit**. Adding a live
read-only event source requires Bumble review plus Randy's explicit credential
and access authorization. An adapter must map only these live helpers:

| Normalized field | Approved Newark source |
|---|---|
| `mode` | `input_select.home_context_mode` |
| `activity` | `input_select.home_current_activity` |
| `confidence` | `input_number.home_context_confidence`; parse its decimal string exactly, require an integral value, then convert to integer; never round |
| `active_rooms` | `sensor.home_active_room`; split its comma-separated multi-room state, trim, deduplicate, sort, and enforce the 12-room whitelist |
| summary context | `input_text.home_context_summary` (derive approved flags; do not store raw text) |
| next prediction | `input_text.home_next_likely_activity` (future aggregate only; not stored in v1) |
| feedback | Confirm / Mark Wrong / Unsure buttons and corrected-activity selector |
| outcome audit | confirmation / correction / unsure counters and last-feedback helper |

## Phase 3.3 snapshot contract

The top level is exactly `snapshot_at`, `observer_config`, and `entities`.
`observer_config` is exactly the reviewed Observer automation ID plus lowercase
SHA-256 `config_sha256` and `version`; its canonical object becomes the opaque
`observer_version` digest. Each entity is exactly `state` and `last_changed`.
Unknown entities, missing required entities, attributes, service/event fields,
transport configuration, and other extras are rejected.

The exact entity allowlist is:

```text
input_select.home_context_mode
input_select.home_current_activity
input_number.home_context_confidence
sensor.home_active_room
input_text.home_context_summary
input_text.home_next_likely_activity
input_boolean.ai_actions_enabled
sensor.home_context_observer_age
binary_sensor.home_context_engine_stalled
binary_sensor.residents_home
binary_sensor.home_room_presence
binary_sensor.tv_active
binary_sensor.music_playing
binary_sensor.exterior_door_open
binary_sensor.recent_arrival
input_button.home_context_confirm
input_button.home_context_mark_wrong
input_button.home_context_mark_unsure
input_select.home_context_corrected_activity
counter.home_context_confirmations
counter.home_context_corrections
counter.home_context_unsure
```

The seven normalized signals are exterior door, music, Observer health, recent
arrival, resident presence, room presence, and TV. Binary entity states become
`active`/`inactive`; `unknown`/`unavailable` become `missing`; an age greater
than the per-signal threshold becomes `stale` (the exact threshold remains
fresh). Observer stalled maps to missing evidence, and Observer age over ten
minutes maps to stale. Residents are emitted only as `none` or `unknown`—never
as an identity or person count guessed from a household-wide binary sensor.

Raw summary text is never emitted. It is reduced to a fixed set of approved
concept flags (`conflict`, `door`, `media`, `missing`, `recent arrival`, or
`stale`). Next activity is emitted only when it exactly matches the approved
activity vocabulary; otherwise it becomes null. The normalizer also refuses to
operate unless the supplied `ai_actions_enabled` state is OFF.

### Episode and feedback boundaries

A prediction episode changes only when semantic context changes: mode, activity,
five-point confidence band, active rooms, anonymous resident bucket, one of the
seven signal-health states, approved context flags, next activity, or Observer
version. A timestamp-only five-minute Observer refresh emits nothing. IDs are
deterministic SHA-256 digests with separate episode/prediction/feedback
namespaces, making replay stable without embedding household-readable values.

Button `last_changed` timestamps—not counters—are feedback-event cursors. The
first snapshot establishes a baseline. A later Confirm/Wrong/Unsure timestamp
emits feedback against the episode visible before that snapshot; a new timestamp
therefore preserves revisions. Counters only check that audit deltas exactly
match the newly observed button timestamps; jumps, resets, or unexplained
increments mark the audit inconsistent but never create feedback events.

### True append and crash behavior

`normalize-snapshot` accepts a local snapshot file and uses `O_APPEND`; it
refuses `atomic-replace`, symlinks/special files, an incomplete existing final
line, or using the same file for normalizer state and JSONL output. Output is
fsynced before the separate normalizer state advances. A crash after append but
before state advance may replay an identical line, which the downstream
event-ID idempotency safely deduplicates. The persistent collector processes
only complete newline-terminated lines and does not replace the output file.

Distinct quarantine rows are capped at 1,000 by default. Old fingerprints are
pruned deterministically while cumulative pruned distinct and occurrence totals
remain in metadata and the report; raw rejected content is never retained.

## Normalized JSONL contract

Each episode is a `prediction` record. Feedback is a separate record linked by
anonymous `episode_id`. The synthetic fixture is the canonical example:
`mac_mini/fixtures/synthetic_events.jsonl`.

Every approved signal must appear in every prediction and be explicitly marked
`active`, `inactive`, `stale`, or `missing`; omission is rejected so an adapter
cannot silently turn unavailable evidence into absence. Non-response is not a
feedback record and remains explicitly unreviewed. A `wrong` record must provide
the corrected activity; `confirm` and `unsure` must not.

`input_number.home_context_confidence` is serialized by HA as a decimal string
such as `20.0`. The future adapter must call the tested exact parser: `20.0`
becomes integer `20`; `20.5` is rejected and is never rounded. The live
`sensor.home_active_room` is genuinely multi-room: for example,
`Family Room, Office, Kitchen, Foyer`. Split on commas and trim each room.
`None` maps to an empty list plus `inactive`; `unknown` and `unavailable` map to
an empty list plus `missing` and must never be treated as absence.

`source_event_id`, `episode_id`, and `observer_version` must be generated opaque
UUIDs or fixed 32/64-character lowercase hex digests. Entity IDs, person names,
room names, timestamps, and other readable household data are forbidden in
identifier values. Feedback is append-only audit history: a household member
may revise a label, and the report uses the latest event visible at `as_of`,
ordered by timestamp and then opaque event ID for deterministic ties. Exact
event replay is idempotent; changed content reusing an event ID is rejected.
The normalizer must emit each prediction before feedback that references it.

### Continuous-ingest contract

`ingest-continuous` is the only supported persistent path. It records a private
per-file byte checkpoint and processes only complete newline-terminated records.
Each accepted line and checkpoint commit together. An invalid line is reduced to
a SHA-256 fingerprint plus bounded error metadata—raw rejected content is not
stored—then ingestion advances to later lines. Identical rejected content is
deduplicated while its occurrence count increases. Both the command result and
aggregate report expose rejected occurrence and distinct-record counts.
Quarantine stores neither the raw line nor exception text derived from its
values—only the line fingerprint, error class, offsets, and counts.
Rejected counts are explicitly database-lifetime operational health, not
historical `as_of` classification metrics.

The strict `ingest` command remains available for offline fixtures and manual
one-shot imports; any invalid line rolls back that entire supplied batch.

## Local proof commands

From the repository root:

```bash
python3 -m unittest discover -s mac_mini/tests -v

pilot_dir="$(mktemp -d)"
python3 -m mac_mini.home_context_analytics.cli normalize-snapshot \
  --input mac_mini/fixtures/newark_snapshot_normal.json \
  --state-database "$pilot_dir/normalizer.sqlite3" \
  --output "$pilot_dir/normalized.jsonl"

python3 -m mac_mini.home_context_analytics.cli ingest-continuous \
  --input "$pilot_dir/normalized.jsonl" \
  --database "$pilot_dir/episodes.sqlite3" \
  --retention-days 45 \
  --drift-window-days 14 \
  --as-of 2026-08-12T18:00:00Z

python3 -m mac_mini.home_context_analytics.cli ingest \
  --input mac_mini/fixtures/synthetic_events.jsonl \
  --database "$pilot_dir/episodes.sqlite3" \
  --retention-days 45 \
  --as-of 2026-08-12T18:00:00Z

python3 -m mac_mini.home_context_analytics.cli report \
  --database "$pilot_dir/episodes.sqlite3" \
  --as-of 2026-08-12T18:00:00Z \
  --window-days 7 \
  --format markdown
```

The report includes the reviewed denominator, Confirm/Wrong/Unsure counts,
unreviewed volume, rejected-record counts, per-activity confusion, stale/missing
signal rate, and adjacent drift-ready windows. Each confidence bucket contains
mean predicted confidence, observed accuracy, and absolute calibration gap; the
report also computes reviewed-count-weighted overall ECE. `Unsure` is reviewed
but excluded from accuracy and calibration. Calibration values use the 0–1
scale, so the future 10-percentage-point gate is `ECE <= 0.10`.

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

Synthetic coverage builds variants from
`fixtures/newark_snapshot_normal.json` for multi-room, unknown/unavailable,
stale-at-boundary, Observer-stalled, revised feedback, meaningful transition,
unchanged refresh, and privacy/allowlist rejection cases. Fixtures contain no
real household state.

## Reviewed launch path (not deployed)

1. Review and commit this implementation; run the full package tests on the Mac
   mini checkout.
2. Obtain Randy's approval for a narrowly scoped, read-only HA event/export
   credential. Build and separately review the normalizer; it may emit only the
   documented JSONL fields and may not expose any service-call method.
3. Choose private local paths outside synced folders, create them mode `0700`,
   and validate a manual one-shot ingest plus report first. Configure retention
   greater than twice the report drift window (the 45/14-day defaults comply).
4. Copy `launchd/xyz.buzz.home-context-analytics.plist.example` to
   `~/Library/LaunchAgents/xyz.buzz.home-context-analytics.plist`, replace every
   placeholder with an explicit local path, run `plutil -lint`, and only then
   bootstrap it with `launchctl bootstrap gui/$(id -u) ...`.
5. Verify that stopping the job changes no HA helper, observer, automation, or
   device state. Verify the generated report against the counters shown in the
   Home Context dashboard.

The launch template invokes `ingest-continuous`, not atomic one-shot ingestion.
Its JSON stdout is an operator-visible run summary, stderr records command-level
failure, and the report exposes deduplicated rejected-record counts. A partial
final line waits for the next run. Rotation/truncation resets that source path's
checkpoint safely; event-level idempotency still prevents duplicate data.

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
