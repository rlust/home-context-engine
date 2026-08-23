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

Phase 3.4 adds the selected **HA-originated push receiver**. It is a stdlib-only
HTTP server that binds explicitly to `127.0.0.1`, accepts one authenticated POST
path, and passes only a complete validated snapshot to the same normalizer. In
the future production shape, tailnet-only HTTPS terminates at Tailscale Serve
and Serve proxies to this loopback listener. The receiver never stores an HA
URL, HA token, MCP path, or capability to call Home Assistant or a device.

The transport architecture is selected and implemented only as non-live code:
HA-originated POST over tailnet-only HTTPS to Tailscale Serve, then loopback
proxying to this receiver. Credential generation, HA configuration, Tailscale
Serve configuration, LaunchAgent installation, and any live connection remain
separate owner-authorized gates.

## Safety boundary

- Home Assistant remains the real-time observer and controller.
- `input_boolean.ai_actions_enabled` remains OFF. The normalizer verifies the
  supplied whitelisted state is OFF; the package cannot query or change it.
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
- The receiver refuses `0.0.0.0`, LAN addresses, hostnames, IPv6, and any bind
  other than explicit IPv4 loopback `127.0.0.1`. Tailscale Serve is the only
  proposed TLS ingress; Funnel is forbidden.

## Phase 3.4 receiver contract (built, not deployed)

The only accepted route is `POST /v1/home-context/snapshot`. Every other path
returns 404 and every other method returns 405. Requests require:

- `Content-Type: application/json`;
- an exact `Content-Length` from 1 through 65,536 bytes;
- `X-Home-Context-Secret`, compared in constant time against a high-entropy
  secret of at least 32 bytes injected through the receiver process environment;
- a complete snapshot whose `snapshot_at` is within 10 minutes of receiver time;
- the existing exact 22-entity snapshot and per-entity field allowlists, with an
  optional reviewed `fp300-context-v1` source lane.

The owner must later generate the dedicated secret with a cryptographically
secure random generator. The same value belongs only in Mac Keychain/injected
process environment and HA `secrets.yaml`; it must never appear in a command
argument, plist, repository file, chat, or log. Empty and shorter-than-32-byte
values fail before the receiver binds. The secret is never written to the replay
database, JSONL, normalizer state, or logs, and responses never echo request
values. Read timeout is five seconds.
Only one normalization transaction can run at a time; concurrent work receives
503 backpressure. Exact-body SHA-256 replay protection returns a safe duplicate
response after snapshot validation and skew enforcement. Fingerprints older
than twice the skew window are pruned because they cannot accompany a valid
request. Normalizer no-transition returns a separate duplicate/no-transition
response. A created record returns 202 accepted, including only counts/booleans;
an accepted feedback audit failure sets `audit_visible: true`. Authentication,
shape, timestamp, method, path, media-type, size, timeout, and backpressure
failures use fixed reason codes without private data.

The review-only HA draft is
`home_assistant/home_context_snapshot_push.yaml.example`. It renders exactly the
22 approved entities with only `state`/`last_changed`/`last_reported`, uses
`verify_ssl: true`, a five-second timeout, `!secret` for the dedicated receiver
header, and `continue_on_error`. It triggers after the reviewed Observer or a
feedback button event and contains no device action.

Observer-trigger coherence is fail closed. The draft records the
`automation_triggered` event time and context ID, then waits at most ten seconds
for all five Observer-written prediction helpers—mode, activity, confidence,
summary, and next activity—to have `last_reported` at or after that event time
and for the Observer automation's `current` attribute to be present and zero.
Only then may the common POST action run. Timeout writes a fixed warning and
stops with an error before POST. The coherence invariant is exact: the reviewed
Observer remains the sole writer of all five helpers, every helper reports after
the captured Observer event, and the Observer run has completed. Together those
facts prove one complete run even when every value stays unchanged. HA may
preserve older, mixed state contexts while advancing `last_reported`, so helper
context equality is deliberately not required. The captured event context is
retained only for diagnostic trace review and never gates export.

