# Home Context Controls — Working Log

Sanitized export of the project's running log. Internal IPs, the Apple ID, and
device/account identifiers have been replaced with placeholders.

## Verified deployment status — 2026-08-24

- The private Mac mini receiver is running the diagnostics return path from
  commit `87a85d0`, bound only to loopback behind the existing private HTTPS
  route. BriefDash remains on its separate existing route.
- Newark Home Assistant is running with
  `sensor.home_context_signal_diagnostics` Healthy on schema 5, zero issues,
  local-only processing, and AI Actions OFF.
- The live `home-command/context` view contains a read-only signal diagnostics
  panel plus a persistent `Last recorded feedback` receipt directly beneath
  Confirm / Wrong / Unsure. Desktop and responsive-mobile QA passed.
- The latest Confirm was recorded as Active / Working at 88% in Office;
  confirmations total 32. The private aggregate review remains below the
  Phase 4 advancement gates, so device-capable actions remain locked.
- Full credential-free rollout evidence, hashes, rollback instructions, and
  the current advancement decision are versioned under
  `docs/operations/`.

## Current system

- **Context helpers:** `home_context_mode`, `home_current_activity`, `home_context_confidence`, `home_context_summary`, `home_next_likely_activity`, `home_context_guest_mode`, `sleep_no_lights`; `ai_context_enabled` (ON), `ai_actions_enabled` (**OFF — safety lock**).
- **Presence:** `sensor.residents_present`; `person.randy` (carried iPhone), `person.kim` (carried iPhone Pro Max via iCloud3), `person.alex`.
- **12 room-occupancy helpers** + `binary_sensor.home_room_presence` + `sensor.home_active_room`.
- **Signals:** `residents_home`, `tv_active` (LG TV only), `music_playing` (music AND TV off), `night_time`, `exterior_door_open`, `recent_arrival`.
- **Observer:** `automation.home_context_evening_observer` — startup, every 5 min, or on any room/signal/door change. Writes only Home Context helpers; never controls devices.
- **Branch order:** Sleeping → Entertaining → Away → Working → Cooking → Watching TV → Listening to Music → Waking → Active → Unknown.

## Work log (most recent first)

### Presence fix (Kim) + iCloud3
- iCloud3 (Apple Find My integration) had failed auth ("Apple Login Failed, trust token expired"); re-authenticated (Apple ID + 2FA).
- `person.kim` had been tracking devices *left at home* (an old iPhone + a watch). Repointed it to her **carried** iPhone Pro Max (iCloud3 tracker) only. Verified she now reads her real location; `residents_present` updates correctly.
- Tradeoff: single-tracker person — accurate for a carried phone, shows away if that phone is off.
- Duplicate-tracker "cleanup": investigated — the stale ones were already gone; the rest are live integration entities (Companion app / iCloud / UniFi) that must be removed at the source, and one (`iot2`) is in use on `person.randy`. Nothing force-deleted. Flag: two Apple integrations (core `icloud` + iCloud3) run in parallel — consider consolidating.

### Sensor audit + door / arrival integration
- Audited all working sensors. Doors were the big untapped category and are now integrated (front, garage-entry, deck + 2 garage covers).
- Built `binary_sensor.exterior_door_open`; observer re-classifies within seconds of a door/garage event; arrival layer (`home_last_entry` → `recent_arrival`) suppresses premature Away for 8 min after an entry-door event.
- Dead ends: no kitchen appliance power (Cooking stays inference), no dining sensor, no house door lock.

### Dashboard
- Full professional redesign — hero status card + 7 logical sections (Home Context · Controls & Safety · Engine Health · Who's Home · Suggestions · Room Presence · Context Signals · Last 24 Hours). Observe-only. Engine-health/stall monitoring added.
- Added a fail-closed signal-diagnostics panel and a persistent visual receipt
  for Confirm / Wrong / Unsure feedback. Both surfaces are read-only and expose
  no repair or device-control action.

### Phase 4 audit + integration
- Suggestion layer (3 automations): `dynamic_suggestions` (text only), `dismiss_suggestion` (feedback only), `approve_denon_music_lighting` (only device-capable).
- **Safety fix:** the approve automation now requires `ai_actions_enabled` = on. With the gate OFF, pressing Approve records feedback and changes nothing.
- Wired 3 new rooms (Theater/Shop/Basement Landing) into the aggregates → 11 rooms. Added per-person presence.

### TV signal fix
- `tv_active` previously counted the DVR, which reports "playing" ~24/7, so it fired constantly. Now keys off the LG TV only. Also fixed `music_playing`, whose DVR-based guard had been suppressing all music detection.

### Phase 2 — activity vocabulary
- Working (office 5+ min, weekday hours), Cooking (kitchen 5+ min, meal window), Listening to Music (music on, TV off). Dining blocked pending hardware.

### Phase 1.5 / 1.6 + earlier
- Room-level awareness (grew to 11 rooms). Fixed: kitchen presence counted as family room; office presence didn't register. Sleep corroborated by a "still human" mmWave target (manual `sleep_no_lights` remains authoritative).
- Optimization: eliminated confidence flapping, DRY refactor to derived helpers, evidence-based dynamic confidence, removed junk person entities.
- Repaired an unrelated "House Mode" lighting automation that used `input_select.set_options` (which destroys the option list) instead of `select_option`.

## Known-open items

- Repair a stuck HAI Family Room motion zone (excluded until fixed).
- Two YAML-defined duplicate person entities need manual removal + reload.
- Consider consolidating the two Apple location integrations onto iCloud3.
- Hardware wishlist: dining-room presence, kitchen appliance power, living-room presence.
- Continue Phase 3 feedback until at least 50 reviewed outcomes and all
  calibration, target-sample, precision, signal-health, and drift gates pass.
- Per-person activity attribution; stale-evidence confidence decay; shower +
  laundry detection.

**Safety gate `input_boolean.ai_actions_enabled` remains OFF.** The one
device-capable automation (approve music lighting) is gated behind it.
