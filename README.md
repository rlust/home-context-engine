# Home Context Engine (Newark)

A **context-awareness layer for Home Assistant**. It observes who is home, which
rooms are occupied, what media is playing, and how people come and go — then
classifies the household's current **mode** and **activity** with an
**evidence-based confidence score**. The long-term goal is a home that *adapts*
to its occupants; today it is strictly **observe-only**.

> **Safety model:** `input_boolean.ai_actions_enabled` is a hard gate that stays
> **OFF**. Nothing in this project controls a device autonomously. The single
> automation that *can* touch a device (an evening music-lighting suggestion)
> requires **both** a manual button press **and** the safety gate to be ON.

This repo is a **sanitized export** — internal IP addresses, the Apple ID, and
account/device identifiers have been replaced with placeholders. It is a record
and reference for the project, not a turnkey import.

**Project direction:** fewer unnecessary interactions, fewer wrong actions and
more trust. See the [vision and execution roadmap](docs/VISION_ROADMAP.md) for
the September 13, 2026 goals, measurement gates and ordered implementation work.
Historical deployment statements in this repository are not live-state checks.

**For Codex and other agents:** start with [AGENTS.md](AGENTS.md), then the
[current handoff](docs/PLAN.md#current-handoff---2026-09-13). Keep code, tests,
dated evidence and the next unfinished task synchronized in each change. For a
ChatGPT session without repository access, provide this repository and ask it
to read those files first; repository guidance is not automatically global memory.

---

## How it works

A single automation, the **Observer**
(`automations/home_context_observer.json`), runs at startup, every five minutes,
and whenever a relevant signal changes (room occupancy, presence, media, doors).
It walks a `choose` block **most-specific-branch-first** and writes the result to
helper entities. It never calls a device service.

```
Sleeping → Entertaining → Away → Working → Cooking →
Watching TV → Listening to Music → Waking → Active → Unknown
```

### Signals feed the classifier through derived helpers

| Helper | Meaning |
|---|---|
| `binary_sensor.residents_home` | any of person.randy / kim / alex is home |
| `binary_sensor.home_room_presence` | any of 12 room-occupancy helpers is on |
| `sensor.home_active_room` | names the currently occupied room(s) |
| `binary_sensor.tv_active` | the LG webOS TV is on (not the always-on DVR) |
| `binary_sensor.music_playing` | a music source is playing and the TV is off |
| `binary_sensor.night_time` | time-of-day helper, 21:00–07:00 |
| `binary_sensor.exterior_door_open` | any exterior door / garage is open |
| `binary_sensor.recent_arrival` | 8 min after a front/garage-entry door opens |

Twelve per-room occupancy helpers (`*_occupied`) each OR together the real
motion/mmWave/FP2 sensors for that room, so a single flaky sensor cannot pin a
room "occupied," and movement **between** rooms re-classifies the context.

### Confidence is evidence-based

Each branch computes `base + bonuses` for corroborating signals, weighted so
**stable** signals dominate and mmWave jitter moves the score by at most a few
points. High when independent signals agree; low when evidence is thin or
conflicting.

| Activity | Range | Strongest evidence |
|---|---|---|
| Sleeping | 53–97 | night + master bedroom occupied |
| Watching TV | 78–96 | family room occupied (+18) |
| Working | 76–88 | office 5+ min, weekday 07:00–18:00 |
| Cooking | 72–90 | kitchen 5+ min, meal window |
| Listening to Music | 74–92 | music on, TV off |
| Away | 85–90 | no residents, no room presence 45s, no recent arrival |

---

## Repo layout

```
automations/   HA config-API JSON:
                 home_context_observer ............ the classifier
                 home_context_stamp_entry ......... arrival/departure timestamp
                 home_context_dynamic_suggestions . Phase 4 suggestion text
                 home_context_approve_denon_music_lighting . gated, manual-only action
                 home_context_dismiss_suggestion .. records dismissal
                 home_context_engine_stalled_alert  Phase 3: notify if observer stalls
                 home_context_mark_wrong .......... Phase 3: log a "that was wrong" correction
                 home_context_sync_bed_time ....... peripheral house-mode ↔ bed_time sync
helpers/       Template + group + input helper definitions (HELPERS.md)
dashboard/     The "Home Context" Lovelace view, current live-view snapshot,
               and offline signal-issue card design
docs/          PLAN.md (working log), VISION_ROADMAP.md (north star), and
               operations/ (credential-free deployment plans and evidence)
```

## Roadmap (abridged — see docs/VISION_ROADMAP.md)

- **Phase 1 / 1.5 / 1.6** ✅ situational + room-level awareness (12 rooms)
- **Phase 2** ✅ activity vocabulary (Working / Cooking / Music / TV)
- **Phase 3** ◀ measurement — Confirm / Wrong / Unsure feedback, private
  aggregate scoring, and signal diagnostics
- **Phase 4** suggest → then adapt (started; observe-only)
- **Phase 5** learn typical patterns

Phase 4 remains locked until the private report has at least 50 reviewed
outcomes, an exact target activity has at least 20 reviewed samples and at
least 90% precision, calibration error is at most 10 percentage points, and
required-signal health plus drift gates pass. The latest credential-free
aggregate and diagnostics deployment evidence is in
`docs/operations/`.

## Design principles

Latest verified operational checkpoint: [2026-09-08 dashboard and measurement
update](docs/operations/HOME_CONTEXT_CHECKPOINT_2026_09_08.md). This documents
live changes without exporting household locations, feedback records, or the
production dashboard. Existing dashboard exports remain dated references.

1. Observe before acting; the safety gate stays OFF until accuracy is proven.
2. Richer sensing over more hardcoded rules.
3. Gate any future action on confidence.
4. Investigate before removing — "dead-looking" config has repeatedly been load-bearing.
5. Validate every sensor against history before trusting it.
6. Keep the plan document living.