The non-overlap precondition is mandatory. The reviewed live Observer config
hash `6b5fa7a109f6636a` uses `mode: restart`, which prevents parallel instances;
`single` is also acceptable. The Observer must remain the sole writer of all
five helpers and remain in a non-parallel `single`/`restart` mode. Changing it
to `parallel` or any equivalent overlapping execution invalidates the coherence
proof and requires review before export resumes. The YAML draft and
`home_context_analytics/ha_export_contract.py` carry cross-references and a
structural regression to keep their shared gate synchronized.

Feedback-trigger exports wait one second for picker/counter settlement, then
require the Observer automation's `current` attribute to be present and zero.
If an Observer run is active or completion cannot be proved within ten seconds,
the draft warns and stops without POST. Thus feedback can export the already
complete current prediction plus its new press, but cannot knowingly sample a
prediction mid-write.

Installing `rest_command`
requires configuration validation, a fresh backup, explicit owner approval,
and an HA restart; this repository does none of those things.

The review-only receiver LaunchAgent is
`launchd/xyz.buzz.home-context-receiver.plist.example`. Its first program
argument is deliberately an owner-reviewed secret-injection wrapper placeholder;
the secret must not be pasted into the plist. The review-only Tailscale commands
are in `tailscale/serve.commands.example`. They first capture the full existing
Serve configuration, add only dedicated HTTPS port 9443 after conflict review,
read it back, and remove only that port on rollback. Bare whole-device `serve
reset`/`serve off` and Funnel are forbidden.

HTTPS port `8443` is reserved by the existing BriefDash mapping to its loopback
service and must not be changed, removed, or reused by this package. Home
Context uses only Tailscale Serve HTTPS `9443` to receiver loopback
`127.0.0.1:8765`.

### Receiver responses

| HTTP | Status | Meaning |
|---:|---|---|
| 202 | `accepted` | One or more normalized records were appended and fsynced |
| 200 | `duplicate` | Exact replay or valid snapshot with no semantic transition |
| 4xx | `rejected` | Fixed authentication/request/snapshot rejection; no values echoed |
| 408/503 | `unavailable` | Read timeout or local single-writer backpressure |
| 500 | `unavailable` | Fixed internal-error fallback; no exception or values logged/echoed |

### Shutdown and crash runbook

SIGTERM and Ctrl-C stop the HTTP loop and close the listener. Handler threads
are non-daemon and `server_close()` waits for them; the five-second per-request
timeout bounds that wait. Only after all handlers exit does the process close
the replay database, preventing a connection-close race. Stop the receiver
before the collector during planned maintenance; HA remains unaffected because
its draft action is `continue_on_error`.

There remains a narrow accepted Phase 3.3 crash window: JSONL is fsynced before
normalizer state is saved. An identical retry is harmless because opaque event
IDs deduplicate downstream. If the first retry is instead a different later
snapshot, the stale pre-crash state can derive a different transition boundary
or associate a press to the wrong adjacent episode. Do not delete data. Preserve
the JSONL/state files and review the adjacent events before accepting their
labels; this rare case is an audit/manual-review condition.

A true partial final JSONL write intentionally halts future appends. Safe repair
is manual and local: stop receiver and collector; make a permission-preserving
backup; confirm the file does not end in a newline; inspect only the final local
fragment; remove exactly that incomplete fragment in a local editor; restore one
final newline; validate every remaining line as JSON; then restart and review
the collector replay/duplicate counts. Do not use an automatic truncate command,
do not print the private file into chat/logs, and do not delete the backup until
the repaired stream and report are verified.

The HA emitter is a credential-free review draft only. Making it live requires
Bumble review plus Randy's explicit credential, restart, and access approval.
It may map only these live helpers:

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

The legacy top level remains exactly `snapshot_at`, `observer_config`, and
`entities`. A backward-compatible enriched snapshot may add `source_context`
containing only `fp300-context-v1`. That source requires the exact 37
state-backed Family Room FP300 entities and the same three per-entity fields.
Evidence, source-health, and audit-only roles are assigned locally; the source
cannot carry service calls or command instructions. Target distance is fresh for
two minutes, other readings for fifteen minutes, and unavailable values are
explicitly marked missing. The two registry-only RSSI/LQI entries are not accepted
until Home Assistant exposes stable state records for them.
`observer_config` is exactly the reviewed Observer automation ID plus lowercase
SHA-256 `config_sha256` and `version`; its canonical object becomes the opaque
`observer_version` digest. Each entity is exactly `state`, `last_changed`, and
`last_reported`. The latter two are source timestamps, not blanket health
heartbeats.

