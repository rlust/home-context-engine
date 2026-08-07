# Home Context Engine — Vision & Roadmap

## The vision

Home Assistant should be **aware of the context of activities in the home** — as
people come and go, move between rooms, and interact with devices — and
**adapt the home to their needs** as it monitors them and the house.

Classification is the means. **Adaptation is the end.** Every change is judged
against one question: *does this make the home more aware, or more adaptive?*

## Standing principles

1. **Observe before acting.** `ai_actions_enabled` is the safety gate; it stays OFF until accuracy is proven.
2. **Richer sensing over more rules.** Per-room, per-activity awareness beats another hardcoded condition.
3. **Gate on confidence.** Never act unconditionally.
4. **Investigate before removing.** "Dead-looking" config has repeatedly turned out to be load-bearing; a broken-looking helper is more often bugged than unused.
5. **Validate every sensor against history before trusting it.** A sensor that is always "on" is worse than no sensor — it silently pins a room to occupied.
6. **Specific beats generic.** Order activity branches most-specific first; require sustained presence + corroboration so passing through a room does not become an activity.
7. **Keep the plan document living.**
8. **Earn each phase.** Measurement justifies suggestion; suggestion justifies action.

**Success criteria:** ≥80% classification accuracy · fewer than 5 wrong recommendations/week · no unexplained device actions.

## Roadmap

Through-line: **awareness → measurement → suggestion → adaptation.**

- **Phase 1 — Situational awareness** ✅ observe-only mode + activity classification
- **Phase 1.5 — Room-level awareness** ✅ per-room occupancy + active-room sensor
- **Phase 1.6 — Extended room coverage** ✅ 11 rooms; sleep corroborated by Master mmWave
- **Phase 2 — Activity vocabulary** ✅ Working / Cooking / Listening to Music / Watching TV
- **Phase 3 — Measurement before action** ◀ context logging, dwell time, a "that was wrong" correction path (engine-stall monitoring added)
- **Phase 4 — Suggest, then adapt** — suggestion layer started (observe-only): the home proposes, accept-rate becomes the accuracy metric; confidence-gated action later, reversible domains first, never locks/alarm/climate without sign-off
- **Phase 5 — Learn patterns** — learned typicals replace hardcoded windows; handle guests, travel, seasons

## Sensor coverage

The home spans multiple floors and ~30 areas. Rooms with presence sensing wired
into the engine: Family Room, Kitchen, Office, Foyer, Master Bedroom, Master
Bath, Basement, Basement Landing, Theater, Shop, Upstairs Hall.

**Doors** (front, garage-entry, deck) and the two vehicle garage covers feed
arrival/departure awareness.

**Blind spots / wishlist hardware:** a dining-room presence sensor (would unlock
the "Dining" activity), kitchen appliance-power monitoring (would turn "Cooking"
from inference into evidence), and a living-room sensor. Master humidity could
drive shower detection via a trend helper; a dryer signal exists for a possible
"Laundry" activity.
