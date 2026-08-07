# Helpers

All helpers are created via the HA config-flow / UI (template, tod, input_*),
not YAML. This file documents their definitions for reference.

## Template binary sensors — derived signals

| Entity | State template (Jinja) |
|---|---|
| `binary_sensor.residents_home` | `{{ is_state('person.randy','home') or is_state('person.kim','home') or is_state('person.alex','home') }}` |
| `binary_sensor.home_room_presence` | OR of the 11 `*_occupied` room helpers |
| `binary_sensor.tv_active` | `{{ states('media_player.lg_webos_smart_tv') in ['on','playing','paused'] }}` |
| `binary_sensor.music_playing` | a music source is `playing` **and** the LG TV is not on (Denon-verified) |
| `binary_sensor.night_time` | `tod` helper, 21:00–07:00 |
| `binary_sensor.exterior_door_open` | `{{ is_state('binary_sensor.hai_front_door','on') or is_state('binary_sensor.hai_garage_door','on') or is_state('binary_sensor.hai_deck_door','on') or states('cover.gdo1_door') in ['open','opening'] or states('cover.grgdo1_door') in ['open','opening'] }}` |
| `binary_sensor.recent_arrival` | `{{ (now().timestamp() - (state_attr('input_datetime.home_last_entry','timestamp') | float(0))) < 480 }}` |

## Template binary sensors — per-room occupancy (11 rooms)

Each ORs together the real motion / mmWave / FP2 sensors for that room so a single
flaky sensor cannot pin a room occupied.

| Room helper | Source sensors (summarized) |
|---|---|
| `binary_sensor.family_room_occupied` | Aqara FP2 zones 1 + 3 |
| `binary_sensor.kitchen_occupied` | kitchen motion group + kitchen occupancy group + FP2 zone 2 |
| `binary_sensor.office_occupied` | 3 ESPHome presence sensors |
| `binary_sensor.foyer_occupied` | ESPHome presence sensor |
| `binary_sensor.master_bedroom_occupied` | 3 mmWave (human / moving / still) + 2 motion sensors |
| `binary_sensor.master_bath_occupied` | closet motion |
| `binary_sensor.basement_occupied` | ESP radar (movement / occupancy) |
| `binary_sensor.basement_landing_occupied` | basement-landing occupancy |
| `binary_sensor.theater_occupied` | theater occupancy |
| `binary_sensor.shop_occupied` | shop occupancy |
| `binary_sensor.upstairs_hall_occupied` | Zigbee motion (Aqara aq2) |

## Template sensors

| Entity | Purpose |
|---|---|
| `sensor.home_active_room` | joins the names of currently-occupied rooms, e.g. "Family Room, Office", or "None" |
| `sensor.residents_present` | joins the names of residents currently home, e.g. "Randy", or "Nobody home" |

## Input helpers (state written by the automations)

- `input_select.home_context_mode` — Unknown · Waking · Active · Relaxing · Entertaining · Sleeping · Away
- `input_select.home_current_activity` — Unknown · Daily Life · Cooking · Dining · Watching TV · Listening to Music · Working · Entertaining · Sleeping · Away
- `input_number.home_context_confidence` — 0–100
- `input_text.home_context_summary` — human-readable evidence
- `input_text.home_next_likely_activity` — predicted next activity
- `input_text.home_context_suggestion` — current suggestion text (Phase 4)
- `input_text.home_context_feedback` — approve/dismiss feedback (Phase 4)
- `input_datetime.home_last_entry` — stamped when a front/garage-entry door opens
- `input_button.approve_home_context_suggestion` / `input_button.dismiss_home_context_suggestion`

## Control / safety flags

- `input_boolean.ai_context_enabled` — master switch (ON)
- `input_boolean.ai_actions_enabled` — **safety gate (OFF)**; no device is controlled while OFF
- `input_boolean.home_context_guest_mode`, `input_boolean.party_mode`, `input_boolean.sleep_no_lights`

## Engine health / observability (Phase 3)

Detects when the Observer stops running (master switch turned off, or an
automation error), so a *frozen* classification is never mistaken for a live one.

| Entity | Type | Definition |
|---|---|---|
| `sensor.home_context_observer_age` | template **sensor** | Minutes since the Observer last ran. `state:` `{% set lt = state_attr('automation.home_context_evening_observer','last_triggered') %}{{ ((now() - lt).total_seconds() / 60) \| round(0) }}` · `device_class: duration` · `unit: min` · `state_class: measurement` · availability guarded on `last_triggered is not none`. |
| `binary_sensor.home_context_engine_stalled` | **threshold** helper | Turns **on** when `sensor.home_context_observer_age` exceeds **15 min**, with `hysteresis: 2` (on above ~17, off below ~13). `entity_id: sensor.home_context_observer_age`, `upper: 15`. |

The dashboard's **Engine Health** section surfaces both, plus a red **STALLED**
badge (visible only when stalled) and a conditional card explaining the likely
cause (usually: the master switch is OFF, so everything is frozen at the last
classification).