The Newark deployment pins live Observer config hash `6b5fa7a109f6636a`.
`config_sha256` is SHA-256 of that reviewed hash string, and `version` is
SHA-256 of `home-context-export-v1:` plus that hash. Any Observer config change
invalidates both reviewed digests and requires a new read-only review before
the export automation continues.
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
`active`/`inactive`, and `unknown`/`unavailable` become `missing`. A stable OFF
aggregate remains `inactive` even when `last_changed` and `last_reported` are
old; neither timestamp proves that its upstream source is healthy. The one
documented transient is positive `recent_arrival`: ON evidence becomes `stale`
only after its `last_reported` is more than 15 minutes old (exactly 15 minutes
remains active). Other stable ON/OFF aggregates retain their current state.
Observer health is governed separately: stalled ON/unknown/unavailable maps to
missing, and Observer age over ten minutes maps to stale. True negative-source
outage detection requires future source-specific availability/heartbeat inputs;
this snapshot contract does not pretend aggregate timestamps provide it.
Residents are emitted only as `none` or `unknown`—never as an identity or person
count guessed from a household-wide binary sensor.

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

Input-button `state` is the feedback press cursor. `last_changed` may advance
during HA reload/recreation and is never treated as a press; changing it alone
emits nothing. A button state of `unknown` or `unavailable` means no known press
cursor and emits nothing. The first snapshot establishes a nullable baseline.
Later valid button-state timestamps preserve revisions. Once a valid cursor is
known, a temporary regression to unknown/unavailable does not erase it, so the
same timestamp returning after recovery cannot replay a label. Counters only
check that audit deltas match newly observed presses and never create feedback
events.

For a semantic transition, the normalizer computes the transition time from
the `last_changed` timestamp of the source field(s) that changed the transition
key (or the documented transient expiry time). If a transition and press first
appear in one snapshot, a press at or after that time labels the new episode; a
press before it labels the prior episode.

Wrong feedback also audits the corrected-activity picker. Its `last_changed`
must be newer than the previous snapshot and no later than the button-state
press time. A stale or later picker value is retained for audit visibility but
the feedback is marked inconsistent and excluded from accuracy, confusion, and
calibration. The report exposes inconsistent counts and approved issue codes.
Known dashboard limitation: selecting the option already retained in the picker
may not advance `last_changed`; until the dashboard supplies a separate
selection timestamp, that press is deliberately flagged
`corrected_activity_stale` rather than silently trusted.

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
anonymous `episode_id` and carries `audit_consistent` plus an approved
`audit_issues` list. The synthetic fixture is the canonical example:
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
audit-consistent scoring denominator, audit-failure counts, unreviewed volume,
rejected-record counts, per-activity confusion, stale/missing signal rate, and
adjacent drift-ready windows. Each confidence bucket contains
mean predicted confidence, observed accuracy, and absolute calibration gap; the
report also computes reviewed-count-weighted overall ECE. `Unsure` is reviewed
but excluded from accuracy and calibration, as is audit-inconsistent feedback.
Calibration values use the 0–1
scale, so the future 10-percentage-point gate is `ECE <= 0.10`.

## Pilot success and Phase 4 boundary

The implementation pilot succeeds when the same synthetic input always yields
the same report, invalid/private input is rejected atomically, network access is
absent, reporting cannot mutate SQLite, retention works, and a Mac mini manual
run reproduces the package tests. Those are software-safety criteria, **not**
evidence that the household classifier is accurate.

## Signal diagnostics and helper-repair transaction

`home_context_analytics.diagnostics` adds a schema-5, local-only diagnostic
artifact for derived Home Context helpers. Its input contract contains only the
affected helper, bounded binary-signal metadata, same-device identity, and a
short transition window. Report output retains summarized evidence but omits
raw transition history and sensitive household fields.

The detector proposes a replacement only when one candidate is on the same
device, has compatible motion/occupancy semantics, is fresh, and has completed
at least two on-to-off cycles. Name-only, stale, single-cycle, or multiple
candidate matches do not produce a repair. The canonical Garage incident is
replayed offline from `fixtures/garage_signal_replay.json`; production must not
be deliberately broken to test the detector.

