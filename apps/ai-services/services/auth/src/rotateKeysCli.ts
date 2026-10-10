#!/usr/bin/env node
import { rotateAllSecretsCli } from './crypto.js';

(async () => {
  try {
    await rotateAllSecretsCli(process.argv.slice(2));
    process.exit(0);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('rotate-cli-error', e);
    process.exit(2);
  }
})();
