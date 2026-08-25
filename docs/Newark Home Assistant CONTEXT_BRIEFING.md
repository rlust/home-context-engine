# Home Context Engine — Project Briefing

*A shared-context handoff for any agent or collaborator working on Randy's Newark
Home Assistant. Written 2026-08-12. This is the "why," the "where we are," and the
"where we're going" — read this before touching the context system.*

---

## 1. The mission (the "why")

Make the home **aware of the household's context** — who is home, which room they're
in, what they're doing, and what "mode" the house is in — as people come and go and
interact with devices. Then use that awareness to **adapt the home to the occupants'
needs** automatically.

The end state is a home that **notices and adjusts on its own**: lights, climate,
media, and scenes that follow real activity instead of fixed schedules or manual
toggles. Context first; adaptation second.

## 2. The core desire: DYNAMIC and SELF-ADJUSTING

This is the north star and the thing to optimize every decision toward. The engine
should **not** stay a pile of hand-tuned rules. It should become a **learning system**
that tunes itself:

- **Learns typical patterns** — per room, per time-of-day, per person, per day-of-week
  (e.g. "office 9–5 on weekdays = Working," "family room + TV after 8pm = Watching TV").
- **Tunes its own confidence** from real feedback instead of hardcoded bonuses.
- **Decays stale evidence** — a sensor that fired 40 min ago should weigh less than one
  firing now.
- **Attributes activity per person**, not just household-wide.
- **Predicts the next likely activity** and pre-adapts.
- **Eventually acts** — adaptive lighting/climate/scenes that adjust to context, gated
  on proven accuracy and confidence.

The **human-in-the-loop correction path is the training signal.** Every "Mark WRONG"
tap (Phase 3, below) is a labeled example of where the model was wrong. That feedback
loop is the seed of self-adjustment — the plan is to feed it back into automatic tuning
rather than us hand-editing thresholds forever.

## 3. Non-negotiable guardrails

1. **Observe before acting.** The engine is currently **observe-only**. The hard safety
   gate `input_boolean.ai_actions_enabled` stays **OFF** until accuracy is proven. The
   one device-capable automation (an evening music-lighting suggestion) requires **both**
   a manual button press **and** that gate ON.
2. **Prove accuracy before automating.** No autonomous action ships until the measured
   error rate is under target (see Phase 3).
3. **Richer sensing over more hardcoded rules.** Prefer adding a real sensor/signal over
   another special-case branch.
4. **Investigate before removing.** "Dead-looking" config here has repeatedly been
   load-bearing. Trace consumers first.
5. **Validate every sensor against history** before trusting it.
6. **Keep the plan living** — the Apple note + this repo are the source of truth.

## 4. How it works today (architecture)

- **One Observer automation** (`automation.home_context_evening_observer`) runs at
  startup, every 5 min, and on any relevant signal change. It walks a `choose` block
  **most-specific-branch-first** and writes only helper entities — it never controls a
  device. Branch order: Sleeping → Entertaining → Away → Working → Cooking → Watching TV
  → Listening to Music → Waking → Active → Unknown.
- **Outputs** (helpers the Observer writes): `input_select.home_context_mode`,
  `input_select.home_current_activity`, `input_number.home_context_confidence`,
  `input_text.home_context_summary`, `input_text.home_next_likely_activity`.
- **Room awareness — 12 rooms.** Each `binary_sensor.<room>_occupied` ORs the real
  motion/mmWave/FP2 sensors for that room, so one flaky sensor can't pin a room, and
  movement *between* rooms re-classifies context. Aggregated by
  `binary_sensor.home_room_presence` and `sensor.home_active_room`.
- **Signals.** `residents_home`, `tv_active` (LG TV only), `music_playing`, `night_time`,
  `exterior_door_open`, `recent_arrival` (8 min after an entry-door event).
- **Evidence-based confidence.** Each branch computes `base + bonuses` for corroborating
  signals, weighted so stable signals dominate and mmWave jitter moves the score by only
  a few points. This is the piece most ripe for **self-tuning**.
- **Presence.** `person.randy` / `person.kim` on carried-phone-only iCloud3 trackers
  (dual-source iCloud Find My + companion app); `person.alex` untracked. Accurate
  presence feeds `residents_home` → the Away branch.

## 5. Roadmap & status

| Phase | What | Status |
|---|---|---|
| 1 / 1.5 / 1.6 | Situational + room-level awareness (→ 12 rooms) | ✅ done |
| 2 | Activity vocabulary (Working / Cooking / Music / TV) | ✅ done |
| **3** | **Measurement — a "that was wrong" correction path; score accuracy** | **◀ RUNNING (started 2026-08-09)** |
| 4 | Suggest → then act (observe-only suggestions built; gated actions next) | started (observe-only) |
| 5 | **Learn typical patterns — the self-adjusting core** | planned |

### Short-term goal (now → next ~week)
Run the **Phase 3 accuracy measurement week**. The household taps **Mark WRONG** whenever
a classification is clearly off; each tap increments `counter.home_context_corrections`
and logs a snapshot. The Monday review scores **wrong-per-week vs a <5 target** and only
green-lights Phase 4 after a full 7+ day window under target. Helpers:
`input_button.home_context_mark_wrong`, `counter.home_context_corrections`,
`input_text.home_context_last_correction`, `input_datetime.home_context_measurement_start`.

### Medium-term goal (Phase 4)
Once accuracy is proven, turn on **one** high-confidence adaptive action at a time
(e.g. context-aware lighting/music), each gated behind `ai_actions_enabled` and a
confidence threshold. Suggest → approve → automate, never a broad rollout.

### Long-term goal (Phase 5 — the whole point)
The **self-adjusting engine**: learn per-room/per-time/per-person baselines; auto-tune
confidence weights from the Mark-WRONG feedback; decay stale evidence; per-person
activity attribution; predictive pre-adaptation; adaptive scenes that follow context
without manual rules. Move from "rules we wrote" to "patterns it learned."

## 6. Where to engage / coordination

- **Two agents share this HA.** Changes are live and mutually visible. Coordinate on
  **dashboards** (`home-command` — concurrent edits cause config_hash conflicts) and on
  **shared sensors** (Aqara FP300, Unity mmWave, the LD1115H radar).
- **Highest-leverage next work toward the vision:** anything that turns the Mark-WRONG
  feedback into automatic tuning; per-person attribution; stale-evidence decay; and
  hardening flaky sensors (the LD1115H radar keeps dropping — a template, not a group,
  degrades gracefully).
- **Backup / full detail:** repo `github.com/rlust/home-context-engine`
  (README, `docs/VISION_ROADMAP.md`, `docs/PLAN.md`, `helpers/HELPERS.md`), plus the
  living Apple note "Home Context Controls for Home Assistant Newark plan."

**Bottom line:** we're building a home that senses context and adapts to it — and the
real goal is for it to **learn and adjust itself** over time, with accuracy proven
before it's ever allowed to act.
