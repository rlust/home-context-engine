import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Preview, demoSnapshot, blockers, TARGET, BRIGHTNESS} from './model.mjs';

const now = 1_000_000;
test('fixed scope and 11 percent; approval is at most once', () => {
  const s = demoSnapshot(now), p = new Preview(s, now);
  assert.equal(TARGET, 'light.family_room_lamp');
  assert.equal(BRIGHTNESS, 11);
  assert.deepEqual(blockers(s, now), []);
  assert.equal(p.approve(s, now), true);
  assert.equal(p.approve(s, now), false);
});
for (const [label, change] of Object.entries({
  vacancy: s => s.occupied = 'off',
  dwell: s => s.occupiedSince = now - 119_999,
  futureDwell: s => s.occupiedSince = now + 1,
  missingTV: s => s.tv = 'unavailable',
  stale: s => s.observedAt = now - 120_000,
  future: s => s.observedAt = now + 1,
  observer: s => s.observerAgeMinutes = NaN,
  oldObserver: s => s.observerAgeMinutes = 10,
  diagnostics: s => s.diagnosticsUntil = now,
  missingDiagnostics: s => delete s.diagnosticsUntil,
  resident: s => s.residents = 'unknown',
  sleep: s => s.sleep = 'on',
  guest: s => s.guest = 'unknown',
  party: s => s.party = 'on',
  gate: s => s.aiActions = 'on',
  context: s => s.contextEnabled = 'off',
  otherActivity: s => s.activity = 'Cooking',
  off: s => s.lamp.state = 'off',
  missingLight: s => s.lamp.state = 'unavailable',
  group: s => s.lamp.entity = 'light.family_room',
  wrongArea: s => s.lamp.area = 'Loft',
  invalidBrightness: s => s.lamp.brightness = undefined,
  session: s => s.session = '',
})) {
  test(`rejects ${label} before and after proposal`, () => {
    const s = demoSnapshot(now), p = new Preview(s, now);
    change(s);
    assert.notEqual(new Preview(s, now).status, 'pending');
    assert.equal(p.approve(s, now), false);
    assert.equal(p.approve(demoSnapshot(now), now), false);
  });
}
test('manual brightness/color or session changes cancel pending approval', () => {
  for (const change of [s => s.lamp.brightness++, s => s.lamp.colorRevision = 'changed', s => s.session = 'new']) {
    const s = demoSnapshot(now), p = new Preview(s, now);
    change(s);
    assert.equal(p.approve(s, now + 1), false);
    assert.equal(p.status, 'cancelled');
  }
});
test('expiration boundary and clock rollback reject approval', () => {
  for (const time of [now + 120_000, now - 1]) {
    const s = demoSnapshot(now), p = new Preview(s, now);
    s.observedAt = time;
    assert.equal(p.approve(s, time), false);
    assert.equal(p.status, 'expired');
  }
});
test('reload reconstructs pending preview, never a durable device approval', () => {
  const s = demoSnapshot(now), p = new Preview(s, now);
  p.approve(s, now);
  assert.equal(new Preview(s, now).status, 'pending');
});
test('UI and model contain no network, storage or device-service interface', () => {
  for (const name of ['model.mjs', 'ui.mjs']) {
    const source = readFileSync(new URL(name, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|WebSocket|callService|callWS|localStorage|sessionStorage/);
  }
});
