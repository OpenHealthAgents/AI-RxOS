import { describe, it, expect } from 'vitest';
import { initDatabase } from './db.js';

describe('Database initialization', () => {
  it('can be invoked concurrently without schema race failures', async () => {
    await expect(Promise.all([
      initDatabase(),
      initDatabase(),
      initDatabase(),
    ])).resolves.toBeDefined();
  });
});
