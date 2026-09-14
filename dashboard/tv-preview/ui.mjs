import {Preview, demoSnapshot} from './model.mjs';

const approve = document.querySelector('#approve');
const status = document.querySelector('#status');
const expiry = document.querySelector('#expiry');
const scenario = document.querySelector('#scenario');
let snapshot;
let preview;

function render() {
  const now = Date.now();
  preview.check(snapshot, now);
  approve.disabled = preview.status !== 'pending';
  status.textContent = `${preview.status.replaceAll('-', ' ')}: ${preview.reason || 'Synthetic checks pass. Approval only rehearses the interaction.'}`;
  expiry.textContent = preview.status === 'pending'
    ? `Expires in ${Math.max(0, Math.ceil((preview.expiresAt - now) / 1000))} seconds`
    : 'No device changed';
}

function reset() {
  snapshot = demoSnapshot(Date.now());
  preview = new Preview(snapshot, Date.now());
  scenario.value = 'ready';
  render();
}

approve.addEventListener('click', () => { preview.approve(snapshot, Date.now()); render(); });
document.querySelector('#restart').addEventListener('click', reset);
scenario.addEventListener('change', () => {
  switch (scenario.value) {
    case 'vacant': snapshot.occupied = 'off'; break;
    case 'tv': snapshot.tv = 'unavailable'; break;
    case 'stale': snapshot.observedAt = Date.now() - 120_000; break;
    case 'off': snapshot.lamp.state = 'off'; break;
    case 'manual': snapshot.lamp.brightness = 100; break;
    case 'gate': snapshot.aiActions = 'on'; break;
  }
  // Returning to eligible cannot revive an invalidated approval.
  render();
});
reset();
setInterval(render, 1000);
