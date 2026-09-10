# Home Context Engine

Status: Active project  
Started: 2026-07-16  
Home Assistant instance: Newark

## Vision

Build a privacy-conscious context layer that learns how the household functions, explains what it has learned, and gradually offers useful actions through Home Assistant.

Home Assistant remains the source of truth and the trusted control layer. AI interprets compact structured context, explains patterns, and proposes actions. It does not silently rewrite automations or directly control safety-critical devices.

## Architecture

1. Home Assistant collects current state from presence, motion, doors, security, climate, environment, leak, lighting, media, energy, weather, calendar, and system-health entities.
2. Native helpers represent the current household context in a small, understandable state model.
3. A context-memory service records curated episodes and summaries rather than copying the complete Recorder database.
4. Statistical learning identifies repeated routines, sequences, manual overrides, and anomalies.
5. AI Task and Assist convert structured observations into explanations and recommendations.
6. Approved Home Assistant scripts and scenes execute safe actions with deterministic conditions, audit logging, and an undo path.

## Context model

### Live context

- Household mode: unknown, waking, active, relaxing, entertaining, sleeping, away.
- Guest mode.
- Quiet hours.
- Occupied rooms.
- Current activity.
- Next likely activity.
- Context confidence.
- Unusual-state summary.

### Routine memory

- Typical wake, sleep, departure, and return windows.
- Room occupancy sequences.
- Lighting behavior by occupancy and daylight.
- Climate adjustments and comfort preferences.
- TV, Denon, Genie, and Apple TV usage patterns.
- Energy baselines.
- Manual overrides and rejected recommendations.
- Sensor-health and availability patterns.

### Explicit preference memory

- Preferences confirmed by a person.
- Accepted, adjusted, dismissed, and blocked suggestions.
- Evidence count, confidence, last confirmation, and expiration for each preference.

## Safety and privacy rules

- AI starts in observation-only mode.
- AI actions and AI context processing have separate master switches.
- Only curated entities and tools are exposed to an AI agent.
- Raw microphone audio and continuous camera footage are not stored as context memory.
- Every recommendation includes evidence and confidence.
- A single unusual event is not treated as a learned preference.
- Reversible lighting, media, and bounded climate actions may become eligible for limited autonomy.
- Locks, alarm disarming, garage doors, water shutoff, cameras/privacy modes, cooking appliances, and other safety-sensitive actions require explicit approval unless handled by an existing deterministic safety automation.
- Every AI-initiated action is logged and has a practical undo path.

## Delivery roadmap

### Phase 1: Context foundation

Status: Observation active

- Inventory existing helpers and monitored signals.
- Create native helpers for household mode, guest mode, quiet hours, AI context enabled, AI actions enabled, current activity, context confidence, and related state.
- Establish safe initial values. AI actions remain disabled.
- Document the live entity IDs.
- Add a compact Context section to the Home Center dashboard after the helper model is validated. Completed on the `home-command/today` view.

#### Live Phase 1 helpers

Created and read back successfully on 2026-07-16:

- `input_select.home_context_mode` — Unknown, Waking, Active, Relaxing, Entertaining, Sleeping, Away.
- `input_boolean.ai_context_enabled` — master switch for context processing; currently on for observation.
- `input_boolean.ai_actions_enabled` — independent master switch for AI-initiated actions; currently off.
- `input_boolean.home_context_guest_mode` — explicit guest-mode input; currently off.
- `input_number.home_context_confidence` — 0 to 100 percent; first live classification is 90 percent.
- `input_select.home_current_activity` — current inferred household activity; first live classification is Sleeping.
- `input_text.home_context_summary` — compact human-readable evidence summary.
- `input_text.home_next_likely_activity` — compact predicted next activity.

Existing `input_select.house_mode` was not modified. It currently exposes only the `Sleep Time` option and may have legacy consumers. Existing `input_boolean.party_mode`, `input_boolean.bed_time`, and related occupancy helpers will be treated as candidate evidence rather than replaced.

#### Live Phase 1 observer

Activated and validated on 2026-07-16:

- `automation.home_context_evening_observer` re-evaluates on Home Assistant start, every five minutes, and when its curated presence, household-mode, or family-room media signals change.
- The observer uses deterministic priority: bedtime, guest/party, away, family-room media, other media, active presence, then unknown.
- It writes only the Phase 1 context helpers. It does not control lights, climate, media, locks, alarms, doors, or other devices.
- The first live result was mode `Sleeping`, activity `Sleeping`, confidence `90`, and next likely activity `Waking`, supported by `input_boolean.bed_time` being on.
- The `home-command/today` dashboard now shows a three-column Home Context row above At a Glance: current mode and evidence, confidence and next activity, and safety/guest guardrails.
- Home Assistant configuration validation passed after the automation and dashboard changes. AI actions remain disabled.

#### Phase 1 review - 2026-07-16

Reviewed live state, recorder history, and observer traces at 2026-07-16 09:04 EDT.

- Current helper state remains `Sleeping` / `Sleeping` with confidence `90`, summary `Bed Time RC is on; household classified as sleeping.`, and next likely activity `Waking`.
- `input_boolean.ai_actions_enabled` is still `off`.
- Recorder history for the Home Context helpers on 2026-07-16 shows only `Unknown` to `Sleeping`. No live transitions into `Waking`, `Active`, `Relaxing`, `Entertaining`, or `Away` have been observed yet, so the one-week observation period is still in progress.
- Recent observer traces at 09:02 EDT all selected the bedtime branch, including runs triggered by kitchen/family-room presence changes and Genie updates.
- A likely stale false positive is already visible: at review time the house still classified as `Sleeping` while `zone.home` was `2`, `binary_sensor.presence_1_presence_2` was `on`, and `media_player.genie` was `playing`. Because `input_boolean.bed_time` stayed `on` all morning, the highest-priority bedtime rule masked daytime evidence and prevented `Active` or `Relaxing` transitions.
- `Waking` is a configured mode option and the predicted next activity, but the observer has no branch that can actually write `Waking`. That is a verified missed-transition gap by design, not a recorder anomaly.
- `media_player.genie` is part of the trigger set, but neither Relaxing branch checks Genie state. Genie-only TV usage can wake the observer without ever qualifying as `Relaxing`.
- `Away` confidence needs more observation because the automation summary says `No tracked people`, but the actual rule depends on `zone.home < 1`. During this review `zone.home` was inflated by `person.randyperson` being home in addition to `person.randy`, so an extra person entity can block `Away` even when the named tracked-person set does not match the narrative.
- No live automation rule changes were applied during this review. Verified change candidates for the next tuning pass are: add an explicit `Waking` branch, prevent stale `bed_time` from dominating daytime classifications, include Genie in media-based relaxing evidence, and decide whether `Away` should use the named tracked persons instead of raw `zone.home`.
- Validation result: `ha_get_system_health(include="config_check")` returned `valid` with no configuration errors.

