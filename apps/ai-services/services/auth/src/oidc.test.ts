import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('./auth.js', () => ({ dbPool: { query: vi.fn() } }));
vi.mock('./logger.js', () => ({ logInfo: vi.fn(), logWarn: vi.fn() }));

const { createOidcProvider, listOidcProviders, getOidcProvider, refreshOidcProviderMetadata, sanitizeOidcProvider, updateOidcProvider, deleteOidcProvider } = await import('./oidc.js');
const { dbPool } = await import('./auth.js');

describe('OIDC provider helpers', () => {
  beforeEach(() => {
    (dbPool.query as any).mockReset();
  });

  it('creates a provider and stores it in organization settings', async () => {
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: {} }] })
      .mockResolvedValueOnce({});

    const provider = await createOidcProvider('org1', {
      name: 'Acme OIDC',
      issuer: 'https://example.com',
      clientId: 'abc',
      clientSecret: 'secret',
    });

    expect(provider.name).toBe('Acme OIDC');
    expect(provider.issuer).toBe('https://example.com');
    expect(provider.clientSecret).toBe('secret');
    expect(provider.id).toBeTruthy();
  });

  it('sanitizes provider payload to omit clientSecret', () => {
    const provider = {
      id: 'p1',
      name: 'Acme',
      issuer: 'https://example.com',
      clientId: 'abc',
      clientSecret: 'secret',
      createdAt: new Date().toISOString(),
    };

    const sanitized = sanitizeOidcProvider(provider);
    expect((sanitized as any).clientSecret).toBeUndefined();
    expect(sanitized.id).toBe('p1');
  });

  it('lists providers for an organization', async () => {
    const provider = { id: 'p1', name: 'Acme', issuer: 'https://example.com', clientId: 'abc', clientSecret: 'secret', createdAt: new Date().toISOString(), enabled: true };
    (dbPool.query as any).mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_providers: [provider] } }] });

    const providers = await listOidcProviders('org1');
    expect(providers).toHaveLength(1);
    expect(providers[0]?.enabled).toBe(true);
    expect(providers[0]?.id).toBe('p1');
  });

  it('returns a provider by id', async () => {
    const provider = { id: 'p1', name: 'Acme', issuer: 'https://example.com', clientId: 'abc', clientSecret: 'secret', createdAt: new Date().toISOString(), enabled: false };
    (dbPool.query as any).mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_providers: [provider] } }] });

    const result = await getOidcProvider('org1', 'p1');
    expect(result.id).toBe('p1');
    expect(result.enabled).toBe(false);
  });

  it('prevents duplicate provider issuers within an organization', async () => {
    const provider = { id: 'p1', name: 'Acme', issuer: 'https://example.com', clientId: 'abc', clientSecret: 'secret', createdAt: new Date().toISOString() };
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_providers: [provider] } }] });

    await expect(
      createOidcProvider('org1', {
        name: 'Acme Duplicate',
        issuer: 'https://example.com',
        clientId: 'abc2',
        clientSecret: 'secret2',
      })
    ).rejects.toThrow('provider_already_exists');
  });

  it('refreshes provider metadata and stores it', async () => {
    const provider = { id: 'p1', name: 'Acme', issuer: 'https://example.com', clientId: 'abc', clientSecret: 'secret', createdAt: new Date().toISOString() };
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_providers: [provider] } }] })
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({});

    const metadata = { issuer: 'https://example.com', authorization_endpoint: 'https://example.com/auth', token_endpoint: 'https://example.com/token', jwks_uri: 'https://example.com/jwks', response_types_supported: ['code'] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => metadata })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ keys: [] }) });
    // @ts-ignore
    global.fetch = fetchMock;

    const result = await refreshOidcProviderMetadata('org1', 'p1');
    expect(result.authorization_endpoint).toBe(metadata.authorization_endpoint);
    // @ts-ignore
    delete global.fetch;
  }, { timeout: 20000 });

  it('updates provider fields and clears metadata when issuer changes', async () => {
    const provider = { id: 'p1', name: 'Acme', issuer: 'https://example.com', clientId: 'abc', clientSecret: 'secret', createdAt: new Date().toISOString(), metadata: { issuer: 'https://example.com' } };
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_providers: [provider] } }] })
      .mockResolvedValueOnce({});

    const updated = await updateOidcProvider('org1', 'p1', { issuer: 'https://changed.com' });
    expect(updated.issuer).toBe('https://changed.com');
    expect(updated.metadata).toBeUndefined();
  });

  it('deletes a provider by id', async () => {
    const provider = { id: 'p1', name: 'Acme', issuer: 'https://example.com', clientId: 'abc', clientSecret: 'secret', createdAt: new Date().toISOString() };
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_providers: [provider] } }] })
      .mockResolvedValueOnce({});

    await deleteOidcProvider('org1', 'p1');
  });

  it('creates a dynamic client (RFC7591) and returns credentials', async () => {
    // SELECT settings
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: {} }] })
      .mockResolvedValueOnce({}); // UPDATE

    const metadata = { redirect_uris: ['https://app.example/cb'], response_types: ['code'] };
    const client = await (await import('./oidc.js')).createDynamicClient('org1', metadata);
    expect(client.client_id).toBeTruthy();
    expect(client.client_secret).toBeTruthy();
    expect(client.registration_access_token).toBeTruthy();
    expect(client.client_metadata.redirect_uris[0]).toBe('https://app.example/cb');
  });
});
