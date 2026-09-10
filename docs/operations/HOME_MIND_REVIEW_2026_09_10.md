# Home Mind code review and selective adoption

## Sources and scope

Reviewed Home Mind at commit `28ceb1f9449beb36e53ce5907116ae5e3b480654`, particularly
[topology-scanner.ts](https://github.com/hoornet/home-mind/blob/28ceb1f9449beb36e53ce5907116ae5e3b480654/src/home-mind-server/src/ha/topology-scanner.ts),
its tests, device-scanner.ts, fact-patterns.ts, and forget-confirmations.ts.
This was a targeted architectural review, not an upstream security audit.

Local engine base: `4b6c149`. Fetched origin/main at `a3ade56`; intervening
changes are documentation only. Pre-existing dashboard and PLAN edits preserved.

## Adopted independently

- Request-scoped room/floor context for the combined Assist agent. Native HA
  registries replace remote template scans; entity area overrides device area.
- Only explicitly Assist-exposed, enabled, visible, uncategorized entities are
  included. Empty exposure never falls back to exposing the whole inventory.
- Exact token-sequence matches on entity names/aliases, area names, and floor
  names select records. Unassigned locations remain unassigned. No inferred
  occupancy or device state is attached to registry membership.
- Deterministic limits: at most five records and 650 serialized characters;
  the full context brief remains at most 1,400 characters. Whole records are
  omitted rather than cut. The safety policy has reserved space and survives
  overflow. Audit categories reflect retained content.

This is fresh structural context, not new activity detection or automatic
room renaming. It does not change trackers, person mappings, services, or gates.

## Not adopted

- Another feedback ledger: the engine already has revisions, deduplication,
  episode association and scoring gates. Extend these instead of duplicating them.
- Thirty-minute cached topology/state as current truth, fail-open exposure,
  or an unbounded full-house prompt.
- Broad regex-based memory deletion or heuristic light color-mode defaults.
- Autonomous actions. Observation and the independent AI-actions gate remain
  the deployment policy; no live gate state was checked or changed in this work.

## Validation and deployment

- `python3 -m pytest tests mac_mini/tests -q`: 125 passed. The first sandboxed
  analytics run had 11 localhost socket permission failures; the permitted rerun
  passed. `git diff --check` passed.
- Integration tests cover area precedence, device fallback, floor matching,
  explicit exposure, hidden/disabled/diagnostic exclusion, aliases, unrelated
  queries, deterministic size limits, and safety-policy preservation.
- Initially validated locally; deployment status is updated below.
- Conservative limitation: default-exposed entities without a stored explicit
  conversation exposure option are omitted. Area aliases are not matched yet.
- Next gate: review diff, back up installed integration, deploy through the
  established process, then obtain restart approval if needed. Verify an exposed
  Office light and an unexposed device through Assist, and confirm actions remain
  off. Do not claim room-context accuracy until that live validation passes.

## Newark installation, 2026-09-10

- Target verified: Newark `192.168.1.4`, Home Assistant Core `2026.9.1`.
- Installed baseline matched local HEAD
  `4b6c149582e9b9a0936815a954e7008a97cc9803` for both replaced files.
- Backup: `/config/codex_backups/home-context-memory-20260910-topology/original`.
  All original Python file hashes verified before copying.
- Copied only `context_brief.py`, `conversation.py`, and new `topology.py` into
  `/config/custom_components/home_context_memory/`; deployed content is an
  uncommitted patch over that HEAD, not a new release commit.
- Read-back SHA-256 hashes matched local files:
  - context_brief.py: `8a85d9d61c70e5647c1b1e980d663eea9a2a5e77eda1934e900948eb5be56fbb`
  - conversation.py: `b787628c19f153896e8c0c9658e56b99eb5eb3ee6c4384ac518b640fb18c4d20`
  - topology.py: `71a4226b41eda4e17f59dfc42fc3b8196b295b58b867316ee7acbae9eefb2dd8`
- AI actions verified `off` before and after copying. No services or gates changed.
- `ha core check` completed successfully after installation. This is a config
  validation gate, not proof of the new module's live conversation behavior.
- Restart explicitly approved and initiated on 2026-09-10. After startup's
  temporary 502 responses cleared, the integration reported `loaded` and
  `input_boolean.ai_actions_enabled` was verified `off` (post-restart timestamp
  17:30:05 America/New_York).
- Combined agent entity discovered:
  `conversation.home_context_memory_memory_chatgpt_control`.
- End-to-end Assist verification remains blocked: the approval reviewer rejected
  the proposed read-only Office question because the combined agent can transmit
  private room/entity topology to an external AI provider. No workaround or
  indirect execution attempted. Obtain explicit user consent for this data
  transmission before retrying. Loaded status alone does not verify topology
  selection or the downstream answer.

## Authorized verification and compatibility correction

- User explicitly authorized ongoing read-only Home Context verification through
  the configured ChatGPT provider, including relevant room/entity details
  ("yes always do that"). Scope excludes device actions, other providers, and
  automatic HA restarts.
- Authorized retry reached the combined agent but returned HTTP 500. Logs show
  `ComputedNameType` has no `casefold` in topology selection. The local mocks had
  only string names and did not cover HA's computed-name sentinel.
- Corrected name handling to fall back to a textual original name or entity ID;
  non-text aliases are ignored. Replaced deprecated device mapping lookup with
  registry `async_get` (also used for area/floor lookup).
- Regression suite: 126 passed. Corrected topology.py installed and its SHA-256
  verified: `5ca7ec1e364bc9070310112dae9fa502ff3e4663dced4aac22c2baa0150c1546`.
  The previous topology hash above describes the first deployment only.
- Correction requires a fresh approved restart. End-to-end answer verification
  remains incomplete; do not report the HTTP 500 as a successful test.

## Second post-restart verification

- User performed restart. Integration loaded; AI actions remained off with
  post-restart timestamp 2026-09-10 17:36:52 America/New_York.
- Assist retry failed before delegation: `AreaRegistry` has no `async_get`.
  The previous correction incorrectly generalized the device registry API.
- Verified exact Core 2026.9.1 source:
  [area lookup](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/helpers/area_registry.py)
  uses `async_get_area`; [floor lookup](https://github.com/home-assistant/core/blob/2026.9.1/homeassistant/helpers/floor_registry.py)
  uses `async_get_floor`. Corrected both and added an adapter-level regression
  test that supplies only these supported methods, including a computed name.
- 127 tests passed. Corrected topology installed; local and remote SHA-256 match:
  `430d9fe1f71e483776f63aca01afd95fa6bf09ed91643d52ce8e9f5062209bfc`.
- Activation needs another approved/user-performed restart. End-to-end testing
  is still incomplete. Earlier unit tests did not cover the registry adapter;
  do not treat their passing result as live compatibility proof.
- Scoped rollback: restore the two replaced files from the backup, remove only
  the newly installed `topology.py`, then obtain approval for a restart to load
  the restored code. Do not restore unrelated HA configuration or memory stores.

## Successful activation and smoke test

- Final restart explicitly approved and completed on 2026-09-10. Integration
  reports `loaded`; AI actions remain `off` with post-restart timestamp
  17:44:34 America/New_York, and were checked again after the test.
- Combined Assist agent successfully answered the read-only Office registry
  question. It returned five records and identified Office as `1st Floor`.
  Conversation ID: `01M26MJD9SS8PZAS2M2D628W8Z`.
- Tool response reported no targets and empty successful/failed service-call
  lists. Its response_type was `action_done`, so that label alone must not be
  interpreted as evidence of a device action.
- Independently verified through HA template location functions that both
  `light.office` and `media_player.kitchen` resolve to Office and Office resolves
  to `1st Floor`. Exposure checks confirm both entities are Assist-exposed.
- The Kitchen-named media player is therefore an existing naming/location
  inconsistency, not an invented assignment in the answer. Left unchanged
  pending clarification of its intended physical room.
- This completes the live happy-path smoke test, not a full privacy audit or
  activity/presence accuracy review. Hidden/unexposed filtering remains covered
  by local regression tests, not a separate live negative-case test.
