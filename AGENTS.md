# Home Context Engine: agent working agreement

Applies to work in this repository. Follow higher-priority session instructions
and the user's current request. This file is project guidance, not permission
to enable devices or make unrelated changes.

## Start every session

1. Read README.md, docs/VISION_ROADMAP.md and the Current handoff section of
   docs/PLAN.md. Read the operation notes linked from the handoff when relevant.
2. Inspect git status and branch/remotes. Fetch origin when available before
   publishing; preserve other agents' and the user's edits. Never force-push,
   discard changes or invent Git attribution. Resolve conflicts explicitly.
3. Distinguish historical snapshots from current evidence. Refresh live state
   before acting on it; label unavailable tools, partial scans and stale metrics.
4. For a general "continue" request, advance the first unfinished roadmap
   milestone with a bounded implementation or investigation, not another
   restatement of the plan. Follow a more specific user request first.

## Purpose and safety

Optimize for fewer unnecessary interactions, fewer wrong actions and more trust.
Understand context, disclose uncertainty, validate improvements independently,
and preserve human control. More automations is not the success metric.

- Newark and Aspire are separate systems. Verify the target is Newark.
- Preserve input_boolean.ai_actions_enabled as an independent safety gate.
  Do not enable it based on roadmap approval or a "continue" request.
- Live device trials require exact target/settings approval and passed evidence
  gates. A synthetic browser approval is not a live authorization or scored review.
- Preserve authoritative person sources: person.randy uses device_tracker.iot2
  only; person.kim uses device_tracker.kim_iphone_12 only. Verify configuration
  and fresh source reports. Cached home states do not disprove Away flapping.
- Missing/stale/conflicting evidence must not grant action eligibility. Rule
  confidence, measured accuracy and suggestion acceptance are distinct metrics.
- Follow the existing advancement gates in VISION_ROADMAP.md. Do not lower
  thresholds or tune scores merely to pass them. Preserve old feedback provenance.
- Consult the applicable Home Assistant skills. Use managed APIs for live
  dashboard/config changes, fresh hashes, narrow transforms and readback.
  Never directly edit .storage. Back up before live mutation; obtain fresh
  explicit approval for a restart. Do not test by disrupting real sensors.
- Keep raw household events, GPS, credentials and private snapshots out of Git.
  Prefer dated, anonymized aggregate evidence in operation notes.

## Keep the shared plan moving

After substantive work, update docs/PLAN.md in the same change:

- Record the date, scope, outcome, files and evidence or operation-note link.
- Separate implementation, automated tests, backup, deployment, restart and
  live validation. Never describe an offline prototype as deployed.
- Replace Current handoff with the actual next unfinished task, its completion
  criteria and remaining blockers. Preserve historical findings below it.
- Update VISION_ROADMAP.md only when direction, milestones or agreed gates
  change; do not silently turn a suggestion into an approved requirement.
- Run relevant tests and git diff --check. Document failures and skipped checks.
  The preview tests run with node --test dashboard/tv-preview/model.test.mjs;
  Python tests use pytest where their dependencies are installed.
- When publishing is authorized, commit the related code, tests and plan
  together; push without force and verify the remote SHA. Record the commit in
  the session handoff response. Never claim unpublished edits are on GitHub.

Repository documentation is shared context only for sessions that can access
and read it. It does not automatically load into every ChatGPT conversation,
schedule background work, or grant unattended production access.