Required-source age is fail-closed only when that source has an explicit
positive `max_age_seconds`; stable OFF binary inputs otherwise remain valid.
Replacement candidates always use the stricter fresh-update window.

`home_context_analytics.repair.execute_helper_repair` is dry-run by default. A
write requires the exact issue ID plus a durable owner-approval reference, AI
Actions OFF, fresh matching evidence, a fetch-before-write helper definition,
and a fresh config hash. The client protocol exposes only helper fetch/update
operations. Successful readback preserves the config entry, entity ID, name,
device class, unrelated inputs, and consumers; failure triggers restoration of
the exact fetched definition. A successful configuration write remains
`Verifying` until the physical Garage PIR ON-to-clear canary is observed.

`append_repair_audit` appends value-bounded transaction events to an owner-only
`0600` JSONL file. It does not persist helper templates. The offline dashboard
design at `dashboard/home_context_signal_issues_preview.json` is a complete,
full-width sections view for mobile and desktop. Its Markdown fallback is
intentional because the card must render a variable-length evidence narrative
and lifecycle without adding an unapproved custom template. It exposes the
detection/proposal/approval/verification/resolution/rollback lifecycle and
contains no HA service action.

The report marks a drift comparison ready only when both adjacent windows have
at least 20 reviewed episodes. Any later Phase 4 proposal still needs the agreed
human evidence gate: at least 50 reviewed episodes overall, at least 20 for the
exact target activity, target-branch precision of at least 90%, confidence
calibration error within 10 percentage points, zero eligibility when required
signals are stale/missing, and a separately demonstrated circuit breaker and
manual override. This package cannot enable or perform an action.

Synthetic coverage builds variants from
`fixtures/newark_snapshot_normal.json` for multi-room, unknown/unavailable,
long-stable OFF, transient stale-at-boundary, Observer-stalled, revised
feedback, reload-only button timestamp changes, both same-window
transition/press orderings, stale corrected picker, meaningful transition,
unchanged refresh, and privacy/allowlist rejection cases. Fixtures contain no
real household state.

## Reviewed launch path (not deployed)

1. Review and commit this implementation; run the full package tests on the Mac
   mini checkout.
2. Obtain Randy's approval to generate a dedicated high-entropy receiver secret
   of at least 32 bytes. Store it only in Mac Keychain/process injection and HA
   `secrets.yaml`; never put it in a command argument, plist, repo, or log.
3. Choose private local paths outside synced folders, create them mode `0700`,
   and validate a manual one-shot ingest plus report first. Configure retention
   greater than twice the report drift window (the 45/14-day defaults comply).
4. Capture `tailscale serve status --json`, confirm existing BriefDash HTTPS
   port 8443 is untouched, review port 9443 for conflicts, add only the dedicated
   9443-to-127.0.0.1:8765 mapping, read it back, and prove Funnel is off. Never
   use whole-device Serve reset/off commands.
5. Copy `launchd/xyz.buzz.home-context-analytics.plist.example` and the receiver
   template to `~/Library/LaunchAgents/`, replace every placeholder with an
   explicit local path, run `plutil -lint`, and only then bootstrap them after
   owner approval. The receiver plist must invoke an owner-reviewed wrapper that
   injects the Keychain secret through the environment; it must not contain it.
   Both templates set launchd `Umask` to decimal `63` (`077`) so newly created
   databases, reports, and stdout/stderr logs are owner-only. Verify every
   household-derived runtime artifact reads back as mode `0600`.
6. Validate HA configuration, take a fresh backup, and obtain explicit approval
   for the restart required to install the draft `rest_command` and automation.
7. Verify that stopping the job changes no HA helper, observer, automation, or
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

If the later receiver path is installed, disable the HA snapshot automation
first, boot out only the receiver and collector LaunchAgents, then remove only
the dedicated mapping with `tailscale serve --https=9443 off`. Capture
`tailscale serve status --json` afterward and compare it to the saved pre-change
configuration to prove unrelated mappings remain. Do not use `tailscale serve
reset` or bare `tailscale serve off`. The inert HA `rest_command` can remain
until an owner-approved maintenance restart removes it.
