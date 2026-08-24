---
title: "Home Context Signal Diagnostics Browser Gate 2026-08-23"
tags: [home-context, newark, home-assistant, diagnostics, rollback]
status: active
created: 2026-08-23
---

# Home Context Signal Diagnostics Browser Gate

The signed-in Newark Studio Code Server page was available in Safari at the
Home Assistant LAN ingress path with `/config/configuration.yaml` open.

Before mutation, a byte-identical file copy was created at:

`/config/configuration.yaml.bak-home-context-signal-20260823T2310EDT`

Both the live file and copy had SHA-256:

`48a2b3bdfb8858f338ebb82307c3565ee8f5b1a24c92f3c8dd17a34d70fab316`

The first attempt to insert the reviewed diagnostics REST sensor through the
browser editor was transformed by code-server auto-indentation and immediately
showed YAML errors. No configuration check, reload, restart, dashboard write, or
device action was attempted from that malformed state.

The live file was restored immediately from the verified copy. The restored
file again had SHA-256
`48a2b3bdfb8858f338ebb82307c3565ee8f5b1a24c92f3c8dd17a34d70fab316`,
and the original `rest:` section was visible in the editor.

A second approach through the code-server terminal was stopped before command
submission because the HTTP insecure-context session transformed long terminal
input instead of preserving it verbatim. The terminal panel was hidden with no
pending command submitted.

## Remaining gate

Resume through a secure authenticated browser context, preferably the Newark
Nabu Casa HTTPS Studio Code ingress page, or expose a managed YAML write and
configuration-check surface. Reconfirm the live file hash above before staging.
Only the reviewed diagnostics REST sensor should change; the existing
`rest_command.home_context_post_snapshot` fragment should remain untouched if
its retained hash still matches. Stop again before Home Assistant restart and
before the `home-command/context` dashboard transaction.

AI Actions remained OFF. Observer behavior, BriefDash `8443`, Home Context
`9443`, automations, dashboard state, and device state were not changed.

## Secure Chrome staging — 2026-08-23 23:40 EDT

Randy opened the Newark Terminal App through the Nabu Casa HTTPS ingress in
Chrome. The secure terminal resolved the prior evidence discrepancy: both the
live file and the rollback copy were byte-identical at the canonical pre-edit
SHA-256
`482ab3dbfb8858f338ebb82307c3565ee8f5b1a24c92f3c8dd17a34d70fab316`.
The earlier `48a2...` value in this log was a transcription error.

The guarded edit required that exact live/backup hash, byte equality, one exact
REST insertion anchor, one exact snapshot-source insertion anchor, and absence
of both new identifiers. It inserted only:

- the reviewed HTTPS REST sensor `home_context_signal_diagnostics`; and
- the reviewed `garage-diagnostics-v1` bounded source lane inside the existing
  `rest_command.home_context_post_snapshot` payload.

The file grew from 55,414 to 58,406 bytes. The two reviewed insertions account
for the complete 2,992-byte delta (622-byte REST sensor plus 2,370-byte source
lane). Post-edit SHA-256 is
`5ec6e3cad519fcf91ca1e7284db48a7e9d9edb7fc4512b43821e0ed6d3e3e416`.

`ha core check` completed with exact result `Command completed successfully.`
Same-endpoint managed YAML readback found exactly one diagnostics REST sensor,
one `garage-diagnostics-v1` lane, and one preserved `fp300-context-v1` lane.
The existing HTTPS snapshot URL and `!secret home_context_receiver_secret`
reference are preserved. Live helper readback still matches config entry
`01KZHASWE6S7W7NE177MHX89AF`, occupancy device class, and the reviewed three
canonical source entities.

Runtime remains intentionally unchanged until a separately approved restart:
the diagnostics sensor is not loaded, AI Actions is OFF, Observer is ON in
`restart` mode at config hash `6b5fa7a109f6636a`, and Snapshot Push is ON in
`queued` mode at config hash `48e5798fbb9f358e`. No restart, dashboard write,
automation write, device command, Mac runtime reload, or port change occurred.

Rollback remains the byte-identical file
`/config/configuration.yaml.bak-home-context-signal-20260823T2310EDT`; the
broader completed HA backup is `68e784a3`. The next gates are the separately
approved Newark restart, live entity/endpoint proof, then the separately staged
dashboard transaction and desktop/mobile visual QA.

## Controlled restart, failed proof, and rollback — 2026-08-23 23:45–23:56 EDT

Randy explicitly approved one controlled Newark Home Assistant restart with
the previously stated rollback-on-failed-proof path. The validated staged
configuration started successfully on Home Assistant `2026.8.3`, but live
proof failed: `sensor.home_context_signal_diagnostics` registered with an
empty state and no bounded report attributes, while Snapshot Push received
HTTP `422 invalid_snapshot` from the private receiver. AI Actions remained
OFF, Observer remained ON in `restart` mode at config hash
`6b5fa7a109f6636a`, Snapshot Push remained ON in `queued` mode at config hash
`48e5798fbb9f358e`, and `light.smart_switch_kitchen` still resolved to
`Kitchen Cans`.