#### Phase 1 review - 2026-07-19

Reviewed live state, recorder history, and configuration validation on 2026-07-19.

- `input_boolean.ai_actions_enabled` remains `off`.
- The observer is no longer stuck on a single mode. Recorder history now shows `Relaxing` transitions on 2026-07-18 at 20:37 EDT and 22:19 EDT, which confirms the family-room media branch can fire.
- Those `Relaxing` states were short-lived and reverted back to `Sleeping` within about three minutes at 20:40 EDT and within about seven seconds at 22:19:50 EDT.
- The bedtime latch is still the dominant problem. During both 2026-07-18 relaxing windows, `input_boolean.bed_time` stayed `on`, so the classifier could briefly recognize active media and then snap back to the higher-priority sleeping branch without any evidence that the household had actually gone to bed.
- The same stale-sleeping pattern is still visible on 2026-07-19 in the morning: at review time the mode was `Sleeping` with confidence `90` while `zone.home` was `1`, `person.randy` was home, and `media_player.genie` was `playing`. The summary still said `Bed Time RC is on; household classified as sleeping.`
- `Waking` is still only a predicted next activity. The helper history from 2026-07-16 through 2026-07-19 shows no actual transition into `Waking`, `Active`, `Entertaining`, or `Away`.
- `Away` distortion from `person.randyperson` is reduced compared with 2026-07-16 because the entity is now `unknown`, but the observer still depends on `zone.home` instead of the explicit named tracked-person set, so the underlying design risk remains.
- No live automation rule changes were applied during this review. The most defensible next tuning step is still to fix or gate `input_boolean.bed_time` before changing confidence numbers or adding more branches. After that, add an explicit `Waking` branch and then decide whether `Away` should be based on the named tracked persons rather than raw `zone.home`.
- Validation result: `ha_get_system_health(include="config_check")` returned `valid` with no configuration errors on 2026-07-19.

#### Verified rule change - 2026-07-19

Applied and verified a narrow source-signal fix on 2026-07-19:

- Created `automation.home_context_sync_bed_time_rc_from_house_mode`.
- The new automation keeps `input_boolean.bed_time` aligned with `input_select.house_mode` by forcing bedtime `on` only for `Sleep Time`, `Sleep`, `Bedtime`, and `Early Morning`, and forcing it `off` for all other house modes.
- The automation runs on Home Assistant start, on every `input_select.house_mode` change, and every 10 minutes as a guard against stale latches.
- Immediate validation after triggering the new automation live: `input_select.house_mode` was `Morning`, `input_boolean.bed_time` changed to `off`, and `automation.home_context_evening_observer` reclassified the household from stale `Sleeping` to `Active` / `Daily Life` with confidence `70`.
- Verified post-fix helper state at 2026-07-19 09:11 EDT:
  - mode: `Active`
  - activity: `Daily Life`
  - summary: `A tracked person or monitored-room presence is active; normal household activity inferred.`
  - next likely activity: `Continue Current Activity`
- Post-change validation result: `ha_get_system_health(include="config_check")` returned `valid` with no configuration errors on 2026-07-19.

#### Verified presence-source correction - 2026-07-22

Applied and verified the requested authoritative person-to-iPhone mappings:

