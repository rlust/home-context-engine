# Watching TV audit follow-up - September 10, 2026

Decision: keep AI Actions off. No live rules, confidence scores, helpers,
devices or services were changed. This review supersedes the earlier claim
that 12 non-restored automation IDs and some script IDs could not be reconciled.

## Consumer inventory

Read the complete Newark automation/script YAML and compared its identifiers
with a fresh HA state inventory. Confirmed with PyYAML safe_load, streaming
the files directly from Newark without retaining the raw configuration:

| Inventory | File entries | Non-restored entities | Restored entities | Unmatched non-restored IDs |
| --- | ---: | ---: | ---: | ---: |
| Automations | 478 | 472 | 34 | 0 |
| Scripts | 229 | 228 | 2 | 0 |

File entries and entities need not be one-to-one; these counts do not prove
every file entry loaded successfully. Non-restored also does not mean enabled
or available. The earlier textual extractor counted only entries beginning
with `- id:` and omitted indented IDs; quoted numeric script keys also needed
normalization. The missing-ID concern was an audit-method error, now corrected.

Literal gate-reference scan found only the Observer description and the
Denon Music Lighting approval automation in automations.yaml, and none in
scripts.yaml. The Observer description is not an action consumer. The Denon
approval remains the one identified device-capable gate consumer, targeting
light.family_room_lights. Do not enable the global gate for a TV test.

Read all 41 distinct referenced automation blueprint paths. Forty exist and
contain no literal ai_actions_enabled reference. This referenced file is absent:

`HASwitchPlate/hasp_Display_Temperature_with_Icon_and_Colors.yaml`

Its four consumers (FR, Kitchen, Master and Front Door temperature-display
automations) all report unavailable. A trace query for the FR consumer returned
zero traces; no expanded configuration was recovered. These unrelated
automations were not repaired, enabled or removed.

Scope limitation: this is complete identifier reconciliation and bounded
on-disk literal-reference scanning, not proof against constructed entity IDs,
runtime/file divergence, external clients or other dynamic consumers. The
missing blueprint body cannot be inspected. No global action clearance follows.

## Calibration breakdown

Read-only SQLite query on the private Mac mini selected the latest feedback per
episode using occurred_at and source_event_id, excluded unsure/inconsistent
reviews and returned only aggregate values. Counts agree with the 23:00:19Z
report from this evening.

| Predicted activity | Scored | Confirmed | Mean confidence | Reviewed accuracy | Reviewed UTC days |
| --- | ---: | ---: | ---: | ---: | ---: |
| Away | 5 | 5 | 86.00% | 100.00% | 4 |
| Daily Life | 39 | 38 | 81.36% | 97.44% | 18 |
| Entertaining | 6 | 6 | 88.00% | 100.00% | 4 |
| Watching TV | 20 | 20 | 95.10% | 100.00% | 15 |
| Working | 19 | 19 | 88.00% | 100.00% | 9 |

The TV aggregate mean-confidence gap is 4.9 percentage points. This is NOT a
replacement for the report's confidence-bucket-weighted overall calibration
error of 12.3 points, which still fails the at-most-10-point gate. The larger
overall discrepancy is principally underconfidence in the reviewed samples,
not high observed TV false positives. These selectively reviewed samples do
not establish population accuracy or recall. Raising confidence values to fit
the same reviews would not be independent validation.

All 20 reviewed TV episodes have no stale/missing signal summary flags, occur
on 15 UTC dates, and share one recorded observer-version digest. Only one TV
review occurred after the latest restart cutoff (2026-09-10T21:44:00Z).
Distinct dates are not proof of independent viewing sessions. The exporter
contains a fixed config_sha256 value, and the normalizer hashes this supplied
metadata rather than querying live observer code. Therefore the shared digest
does not by itself prove historical/current rule equivalence. No digest or
historical record was rewritten.

## Next evidence gate

1. Verify the exporter's declared observer fingerprint against the deployed
   observer using a documented canonical representation; do not relabel old
   reviews as belonging to new rules.
2. Collect prospective session-based reviews covering TV start, TV stop,
   resident home in another room, room vacancy and stale/unavailable sources.
   Keep missed detections and false positives distinct from confirmations.
3. Investigate Daily Life calibration on separate training/evaluation periods;
   do not tune confidence solely to cross today's threshold.
4. Validate a server-side, single-target proposal's expiration, restart reset,
   manual override and circuit breaker without device calls before requesting
   an explicitly approved real lighting test. The browser rehearsal does not
   provide these production guarantees.

AI Actions was read again as off at the end of the audit. Next review target:
September 11, 2026, after fresh post-restart observations. No schedule or
restart was created. Local prototype remains undeployed to Home Assistant.