The pre-authorized rollback was executed through the secure Terminal App. A
guard required the staged live SHA-256
`5ec6e3cad519fcf91ca1e7284db48a7e9d9edb7fc4512b43821e0ed6d3e3e416`, the
rollback SHA-256
`482ab3dbfb8858f338ebb82307c3565ee8f5b1a24c92f3c8dd17a34d70fab316`, and
non-equality before copying the rollback file over `configuration.yaml`.
`ha core check` had to succeed before the rollback restart could run. Newark
recovered RUNNING on `2026.8.3`; AI Actions is OFF, Observer and Snapshot Push
are ON with current `0`, and the removed diagnostics entity is now an expected
unavailable registry remnant rather than a loaded REST sensor.

The rollback exposed an independent pre-existing receiver/runtime blocker:
Snapshot Push still received HTTP `422` after the original configuration was
restored, with two occurrences at the post-rollback startup trigger. The exact
rejected rollback snapshot was accepted by the local validator at the reviewed
worktree HEAD, which points to the live Mac mini receiver process/runtime not
matching that accepted validator behavior (or an equivalent runtime-local
gate). No rejected payload was retained after this check. Resolving that layer
requires a separately authorized controlled Mac mini receiver reload and live
endpoint proof before reattempting the HA diagnostics lane.

No dashboard write, automation write, device command, AI Actions change,
BriefDash port change, Home Context port change, or Mac runtime reload occurred.

## Receiver reload, accepted canary, and successful restage — 2026-08-24 08:01–08:17 EDT

Randy explicitly authorized one controlled Mac mini Home Context receiver
reload, authenticated endpoint proof, a legacy Newark Snapshot Push canary,
and—only after those checks passed—the reviewed diagnostics restage and Newark
restart.

Mac mini preflight found the receiver running as PID `67136` since
2026-08-23 11:33 EDT while the clean deployed checkout was diagnostics commit
`87a85d0a81fc64a9e8ae631f2c2507f30cdc8941`. The process therefore predated the
deployed diagnostics runtime. Before reload, launchd, loopback-only
`127.0.0.1:8765`, Home Context HTTPS `9443`, BriefDash HTTPS `8443`, empty
receiver logs, and owner-only `0600` artifacts all read back intact.

One `launchctl kickstart -k` replaced the stale process with PID `8332`.
Launchd reports state `running`, run count `2`, and prior exit code `0`; `lsof`
still shows only `127.0.0.1:8765`. The Tailnet endpoint returned the expected
unauthenticated fixed-value HTTP `401`. Direct SSH Keychain access stopped with
exit `36`, so no credential was copied or exposed. The intended credential
holder—Newark's existing `!secret` REST command—provided the authenticated
proof and legacy canary. Snapshot Push completed its coherence gate and invoked
the REST command; the receiver recorded accepted timestamps
`2026-08-24T12:05:00.507475Z` and `2026-08-24T12:05:17.628901Z`, with no HTTP
`422`, stderr, or new normalized transition because household context was
unchanged.

Only after that proof passed, the previously reviewed guarded staging command
was replayed against the byte-identical original/rollback SHA-256
`482ab3dbfb8858f338ebb82307c3565ee8f5b1a24c92f3c8dd17a34d70fab316`.
The staged file again measured 58,406 bytes at SHA-256
`5ec6e3cad519fcf91ca1e7284db48a7e9d9edb7fc4512b43821e0ed6d3e3e416`, and
`ha core check` completed successfully. Randy's authorization covered the
follow-on restart; Newark returned RUNNING on Home Assistant `2026.8.3`.

Post-restart managed file readback found exactly one
`home_context_signal_diagnostics` REST sensor, one `garage-diagnostics-v1`
lane, one preserved `fp300-context-v1` lane, and two unchanged masked secret
references. Snapshot Push traces finished successfully and the receiver
recorded accepted snapshots at `2026-08-24T12:16:34.023525Z` and
`2026-08-24T12:16:34.299260Z`.

Live `sensor.home_context_signal_diagnostics` is `Healthy` on schema `5`, with
`generated_at` `2026-08-24T12:16:34.299260Z`, `fresh_until`
`2026-08-24T12:26:34.299260Z`, issue count `0`, AI Actions `OFF`, device
controls unavailable, local-only processing, `network_used: false`, and no raw
transition history. Observer is ON / `restart` / current `0`; Snapshot Push is
ON / `queued` / current `0`; `light.smart_switch_kitchen` still resolves to
Kitchen Cans and was live-read as ON after restart. No device command was sent.
Receiver stderr remains empty, PID `8332` remains loopback-only, and the
`8443`/`9443` Serve mappings remain unchanged.

Rollback remains the exact original file
`/config/configuration.yaml.bak-home-context-signal-20260823T2310EDT`. No
dashboard write, automation configuration write, device command, AI Actions
change, secret change, DNS change, or Serve port change occurred.

