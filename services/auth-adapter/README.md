# auth-adapter

BetterAuth adapter scaffold for the identity migration described in the
platform's Prompt 2 work. Runs on port **8089**. This service is
additive: `services/auth` (Go) is unchanged and still owns the
`/api/v1/auth/{register,login,refresh}` contract that apps/api-gateway
proxies and validates today.

## What's here

- `src/auth.ts` — a real `betterAuth()` instance (Postgres via `pg`,
  email/password enabled, BetterAuth's own JWT plugin) mounted at
  `/api/auth/*` via `toNodeHandler`. BetterAuth manages its own
  user/session tables in the same Postgres database as `services/auth`'s
  hand-rolled `users` table — a different table set, no collision.
- `src/legacyToken.ts` — a documented bridge function,
  `signLegacyAccessToken`, that mints an HS256 JWT with the same
  `sub`/`iat`/`exp` claim shape as `services/auth` (see
  `services/auth/internal/handlers/auth.go`), signed with the same
  `JWT_SECRET` so `apps/api-gateway`'s existing `jwtAuth` middleware
  accepts it unchanged.
- `GET /healthz` — standard health endpoint, matches every other service.

## Schema migration (required before first use)

Unlike this repo's Go services (which self-migrate `CREATE TABLE IF NOT
EXISTS` on boot), BetterAuth does **not** auto-create its tables when the
server starts — verified by running this service against the
docker-compose Postgres: it started and served `/healthz` cleanly, but no
BetterAuth tables existed in `ai_rxos` until a migration is run. Passing a
raw `pg.Pool` (as `src/auth.ts` does) makes BetterAuth use its built-in
Kysely adapter, so the standard CLI migration applies:

```bash
cd services/auth-adapter
npx auth@latest migrate --config src/auth.ts
```

This is a one-time (or per-schema-change) operational step, not something
that happens automatically in `docker-compose up` or the Helm chart —
whoever wires this into a real deploy path needs to run it (e.g. as a
Helm pre-install hook or a CI migration step) before traffic hits
`/api/auth/*`.

## What's intentionally not here yet

BetterAuth's built-in JWT plugin only supports asymmetric algorithms
(EdDSA by default, or ES256/ES512/RS256/PS256/ECDH-ES) — **not** HS256
with a static shared secret (verified against
https://www.better-auth.com/docs/plugins/jwt). That means the plugin
itself cannot produce tokens compatible with the existing gateway
middleware; `legacyToken.ts` exists as the bridge, but nothing currently
calls it. Wiring a real sign-in flow (BetterAuth authenticates the user →
`signLegacyAccessToken` mints the gateway-compatible token → response
matches `services/auth`'s `tokenResponse` shape) requires deciding:

1. Which BetterAuth server-side API to call for programmatic sign-in
   (e.g. `auth.api.signInEmail`) — needs verifying against the current
   BetterAuth version pinned in `package.json`, since this wasn't
   confirmed against live docs for this scaffold.
2. Whether refresh tokens continue to live in Redis (mirroring
   `services/auth`) or move to BetterAuth's own session store.
3. Whether/how `apps/api-gateway` routes any traffic to this service —
   no routing change has been made; it is not in `docker-compose.yml`'s
   `api-gateway.depends_on` or any Helm ingress path yet.
4. How tenant/organization claims (see `packages/tenancy`) get attached
   to issued tokens, if at all.

None of this is invented here — see the code comments in `src/auth.ts`
and `src/legacyToken.ts` for exactly what was verified against BetterAuth
docs versus what remains open.
