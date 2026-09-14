// Offline rehearsal only. No Home Assistant client or device-service interface.
export const TARGET = 'light.family_room_lamp';
export const BRIGHTNESS = 11;
const MAX_AGE = 120_000;

export function blockers(s, now) {
  const reasons = [];
  const age = now - s?.observedAt;
  if (!Number.isFinite(age) || age < 0 || age >= MAX_AGE) reasons.push('Snapshot stale or missing');
  if (s?.aiActions !== 'off') reasons.push('AI Actions must be off');
  if (s?.contextEnabled !== 'on') reasons.push('Context disabled or unavailable');
  if (s?.activity !== 'Watching TV') reasons.push('Not Watching TV');
  if (s?.tv !== 'on') reasons.push('TV off or unavailable');
  if (s?.occupied !== 'on' || !Number.isFinite(s?.occupiedSince)
      || now - s.occupiedSince < MAX_AGE) reasons.push('Room presence needs two minutes');
  if (s?.residents !== 'on') reasons.push('Resident presence missing');
  for (const key of ['sleep', 'guest', 'party']) {
    if (s?.[key] !== 'off') reasons.push(`${key} guard not clear`);
  }
  if (!Number.isFinite(s?.observerAgeMinutes) || s.observerAgeMinutes < 0
      || s.observerAgeMinutes >= 10) reasons.push('Observer stale or unavailable');
  if (s?.diagnostics !== 'Healthy' || !Number.isFinite(s?.diagnosticsUntil)
      || now >= s.diagnosticsUntil) reasons.push('Diagnostics stale or unhealthy');
  if (s?.lamp?.entity !== TARGET || s?.lamp?.area !== 'Family Room') reasons.push('Target scope mismatch');
  if (s?.lamp?.state !== 'on') reasons.push('Lamp off or unavailable; leave unchanged');
  if (!Number.isInteger(s?.lamp?.brightness) || s.lamp.brightness < 0
      || s.lamp.brightness > 255) reasons.push('Lamp brightness unavailable');
  if (!s?.session) reasons.push('Session identity missing');
  return reasons;
}

function fingerprint(s) {
  return JSON.stringify([s?.session, s?.lamp?.entity, s?.lamp?.area,
    s?.lamp?.state, s?.lamp?.brightness, s?.lamp?.colorRevision]);
}

export class Preview {
  constructor(snapshot, now) {
    this.createdAt = now;
    this.expiresAt = now + MAX_AGE;
    this.identity = fingerprint(snapshot);
    this.status = blockers(snapshot, now).length ? 'blocked' : 'pending';
    this.reason = blockers(snapshot, now).join('; ');
  }

  check(snapshot, now) {
    if (this.status !== 'pending') return this.status;
    if (now < this.createdAt || now >= this.expiresAt) {
      this.status = 'expired';
      this.reason = 'The two-minute approval window ended';
    } else if (fingerprint(snapshot) !== this.identity) {
      this.status = 'cancelled';
      this.reason = 'Session or lamp changed; no reapplication';
    } else {
      const reasons = blockers(snapshot, now);
      if (reasons.length) {
        this.status = 'cancelled';
        this.reason = reasons.join('; ');
      }
    }
    return this.status;
  }

  approve(snapshot, now) {
    if (this.check(snapshot, now) !== 'pending') return false;
    this.status = 'preview-approved';
    this.reason = 'Rehearsal accepted once. No device changed; no feedback was submitted.';
    return true;
  }
}

export function demoSnapshot(now) {
  return {
    observedAt: now, aiActions: 'off', contextEnabled: 'on', activity: 'Watching TV',
    tv: 'on', occupied: 'on', occupiedSince: now - MAX_AGE, residents: 'on',
    sleep: 'off', guest: 'off', party: 'off', observerAgeMinutes: 0,
    diagnostics: 'Healthy', diagnosticsUntil: now + 600_000, session: 'synthetic-tv-session',
    lamp: {entity: TARGET, area: 'Family Room', state: 'on', brightness: 80, colorRevision: 'unchanged'},
  };
}
