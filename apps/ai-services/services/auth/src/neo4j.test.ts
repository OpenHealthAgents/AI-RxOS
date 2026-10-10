import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('./config.js', () => ({
  config: {
    neo4jUrl: 'bolt://localhost:7687',
    neo4jUser: 'neo4j',
    neo4jPassword: 'test',
    neo4jEncrypted: false,
    neo4jDatabase: 'neo4j',
    neo4jPoolSize: 10,
    neo4jMaxRetryTimeMs: 2000,
  },
}));

vi.mock('neo4j-driver', () => {
  const runMock = vi.fn();
  const closeMock = vi.fn();
  const sessionMock = vi.fn(() => ({
    run: runMock,
    close: closeMock,
    executeWrite: async (fn: any) => fn({ run: runMock }),
  }));
  return {
    auth: { basic: vi.fn(() => ({})), none: vi.fn(() => ({})) },
    driver: vi.fn(() => ({ session: sessionMock, close: closeMock })),
    session: { READ: 'READ', WRITE: 'WRITE' },
  };
});

const configModule = await import('./config.js');
const { isAllowedByNeo4j, seedPermission, initNeo4jSchema } = await import('./neo4j.js');

describe('Neo4j helper', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    configModule.config.neo4jUrl = 'bolt://localhost:7687';
  });

  it('returns allow when Neo4j is unavailable', async () => {
    const config = await import('./config.js');
    config.config.neo4jUrl = '';
    const res = await isAllowedByNeo4j('u1', 'r1', 'read', 't1');
    expect(res.allowed).toBe(true);
    expect(res.available).toBe(false);
  });

  it('initializes Neo4j schema', async () => {
    const res = await initNeo4jSchema();
    expect(res.ok).toBe(true);
  });

  it('seeds a permission graph entry', async () => {
    const res = await seedPermission('u1', 'r1', 'read', 't1');
    expect(res.ok).toBe(true);
  });
});
