# Home Context Controls — Working Log

Sanitized export of the project's running log. Internal IPs, the Apple ID, and
device/account identifiers have been replaced with placeholders.

## Current system

- **Context helpers:** `home_context_mode`, `home_current_activity`, `home_context_confidence`, `home_context_summary`, `home_next_likely_activity`, `home_context_guest_mode`, `sleep_no_lights`; `ai_context_enabled` (ON), `ai_actions_enabled` (**OFF — safety lock**).
- **Presence:** `sensor.residents_present`; `person.randy` (carried iPhone), `person.kim` (carried iPhone Pro Max via iCloud3), `person.alex`.
- **11 room-occupancy helpers** + `binary_sensor.home_room_presence` + `sensor.home_active_room`.
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
- Phase 3 measurement instrumentation (correction path); per-person activity attribution; stale-evidence confidence decay; shower + laundry detection.

**Safety gate `input_boolean.ai_actions_enabled` remains OFF.** The one
device-capable automation (approve music lighting) is gated behind it.