## Dashboard transaction and desktop/mobile QA — 2026-08-24 08:31–08:35 EDT

Randy explicitly authorized the `home-command/context` dashboard transaction
and desktop/mobile QA. Newark preflight resolved `light.smart_switch_kitchen`
to Kitchen Cans, read `sensor.home_context_signal_diagnostics` as `Healthy` on
schema `5` with issue count `0`, and confirmed AI Actions `off`.

The fresh storage-dashboard read returned view `context` at index `8` with
pre-change config hash `a8c52a5587a802b3`. The exact scoped view was captured
before the write at
`.scratch/HOME_CONTEXT_DASHBOARD_BACKUP_20260824T0831EDT.json`, SHA-256
`bbed12028a2b49db206434cdcd370a8b0f77b66bc76647abaa985585f6a2d120`.
Rollback is one hash-guarded replacement of only `config["views"][8]` from that
artifact; no Home Assistant restart or full backup restore is required.

One optimistic-locking `python_transform` extended the existing
`#hc-signals` popup rather than adding a new dashboard section. It inserted one
`Signal diagnostics` heading and one read-only markdown panel using the
reviewed sanitized issue-card contract. The panel renders fail-closed
`Diagnostics unavailable`, the full issue lifecycle and bounded proposal when
an issue exists, or `Healthy` with report generation time when no contradiction
is reported. It states AI Actions OFF and exposes no repair or device-control
action.

Fresh managed readback returned post-change hash `090d5c97d83d106d`, exactly
one diagnostics panel, and the Signals popup card count `7 -> 9`; the inserted
heading and panel are the first two popup cards. No other view was replaced.

Signed-in Newark Chrome rendered the live popup successfully. Desktop QA at
1920x902 showed the full Healthy panel above the existing Signals content with
no horizontal overflow (`scrollWidth == clientWidth == 1920`). Mobile QA used
the responsive viewport override and rendered the same status, explanation,
timestamp, and AI Actions OFF line above the existing two-column cards with no
horizontal overflow (`scrollWidth == clientWidth == 433`). The temporary
viewport override was reset. Existing unrelated HACS/ingress console errors
were present; none prevented the Home Context view or diagnostics panel from
rendering.

Final live readback kept the dashboard hash `090d5c97d83d106d` and showed:

- diagnostics `Healthy`, schema `5`, issue count `0`, `network_used: false`;
- AI Actions `off`;
- Observer `on` / `restart` / current `0`, config hash
  `6b5fa7a109f6636a`;
- Snapshot Push `on` / `queued` / current `0`, config hash
  `48e5798fbb9f358e`;
- Kitchen Cans still resolved at `light.smart_switch_kitchen`; no command was
  sent.

No restart, automation write, helper write, device command, Mac receiver
reload, AI Actions change, secret change, DNS change, or Serve change occurred.

## Persistent feedback receipt — 2026-08-24 08:41–08:49 EDT

Randy pressed **Confirm current context** at `08:41:08 EDT`. Live Newark
readback proved the event was recorded: `counter.home_context_confirmations`
advanced to `32`, `input_text.home_context_last_feedback` became
`CONFIRMED 08/24 08:41: Active/Working 88.0% · Office`, and Snapshot Push
triggered in the same second before returning to `on` / `queued` / current
`0`. Diagnostics remained `Healthy` on schema `5` with issue count `0`, and
AI Actions remained `off`.

To make that success visible without opening the correction popup, a fresh
hash-guarded dashboard transaction added one read-only native tile directly
beneath Confirm / Wrong / Unsure. The tile is named `Last recorded feedback`
and renders the authoritative feedback helper state plus its age. It exposes
only Home Assistant's read-only more-info view; it has no service action,
device control, or repair control.

The transaction changed the full dashboard hash from
`090d5c97d83d106d` to `4326404e8bf42f92`. Fresh readback found exactly one
tile with that name at rating-section card index `4`, between `Unsure` and the
`Explore` heading. The exact pre-change scoped view is preserved at
`.scratch/HOME_CONTEXT_FEEDBACK_VISUAL_BACKUP_20260824T0842EDT.json`,
SHA-256
`f96824a5af92a9452e0a89f08d5f52f17128c27520a0f7445bb158f07a50a91f`.
Rollback is one fresh-hash-guarded replacement of only
`config["views"][8]` from that artifact; no HA restart is needed.

Signed-in Chrome QA rendered the live receipt on desktop at `1920x902` with
no horizontal overflow (`scrollWidth == clientWidth == 1920`). A responsive
mobile override rendered the same receipt and complete Confirm string with no
horizontal overflow (`scrollWidth == clientWidth == 481`); the override was
reset. The live Home Context tab was left open on the receipt for owner
inspection.

No automation/helper configuration write, device command, HA restart, Mac
reload, AI Actions change, secret/DNS/Serve change, or unrelated dashboard
replacement occurred. Two earlier restricted-transform validation attempts
failed before mutation; the dashboard hash remained unchanged until the single
successful scoped insertion.