- Updated `person.randy` to use only `device_tracker.iot2` (Randy's iPhone 16), replacing 19 competing device trackers. The initially selected `device_tracker.rc_iphone` was superseded the same day after it was found to be stale. The person now resolves `home` from `iot2` with GPS accuracy of about 8 m and a fresh 19:35 EDT report.
- Updated `person.kim` to use only `device_tracker.kim_iphone_12`, replacing the stale Apple Watch-only mapping. The person immediately corrected from `not_home` to `home` from that tracker.
- The Home Context observer continues to consume `person.randy` and `person.kim`, so no observer-rule change was required. Its current result remains `Active`.
- `input_boolean.ai_actions_enabled` remains `off`; this correction changes only observation evidence and cannot control devices.
- Post-change validation result: `ha_get_system_health(include="config_check")` returned `valid` with no configuration errors on 2026-07-22.
- Observation caveat: Randy's selected tracker is now fresh, but Kim's selected iPhone tracker last reported at 07:55 EDT on 2026-07-22. The next review must confirm fresh updates during actual arrivals or departures before treating either source as proven against Away flapping.

#### Phase 1 review - 2026-07-23

Reviewed Newark live observer configuration, current entity states, and a fresh configuration validation check at 2026-07-23 09:06 EDT.

- Current live read-back still shows `input_select.home_context_mode` as `Active`, with `person.randy` and `person.kim` both currently `home`.
- `input_boolean.ai_actions_enabled` remains `off`.
- `ha_get_system_health(include="config_check")` again returned `valid` with no configuration errors on 2026-07-23.
- The observer logic itself is unchanged from the 2026-07-19 post-fix version. The verified design gaps are therefore still present:
  - `Waking` remains unreachable because no observer branch ever writes that mode.
  - `Away` still depends on `zone.home` rather than the explicit tracked-person set, so cached `home` presence or extra zone contributors can still mask departures.
  - `media_player.genie` is still only a trigger source, not relaxing evidence, so Genie-only TV sessions can still miss `Relaxing`.
- The stale-bedtime source fix is still in place via `automation.home_context_sync_bed_time_rc_from_house_mode`, so the previously verified daytime false-positive `Sleeping` latch should remain mitigated as long as `input_select.house_mode` stays accurate.
- Evidence remains incomplete for a full transition audit today. The Newark search/read surface timed out on deeper config/history scans, so this review could not yet re-verify fresh recorder-backed transitions for `Waking`, `Relaxing`, `Entertaining`, `Sleeping`, and `Away`, and it could not yet confirm fresh arrival/departure timestamp pairs for `device_tracker.iot2` and `device_tracker.kim_iphone_12`.
- Because the missing evidence is on the observation side rather than the rule side, no new automation edits were applied in this review.

Next review target: 2026-07-24, preferably after at least one real arrival or departure and one evening media session are visible in recorder history.

#### Phase 1 review - 2026-07-30

Reviewed Newark live observer configuration, current entity states, recorder history, recent observer traces, and a fresh configuration validation check at 2026-07-30 14:24 EDT.

- Current live read-back shows `input_select.home_context_mode=Active`, `input_select.home_current_activity=Cooking`, `input_number.home_context_confidence=90`, `input_text.home_next_likely_activity=Dining`, `person.randy=not_home`, and `person.kim=home`.
- `input_boolean.ai_actions_enabled` remains `off`.
- `ha_get_system_health(include="config_check")` returned `valid` with no configuration errors on 2026-07-30.
- The live observer has moved beyond the earlier Phase 1-only assumption set. `Waking` is now a real branch in `automation.home_context_evening_observer`, and recorder history shows at least one verified `input_select.home_context_mode=Waking` transition on 2026-07-27 at 08:50 EDT.
- `Active`, `Relaxing`, and `Sleeping` transitions are all present repeatedly in the 2026-07-23 through 2026-07-30 recorder window. `Relaxing` is common, `Sleeping` still appears nightly, and the current daytime `Cooking` activity is carried under `home_context_mode=Active`.
- `Entertaining` and `Away` were not observed in the `input_select.home_context_mode` history fetched for the last 7 days, so those branches remain unverified by recent recorder evidence rather than disproven.
- A likely false-positive or stale edge remains around overnight sleep handling. Multiple nights still show short `Sleeping -> Active -> Sleeping` oscillations around roughly 02:01 to 02:15 EDT before the morning transition, which suggests restart or helper-refresh churn rather than a real household wake cycle.
- A second likely false-positive remains near the home-zone boundary for Randy. `person.randy` briefly flipped `home -> not_home -> home` on 2026-07-27 from 19:20:37 to 19:24:58 EDT, and `home -> not_home` again on 2026-07-28 from 10:22:16 to 13:03:53 EDT, while the person source stayed `device_tracker.iot2`. Those transitions are fresh GPS updates, but they are close enough to the home/londondale boundary that cached `home` should still not be used as evidence against Away flapping.
- Randy's real departures and arrivals were backed by fresh source-tracker movement. For example, on 2026-07-30 `device_tracker.iot2` stepped `home -> Londondale` at 10:32:23 EDT and `Londondale -> not_home` at 10:32:50 EDT, matching `person.randy` moving to `not_home` at 10:32:50 EDT. On 2026-07-29 the return path was likewise fresh: `device_tracker.iot2` reached `Londondale` at 15:53:24 EDT, `home` at 15:53:59 EDT, and `person.randy` followed to `home` at 15:53:59 EDT.
- Kim did not show any real arrival or departure in the reviewed 7-day window. `person.kim` stayed effectively `home`, so there was no Away-boundary test for `device_tracker.kim_iphone_12`. The tracker itself still refreshed on 2026-07-30 at 07:03 EDT, but that was an in-place `home` refresh, not an arrival or departure.
- The requested "only from tracker" confirmation is only partially satisfied. Current live source attributes are correct: `person.randy` currently resolves from `device_tracker.iot2` and `person.kim` currently resolves from `device_tracker.kim_iphone_12`. However, recorder history still contains repeated restart-related transient states where `person.randy` or `person.kim` show `source=person.<name>` and, for Kim, brief `unknown` gaps before returning to the intended tracker source. That means the live mapping is correct, but the recorder history does not support claiming an uninterrupted tracker-only source path yet.
- Recent observer traces are available only for the last few executions and currently show ordinary periodic and occupancy-triggered runs on 2026-07-30. The deeper transition audit therefore depended mainly on recorder history rather than retained trace details.
- No live automation or helper rules were changed in this review. The only update made this run is this dated observation record.

Next review target: 2026-08-02, or sooner if a full-house departure, a real return, or a guest/party event occurs.

#### Phase 1 review - 2026-08-06

Reviewed Newark live observer configuration and current Home Assistant states on 2026-08-06 shortly after a 02:00 EDT restart/restore cycle.

- Current live read-back shows `input_select.home_context_mode=Relaxing`, `input_select.home_current_activity=Watching TV`, `input_number.home_context_confidence=96`, and `input_text.home_next_likely_activity=Bedtime`.
- `input_boolean.ai_actions_enabled` remains `off`, which keeps AI-initiated actions safely disabled.
- Observation mode is no longer active. `input_boolean.ai_context_enabled` is currently `off` as of 2026-08-06 02:00:51 EDT, so the observer's own condition blocks new classifications.
- That disable is consistent with the observer metadata: `automation.home_context_evening_observer` is still enabled, but its `last_triggered` remains 2026-08-04 22:10:00 EDT even though the context helpers all refreshed around 2026-08-06 02:00 EDT. Because the automation is configured to trigger on Home Assistant start, the combination of restored helper values plus a stale `last_triggered` strongly suggests the current helper state is restored/cached state rather than a fresh post-restart classification.
- The requested authoritative source check is now only partially satisfied. `person.randy` is still sourced from `device_tracker.iot2`, but `person.kim` is currently sourced from `device_tracker.kim_iphone16`, not `device_tracker.kim_iphone_12`. A direct live lookup for `device_tracker.kim_iphone_12` returned `ENTITY_NOT_FOUND`, so the 2026-07-22 source mapping is no longer true in the current Newark instance.
- Freshness at the current snapshot is acceptable for in-place state refreshes but does not prove arrival/departure correctness. At 2026-08-06, `device_tracker.iot2` last reported at 02:01:11 EDT and `person.randy` at 02:01:48 EDT; `device_tracker.kim_iphone16` last reported at 02:01:10 EDT and `person.kim` at 02:01:48 EDT. Those are fresh reports, but they are both current `home` snapshots, not an arrival or departure pair, so they do not validate Away behavior.
- Because the observer is blocked by `ai_context_enabled=off`, this review does not add new verified recorder-backed transitions for `Waking`, `Active`, `Relaxing`, `Entertaining`, `Sleeping`, or `Away`. The last strong transition evidence remains the 2026-07-30 review window. Cached `home` states are still not acceptable as proof against Away flapping.
- Verified rule changes this run: none.
- Validation result this run: live automation read-back succeeded and confirmed the startup trigger is still present; no new automation or helper edits were applied.

Next review target: 2026-08-09, after `input_boolean.ai_context_enabled` is intentionally re-enabled for observation and at least one real departure/return pair is visible from the current authoritative person trackers.

#### Phase 1 review - 2026-08-13

Reviewed Newark live observer configuration, current helper states, current presence/tracker sources, and current observer-health signals on 2026-08-13.

- The observer is live again. `input_boolean.ai_context_enabled=on`, `automation.home_context_evening_observer` is enabled, `automation.home_context_evening_observer.last_triggered` advanced through 09:02 EDT, `sensor.home_context_observer_age=1`, and `binary_sensor.home_context_engine_stalled=off`.
- Current live classification at review time is internally consistent with the configured rules: `input_select.home_context_mode=Active`, `input_select.home_current_activity=Working`, `input_number.home_context_confidence=88`, and `input_text.home_context_summary='Sustained office presence during weekday work hours; classified as working.'`
- Supporting live evidence for that current classification is present: `binary_sensor.office_occupied=on`, `binary_sensor.residents_home=on`, `binary_sensor.home_room_presence=on`, `binary_sensor.tv_active=off`, `binary_sensor.music_playing=off`, `input_boolean.sleep_no_lights=off`, and `binary_sensor.night_time=off`.
- `input_boolean.ai_actions_enabled` remains `off`, so AI-initiated actions are still safely disabled.
- Verified rule state changed since the 2026-07-30 and 2026-08-06 notes: the live observer no longer uses raw `zone.home` for Away. The current automation config requires `binary_sensor.residents_home=off`, `binary_sensor.recent_arrival=off`, and `binary_sensor.home_room_presence=off` for 45 seconds before writing `Away`. That is a safer design against cached `home` presence, but it still needs recorder-backed departure/return validation.
- The requested authoritative person mappings are currently not satisfied. `person.randy` is live-sourced from `device_tracker.rc_iphone`, not `device_tracker.iot2`. `person.kim` is live-sourced from `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, not `device_tracker.kim_iphone_12`. A direct state lookup for `device_tracker.kim_iphone_12` still returns `ENTITY_NOT_FOUND`.
- Current freshness favors the unexpected source trackers rather than the requested ones. At review time, `person.randy` reported at 08:50:46 EDT and its current source `device_tracker.rc_iphone` also reported at 08:50:46 EDT, while `device_tracker.iot2` last reported slightly earlier at 08:50:06 EDT. `person.kim` reported at 08:50:46 EDT and its current source `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max` also reported at 08:50:46 EDT, while `device_tracker.kim_iphone16` last reported at 08:50:06 EDT.
- Evidence remains incomplete for the full transition audit requested this round. This review verified the current live classification and the current Away-rule shape, but it did not obtain fresh recorder-backed history for all `Waking`, `Active`, `Relaxing`, `Entertaining`, `Sleeping`, and `Away` transitions in the current observation window. Because of that gap, do not claim that missing modes failed to occur, and do not treat the current `home` tracker states as proof against Away flapping.
- Verified rule changes this run: none applied. Verified live rule differences from prior notes: the observer now has an explicit `Waking` branch and the current `Away` branch depends on resident/home-room signals plus `recent_arrival`, not `zone.home`.
- Validation result this run: live read-back succeeded for the observer, context helpers, supporting binary sensors, and the observer-health signals. No Home Assistant automations or helpers were modified during this review.

Next review target: 2026-08-16, or sooner after one real departure/return pair for both residents is visible from the intended authoritative trackers.

#### Observation checklist and next review

Next review target: 2026-08-16, or sooner after one full-house departure/return pair or one verified guest/party session is visible from the intended authoritative trackers.

At each review:

1. Inspect the context-helper history and observer traces for Waking, Active, Relaxing, Entertaining, Sleeping, and Away transitions.
2. Compare each classification with presence, bedtime, party/guest, TV, Denon, Apple TV, and Genie states at that time.
3. Record false positives, missed transitions, stale states, and classifications with weak or conflicting evidence.
4. Tune rule priority and confidence only when history shows a repeated problem; do not optimize around a single unusual event.
5. Confirm `input_boolean.ai_actions_enabled` is still off and rerun the Home Assistant configuration check after changes.
6. Update this document with findings, rule changes, validation results, and the next review date.

Exit criteria for Phase 1 observation:

- At least seven days of observations spanning weekday and weekend behavior.
- No safety-sensitive device actions and no unintended device control.
- Major household transitions are classified correctly often enough to begin measuring accuracy formally.
- Evidence summaries are understandable and identify why the mode was selected.
- Repeated false positives have documented causes and proposed corrections.

The next implementation step after this review is a structured observation log and accuracy scorecard. Recommendation mode and AI actions remain out of scope until the observation data supports them.

### Phase 2: Context memory

Status: Planned

- Build a small private context service using Python and SQLite initially.
- Subscribe to a curated Home Assistant event set.
- Convert raw changes into meaningful episodes.
- Retain 30 to 90 days of structured routine history.
- Keep Recorder as Home Assistant's operational history rather than expanding it solely for AI.

### Phase 3: Routine learning

Status: Planned

- Calculate time windows, frequencies, transitions, correlations, and manual-override rates.
- Detect repeated routines and unusual deviations.
- Assign evidence, confidence, last-seen, and expiration values.
- Require repeated evidence before creating a learned routine.

### Phase 4: Recommendation mode

Status: Planned

- Produce morning, evening, and weekly context summaries.
- Show suggested actions with Approve, Adjust, Dismiss, and Never suggest again controls.
- Record feedback as explicit preference evidence.
- Measure false positives and suggestion acceptance.

### Phase 5: Context-aware Assist

Status: Planned

- Add narrow tools such as `get_home_context`, `get_recent_activity`, `get_learned_routine`, `explain_unusual_state`, `record_household_preference`, and `propose_home_action`.
- Use existing Conversation and AI Task entities.
- Repair and test the local Ollama path for private reasoning while retaining cloud-model options.

### Phase 6: Limited safe autonomy

Status: Planned

- Enable only high-confidence, reversible actions.
- Execute approved Home Assistant scripts and scenes rather than arbitrary AI-generated service calls.
- Apply deterministic safety conditions, cooldowns, action limits, audit logging, and undo.
- Keep AI actions independently disabled until the observation and recommendation phases meet their success thresholds.

## First pilot: Evening Context

The first routine-learning pilot will combine presence, room motion, time, lighting, climate, and media activity.

It will learn:

- When evening relaxation usually begins.
- Which room is occupied.
- Whether the TV, Genie, or Apple TV is normally selected.
- Normal Denon input and volume patterns.
- Preferred lighting and temperature.
- The transition toward bedtime.
- Manual changes that indicate a recommendation was wrong.

During the observation period it will only show the inferred context and offer an optional Prepare Evening action. It will not act automatically.

### Initial live signal shortlist

Verified on 2026-07-16. This list is provisional and will be narrowed after history and reliability checks.

Presence and household state:

- `person.randy`
- `person.kim`
- `person.alex`
- `input_boolean.bed_time`
- `input_boolean.party_mode`
- `binary_sensor.presence_sensor_fp2_e8ce_presence_sensor_1` — family-room presence.
- `binary_sensor.presence_1_presence_2` — foyer presence.
- `binary_sensor.presence_sensor_fp2_e8ce_presence_sensor_2` — kitchen presence.

Family-room environment and comfort:

- `sensor.family_room_temperature`
- `sensor.family_room_humidity`
- `climate.family_room`

Family-room media:

- `media_player.lg_webos_smart_tv` — LG TV; exposes the active input and input list.
- `media_player.family_room` — Denon Receiver Family Room; exposes receiver source, volume, mute, and source list.
- `media_player.genie` — DirecTV Genie; exposes playing title, episode/channel, and source.
- `media_player.apple_tv_family_room` — Apple TV Family Room.

Family-room lighting:

- `light.family_room_lamp`
- `light.family_room_lights`
- `light.switchlinc_dimmer_31_5e_c4` — FR Cans.

Unavailable duplicate and legacy entities are excluded from the initial pilot until their ownership and reliability are verified.

## Success criteria

- Context classification is correct at least 80 percent of the time after the learning period.
- Fewer than five incorrect recommendations per week.
- At least 60 percent of mature suggestions are accepted or adjusted rather than dismissed.
- No unexplained device actions.
- All eligible actions are reversible and logged.
- Safety-sensitive domains receive no autonomous AI control.

## Current live baseline

Checked 2026-07-16:

- Home Assistant Core 2026.7.2 on Home Assistant OS 18.1.
- Recorder uses SQLite and is approximately 1.44 GiB.
- Detailed history currently spans about 10 to 11 days.
- Ten Conversation entities and five AI Task entities are available.
- Local Ollama Conversation and AI Task entities exist but are currently unavailable.
- Whisper, Piper, openWakeWord, Node-RED, Music Assistant, and Home Assistant MCP Server are installed.

## Working principles

- Inspect live Home Assistant state before every implementation slice.
- Prefer native helpers and validated Home Assistant APIs.
- Make narrow changes and read them back after creation.
- Validate configuration after changes that affect automations, scripts, dashboards, or YAML.
- Finish and verify one phase before expanding the scope.
- Update this document as decisions, entity IDs, and results become known.

## Phase 1 review - 2026-08-20

Reviewed Newark live observer state, recorder history since the 2026-08-13 review, a recent detailed observer trace, person/tracker freshness, and a fresh `config_check`.

- Current live observer health is good: `input_boolean.ai_context_enabled=on`, `input_boolean.ai_actions_enabled=off`, `automation.home_context_evening_observer.last_triggered=2026-08-20 09:05 EDT`, `sensor.home_context_observer_age=4 min`, and `binary_sensor.home_context_engine_stalled=off`.
- Current live classification at review time was `home_context_mode=Waking`, `home_current_activity=Daily Life`, `confidence=78`, and `home_context_summary='Morning window with sleep signal off; activity in: unknown.'`
- A detailed trace from 2026-08-20 08:57 EDT confirms the observer deliberately chose the `Waking` branch because the time window matched and `binary_sensor.residents_home=on`, even though `binary_sensor.home_room_presence=off`, `binary_sensor.office_occupied=off`, and `sensor.home_active_room=unknown`. That is a likely over-broad or stale `Waking` classification, not a recorder gap.
- Recorder history since 2026-08-13 now includes all requested top-level modes: `Waking`, `Active`, `Relaxing`, `Entertaining`, `Sleeping`, and `Away`. The branches are reachable; the remaining question is stability and evidence quality.
- `Sleeping` still appears nightly and `Relaxing` appears repeatedly in the afternoon/evening windows, which is consistent with normal observation coverage rather than a disabled observer.
- `Entertaining` was finally observed on 2026-08-18 at 09:31 EDT and 09:36 EDT. Those transitions were legitimate branch executions driven by brief manual helper changes: `input_boolean.party_mode=on` at 09:31 and `input_boolean.home_context_guest_mode=on` at 09:36, both while both residents were home and room presence was on. This proves the branch works, but it does not yet prove reliable organic entertaining detection.
- `Away` has at least one recorder-backed valid transition in the current review window. On 2026-08-14, `binary_sensor.home_room_presence` went `off` at 11:58:57 EDT, `binary_sensor.recent_arrival` went `off` at 11:58:00 EDT, `person.kim` left `home` for `Londondale` at 12:00:10 EDT, `binary_sensor.residents_home` turned `off` at 12:00:10 EDT, and `home_context_mode` switched `Active -> Away` at 12:00:10 EDT before returning to `Active` at 12:07:18 EDT when room presence and recent-arrival evidence came back. That is a real, internally consistent `Away` classification.
- `Away` is still not stable enough to call validated against flapping. On 2026-08-15 from 16:51 to 17:15 EDT, recorder shows repeated `Unknown -> Away -> Active -> Unknown -> Away` cycling while `binary_sensor.home_room_presence` toggled, `binary_sensor.recent_arrival` toggled, and both person entities were still sourced from the wrong trackers. Those oscillations are conflicting evidence, not a clean success case.
- Source validation is still failing the user's required check. `person.randy` currently resolves from `device_tracker.rc_iphone`, not `device_tracker.iot2`, and `person.kim` resolves from `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, not `device_tracker.kim_iphone_12`. Direct lookup for `device_tracker.kim_iphone_12` still returns `ENTITY_NOT_FOUND`.
- Current freshness also favors the wrong trackers. At review time, `person.randy` last reported at 08:08 EDT while `device_tracker.iot2` had not reported since 02:01 EDT and `device_tracker.rc_iphone` had reported at 09:01 EDT. `person.kim` last reported at 08:55 EDT and its active source tracker reported at 08:55 EDT, while the requested `device_tracker.kim_iphone_12` remains missing. Because the authoritative source requirement is broken, arrival/departure freshness on the intended trackers still cannot be verified.
- Recorder history for `person.randy` still contains transient `source=person.randy` self-source records and `unknown` gaps around restarts and tracker handoffs. That is another reason not to treat current `home` states as proof against Away flapping.
- Verified rule changes this run: none. The observer remains observation-only.
- Validation result this run: `ha_get_system_health(include="config_check")` returned `valid` on 2026-08-20.

Next review target: 2026-08-23, or sooner after the person-to-tracker mappings are corrected and at least one real departure/return pair is recorded for the intended authoritative trackers.

Safe next steps:

- Keep `input_boolean.ai_actions_enabled` off.
- Leave observation enabled so the recorder can collect more real transitions.
- Fix or explicitly re-baseline the authoritative person mappings (`person.randy -> device_tracker.iot2`, `person.kim -> device_tracker.kim_iphone_12` or a confirmed replacement) before using presence history as authoritative evidence.
- After the mapping issue is resolved, wait for a real departure/return pair and then re-check `Away` for flapping rather than inferring from cached `home` snapshots.

## Phase 1 review - 2026-08-27

Reviewed Newark live observer state, current observer config, current context helpers, current person/tracker source attributes, and the current supporting presence signals on 2026-08-27.

- Current live observer health remains good: `input_boolean.ai_context_enabled=on`, `input_boolean.ai_actions_enabled=off`, `automation.home_context_evening_observer` is enabled in `restart` mode, `automation.home_context_evening_observer.last_triggered=2026-08-27 09:00 EDT`, `sensor.home_context_observer_age=3 min`, and `binary_sensor.home_context_engine_stalled=off`.
- Current live classification at review time is internally consistent with the configured `Away` branch: `input_select.home_context_mode=Away`, `input_select.home_current_activity=Away`, `input_number.home_context_confidence=85`, `input_text.home_context_summary='No tracked residents or room presence detected; household classified as away.'`, and `input_text.home_next_likely_activity='Returning Home'`.
- The supporting live evidence also lines up with that current `Away` snapshot: `binary_sensor.residents_home=off`, `binary_sensor.recent_arrival=off`, `binary_sensor.home_room_presence=off`, and `sensor.home_active_room=unknown`. This is a valid point-in-time `Away` classification, but it is still only a snapshot until recorder-backed transition history is re-checked.
- The observer logic itself is unchanged from the 2026-08-20 review. The configured branches still cover `Sleeping`, `Entertaining`, `Away`, `Active`/`Working`, `Active`/`Cooking`, `Relaxing`/`Watching TV`, `Relaxing`/`Listening to Music`, `Waking`, `Active`/`Daily Life`, and `Unknown`. No live rules were changed in this run.
- The requested authoritative tracker validation is still failing. `person.randy` is currently sourced only from `device_tracker.rc_iphone`, not `device_tracker.iot2`, and `person.kim` is currently sourced only from `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, not `device_tracker.kim_iphone_12`.
- The requested Kim tracker is still absent in the live Newark instance. Direct lookup for `device_tracker.kim_iphone_12` again returned `ENTITY_NOT_FOUND`, so the intended Kim source cannot be validated or used for a fresh arrival/departure audit in the current system state.
- Current freshness still favors the wrong trackers rather than the required ones. At review time, `device_tracker.iot2` had refreshed at 09:02:55 EDT, but `person.randy` still resolved from `device_tracker.rc_iphone`, which refreshed slightly later at 09:03:01 EDT. `person.kim` last reported at 08:55:36 EDT from `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, while the required `device_tracker.kim_iphone_12` does not exist to compare against.
- Because the authoritative mappings remain broken, this run could not verify the user's required arrival/departure condition that both intended source trackers update freshly when a resident leaves or returns. Current `not_home` states are not acceptable substitutes for that proof.
- This run did not produce a fresh recorder-backed transition audit for `Waking`, `Active`, `Relaxing`, `Entertaining`, `Sleeping`, and `Away`. The current thread exposed live state/config reads cleanly, but the deeper history/config-check read surface was not directly available here, so there is not enough new evidence yet to advance the transition-validation status beyond the 2026-08-20 findings.
- Verified rule changes this run: none. Validation result this run: live observer/config read-back succeeded, `input_boolean.ai_actions_enabled` remains `off`, and no Home Assistant writes were performed. A fresh `config_check` was not re-verified in this run.

Next review target: 2026-08-30, or sooner after the person-source mappings are corrected or explicitly re-baselined and a real departure/return pair is visible from the intended authoritative trackers.

Safe next steps:

- Keep `input_boolean.ai_actions_enabled` off.
- Do not treat the current `Away` snapshot or cached `home` history as proof that Away flapping is resolved.
- Repair or explicitly re-baseline `person.randy` and `person.kim` to the intended authoritative trackers before using presence history as decision-grade evidence.
- After the mapping issue is resolved, capture one real departure and one real return for each resident and then re-review `Away`, `Waking`, and overnight `Sleeping -> Active -> Sleeping` churn with recorder-backed history.

## Phase 1 review - 2026-09-03

Reviewed Newark live observer state, current observer config, current context helpers, current supporting presence signals, and current person/tracker source attributes on 2026-09-03.

- Current live observer health remains good: `input_boolean.ai_context_enabled=on`, `input_boolean.ai_actions_enabled=off`, `automation.home_context_evening_observer` is enabled in `restart` mode, `automation.home_context_evening_observer.last_reported=2026-09-03 09:00 EDT`, `sensor.home_context_observer_age=1-2 min`, and `binary_sensor.home_context_engine_stalled=off`.
- Current live classification at review time is internally consistent with the configured `Away` branch: `input_select.home_context_mode=Away`, `input_select.home_current_activity=Away`, `input_number.home_context_confidence=85`, `input_text.home_context_summary='No tracked residents or room presence detected; household classified as away.'`, and `input_text.home_next_likely_activity='Returning Home'`.
- The supporting live evidence also lines up with that current `Away` snapshot: `binary_sensor.residents_home=off`, `binary_sensor.recent_arrival=off`, `binary_sensor.home_room_presence=off`, and `sensor.home_active_room=unknown`. `home_room_presence` last changed to `off` at 2026-09-03 04:11 EDT, and `home_context_mode` changed to `Away` at 2026-09-03 04:15 EDT, which is at least directionally consistent with the configured 45-second hold on the Away branch.
- The observer logic is unchanged from the 2026-08-27 review. The configured branches still cover `Sleeping`, `Entertaining`, `Away`, `Active`/`Working`, `Active`/`Cooking`, `Relaxing`/`Watching TV`, `Relaxing`/`Listening to Music`, `Waking`, `Active`/`Daily Life`, and `Unknown`. No live rules were changed in this run.
- The requested authoritative tracker validation is still failing on 2026-09-03. `person.randy` is currently sourced from `device_tracker.rc_iphone`, not `device_tracker.iot2`, and `person.kim` is currently sourced from `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, not `device_tracker.kim_iphone_12`.
- The intended Randy tracker is present and fresh, but it is still not authoritative in the current person mapping. At review time, `device_tracker.iot2` reported `not_home` at 2026-09-03 08:47:07 EDT, while `person.randy` still resolved from `device_tracker.rc_iphone`, which reported slightly later at 08:47:11 EDT.
- The intended Kim tracker is still absent in the live Newark instance. Direct lookup for `device_tracker.kim_iphone_12` again returned `ENTITY_NOT_FOUND`, so the intended Kim source cannot be compared for freshness or used for a real arrival/departure validation in the current system state.
- Kim's current live state is also stale relative to Randy's. `person.kim` last reported `not_home` at 2026-09-03 02:02:25 EDT from `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, whose own last report was 2026-09-03 02:02:32 EDT. That is enough to explain the current snapshot, but not enough to validate an actual departure/return pair on the intended tracker.
- This run did not complete a fresh recorder-backed transition audit across `Waking`, `Active`, `Relaxing`, `Entertaining`, `Sleeping`, and `Away`. The live read surface and current config read-back were available, but the deeper recorder-history evidence needed for a full mode-by-mode transition review was not completed in this run. Treat this as continued observation rather than a closure of the Phase 1 accuracy audit.
- Verified rule changes this run: none. Validation result this run: live observer/config read-back succeeded, `input_boolean.ai_actions_enabled` remains `off`, and no Home Assistant writes were performed. A fresh `config_check` was not re-verified in this run.

Next review target: 2026-09-06, or sooner after the person-source mappings are corrected or explicitly re-baselined and a real departure/return pair is visible from the intended authoritative trackers.

Safe next steps:

- Keep `input_boolean.ai_actions_enabled` off.
- Do not treat the current `Away` snapshot as proof that Away flapping is resolved without fresh recorder-backed transition history.
- Repair or explicitly re-baseline `person.randy` and `person.kim` to the intended authoritative trackers before using presence history as decision-grade evidence.
- After the mapping issue is resolved, capture one real departure and one real return for each resident and then re-review `Away`, `Waking`, `Relaxing`, and overnight churn with recorder-backed history.

## Phase 1 review - 2026-09-10

Reviewed Newark at approximately 11:01–11:06 EDT. Recorder window: **September 3 09:00:40 through September 10 11:00 EDT**. Retrieved all 235 mode records (`has_more=false`), supporting gate/sleep/media/person histories, focused presence/activity history from September 9 17:00, and full-attribute departure records. Counts below are returned records, not accuracy scores; Away includes the initial boundary state. Boundary timestamps are not fresh device reports. The live bulk read was partial because two Kim trackers were missing; each successful entity record was assessed individually.

### Observer and safety validation

- Observer enabled in `restart` mode, last triggered 11:01:31 EDT, age helper 0 minutes, stalled off. Observation gate on and AI actions off; retrieved week-long gate histories contain only on and off respectively.
- Current classification: Active / Daily Life, confidence 60, room presence and recent arrival on, residents home off. The 11:02:16 trace (`2bca7024ac690d23a603dd4273a29ae6`) completed successfully, selected normal activity from room presence, and rejected Away because recent arrival was on. Its actions wrote only context helpers.
- Recorder's current run began at 02:01:28 EDT. Helper startup timestamps do not prove fresh physical events; the later trace independently verifies observer execution.
- Fresh configuration validation: **valid**, `is_valid=true`, no errors. Observer config hash: `d47cc3075f7596c9`. Verified rule changes this run: **none**. This review performed no live HA writes or restarts.

### Mode coverage

| Mode | Records | Verified evidence and limits |
| --- | ---: | --- |
| Waking | 17 | September 10 Sleeping → Waking at 07:30:12 follows sleep-signal off within milliseconds, with room and resident presence on. Repeated returns from Active at 08:55, 09:28, 09:41, and 09:51 are morning fallback classifications, not evidence of repeated waking. The rule requires no recent sleep transition. These sampled returns had room presence; this run does not reproduce the earlier empty-room false-positive case. |
| Active | 87 | Includes room-supported activity and short excursions during Away churn. Morning activity alternates Working / Daily Life; the current trace verifies room-supported Daily Life. Physical occupancy is not independently confirmed. |
| Relaxing | 5 | September 9 at 19:08:07 follows TV-on within milliseconds with room/resident presence on; TV-off at 23:37:34 corresponds to Active. At 18:13:16 Watching TV returns with room presence while residents home is off: consistent with the rule but conflicting presence evidence. |
| Entertaining | 0 | Party and guest-mode histories stayed off. No eligible transition demonstrated; absence is not evidence of a missed branch. |
| Sleeping | 3 | Three sleep-signal on edges recorded. Latest Sleeping entry at September 10 00:06:22 follows the authoritative signal within milliseconds and persists until 07:30:12 without intermediate mode churn. Room presence was off at entry: the sleep helper supports classification but does not prove bedroom occupancy. |
| Away | 58 | Repeated Away → Active → Unknown → Away cycling persists. These are classifier transitions, not verified household departures. |
| Unknown | 65 | Frequently follows room-presence clearing before Away's duration condition can pass. |

Representative churn on **September 9**: room presence off at 18:27:14 produced Unknown; Away followed at 18:30. Room presence on at 18:36:29 produced Active; off at 18:37:38 produced Unknown; Away followed at 18:40; room presence on at 18:49:33 produced Active. Residents home stayed off throughout and recent arrival had been off since 18:01. This verifies sensor-driven classifier churn, but does not establish false-positive room detections versus an untracked person being present.

A **missed evaluation opportunity** occurred September 10: residents home was off from 10:37:30, recent arrival off from 10:43, and room presence off from 10:51:09 until 10:54:54. The mode became Unknown, but never Away in that interval. Away's 45-second condition could pass around 10:51:54; current config has a duration condition inside its branch rather than an expiry trigger, and the next periodic refresh was 10:55. This explains a timing gap, not a verified physical departure missed by the system. An expiry-trigger change remains a proposal pending reliable presence evidence.

### Authoritative sources and freshness

Both required **only-source** checks fail:

- `person.randy` lists **two** configured trackers: `device_tracker.rc_iphone` and `device_tracker.randys_macbook_pro`; active source is `device_tracker.rc_iphone`. It is not configured only from `device_tracker.iot2`.
- `person.kim` lists `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, has no current source attribute, and is **unknown**. Both that configured tracker and required `device_tracker.kim_iphone_12` return `ENTITY_NOT_FOUND`. This is deterioration from the previous review's stale but available configured source. Kim's recorded state became unknown September 9 at 02:02:39, with no subsequent known state in the window.
- Live last-reported timestamps (September 10 EDT): Randy person **10:56:20.290876**; active `rc_iphone` **10:56:20.290815**; intended `iot2` **10:56:17.318724**, about three seconds earlier. Kim person **02:03:10.261543**, about nine hours earlier; neither missing Kim tracker has a current timestamp.
- Full-attribute departure history: `iot2` left home September 10 at **10:37:20.950251**, `rc_iphone` at **10:37:30.295026**, and Randy person at **10:37:30.295092**, retaining source `rc_iphone`. Both Randy trackers produced contemporaneous changed records about 9.3 seconds apart. This does **not** satisfy freshness for both residents' required trackers: Kim stayed unknown and her required tracker had no records. Historical results expose changed/updated timestamps, not `last_reported`; these establish fresh changed records only.
- Randy's September 9 return was also recorded: person home at 19:03:55, intended `iot2` home at 19:05:05, about 70 seconds later. This does not resolve Kim's evidence gap or prove a household arrival.

Cached home states, synthetic history-boundary timestamps, and current Away/Active snapshots are not proof against flapping. No accuracy percentage or Phase 1 completion is justified without reliable resident sources and real-event confirmation.

**Next review target: 2026-09-17**, aligned with the weekly review, or sooner after mappings and Kim's missing source are resolved and a genuine departure/return pair is available. Continue observation with AI actions off. First restore/confirm the required authoritative sources, then capture fresh events for both residents and review Away timing/churn and repeated Waking fallback. No live rule changes are justified yet.

## Presence source repair - 2026-09-10

Responded to a live report that Kim was home while Home Context showed her unavailable.

- Root cause confirmed: `person.kim` referenced the deleted entity `device_tracker.kim_iphone_pro_max_kim_iphone_pro_max_kim_iphone_pro_max`, while the required canonical entity `device_tracker.kim_iphone_12` was absent.
- Identity check confirmed the live replacement was Kim's Apple iPhone 16 Pro Max (`device_tracker.kim_iphone_3`, friendly name `Kim iphone`), not the separate iCloud3 iPhone 17,2 entity that was unavailable. The replacement reported `home`, GPS source, online status, and 95% battery.
- Verified rule change: renamed the live Kim phone entity from `device_tracker.kim_iphone_3` to `device_tracker.kim_iphone_12`, then updated `person.kim` to use only that tracker. No Home Context observer rule was changed.
- Validation: `person.kim=home`, source is exactly `device_tracker.kim_iphone_12`, the tracker is `home` with matching coordinates, and `sensor.residents_present` now reports `Randy, Kim`. Both tracker and person last reported at approximately 15:13 EDT, so this is a fresh in-place update, not cached `home` evidence.
- Safety: `input_boolean.ai_actions_enabled=off`. The Home Context dashboard has no reference to the old live ID. The broad automation scan remained incomplete because Newark timed out on most automation configs; templated references and YAML-defined scripts remain a follow-up check.
- Remaining source issue: `person.randy` still lists `device_tracker.rc_iphone` and `device_tracker.randys_macbook_pro`, not only the required `device_tracker.iot2`. Do not claim the two-resident source contract is complete until Randy is corrected and both residents have fresh departure/return evidence.

Next review target: 2026-09-17, or sooner after a real departure/return pair is recorded. Keep AI actions off, verify the old Kim ID stays absent from consumers, and continue treating cached `home` states as insufficient evidence against Away flapping.

## Randy presence source repair - 2026-09-10

- Verified and corrected `person.randy`, which had been configured with `device_tracker.rc_iphone` and `device_tracker.randys_macbook_pro`.
- Updated the person helper to use only the required authoritative source, `device_tracker.iot2`. No entity rename, dashboard change, or observer-rule change was made.
- Validation: `person.randy=home`, source is exactly `device_tracker.iot2`, and both report the same GPS coordinates. `device_tracker.iot2` last reported at 15:16 EDT; `person.randy` refreshed at 15:18 EDT after the helper update. `sensor.residents_present` remains `Randy, Kim`.
- Safety: `input_boolean.ai_actions_enabled=off`. The broad automation consumer scan remains incomplete because Newark timed out while reading most automation configurations; this is a follow-up limitation, not a failure of the person-helper update.

Next review target: 2026-09-17, or sooner after a real departure/return pair for both residents. Keep AI actions off and validate Away behavior from fresh tracker events rather than cached states.
