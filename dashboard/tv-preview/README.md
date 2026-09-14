# Watching TV rehearsal

Isolated browser prototype, not a Lovelace card or deployed HA automation.
Uses synthetic signals only. Approval is in-memory UI rehearsal, never scored
feedback or authorization for device control. There is no network or service
client; the page CSP also rejects outbound connections.

Run from the repository root:

```sh
node --test dashboard/tv-preview/model.test.mjs
python3 -m http.server 8876 --bind 127.0.0.1 --directory dashboard/tv-preview
```

Open http://127.0.0.1:8876. The scenario selector invalidates the current
proposal. It cannot revive a cancelled proposal; New demo session explicitly
starts another synthetic rehearsal. Approval expires after two minutes.
Reloading never restores an approval. The model intentionally has no executor
or Undo: there is no real state change to undo.

Metrics are a dated September 10 aggregate snapshot, not live telemetry.
The 11% target is user-selected; preserving warmth and leaving an off lamp off
are conservative proposed defaults. Do not treat passing these synthetic
tests as validation of live source freshness, persistent session identity,
cross-client deduplication, manual override or device-side circuit breakers.

Live deployment is a separate gate: reconcile all loaded consumers, resolve
calibration readiness, implement authoritative server-side approval/session
handling, verify source freshness, back up the dashboard, perform a narrow
fresh-hash update and obtain explicit permission for any real lighting test.
