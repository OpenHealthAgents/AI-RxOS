import { scimSyncForOrganization } from './scim.js';
import { config } from './config.js';

let running = false;

export async function startScimWorker() {
  if (process.env.NODE_ENV === 'test') return;
  if (running) return;
  running = true;
  const intervalMs = config.scimSyncIntervalMinutes * 60 * 1000;
  // initial delay small to let DB come online
  setTimeout(() => runLoop(intervalMs), 5000);
}

async function runLoop(intervalMs: number) {
  while (running) {
    try {
      // Global scan: find orgs with scim.enabled and run sync for each
      await scimSyncForOrganization();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('SCIM worker iteration failed:', e);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export function stopScimWorker() {
  running = false;
}

export default { startScimWorker, stopScimWorker };
