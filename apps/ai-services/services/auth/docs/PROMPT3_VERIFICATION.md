# Prompt 3 Verification Commands

This document contains all commands required to verify the implementation of Prompt 3 (Enterprise Authentication for AI-RxOS).

Project Location:

```powershell
cd C:\Users\Lenovo\Downloads\AI-RxOS\services\auth
```

Verified Local Runtime Note:

For local Windows verification, the auth service must point to the host loopback Postgres endpoint instead of the Docker-only service hostname `postgres`. The Docker Compose stack now publishes Postgres on host port `15432`, and the auth service is exposed on `8081`.

Docker-backed dependency startup:

```powershell
docker compose up -d postgres redis
```

Verified auth runtime environment:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:DATABASE_URL='postgresql://ai_rxos:changeme@127.0.0.1:15432/ai_rxos'
$env:REDIS_URL='redis://localhost:6379'
$env:PORT='8081'
$env:BETTER_AUTH_SECRET='mysupersecretkey12345678901234567890'
$env:JWT_SECRET='myjwtsecret12345678901234567890'
$env:AUDIT_LOG_HMAC_SECRET='audit-hmac-secret-for-local-dev'
$env:KEY_MANAGEMENT_PROVIDER='env'
$env:ACTIVE_MASTER_KEY='v1'
$env:MASTER_KEY_V1='<replace-with-a-real-32-byte-base64-key>'
```

OIDC note:
- The verified runtime path for `/api/v1/auth/oidc/register` requires the env-backed key registry to be configured with a valid 32-byte Base64 `MASTER_KEY_V1`.
- Without that key, the route will reject dynamic client registration with the unsupported key version error.

Verified startup command:

```powershell
cd C:\Users\Lenovo\Downloads\AI-RxOS\services\auth
pnpm exec tsx src/index.ts
```

Expected startup evidence:

```text
Database schema initialized successfully (RLS and Immutable Audit Log triggers configured).
{"level":"INFO","msg":"Auth service listening","port":"8081"}
```

Admin UI endpoints available from the auth service:

- `http://localhost:8081/admin/sessions`
- `http://localhost:8081/admin/passkeys`

---

# 1. Install Dependencies

Command

```powershell
pnpm install
```

Purpose

- Installs all required Node.js packages.
- Downloads BetterAuth, Express, PostgreSQL client, Vitest, Redis client, etc.
- Must be executed before running the project.

Expected Result

- Installation completes without errors.

---

# 2. TypeScript Compile Check

Command

```powershell
cd C:\Users\Lenovo\Downloads\AI-RxOS\services\auth
pnpm run typecheck
```

or

```powershell
cd C:\Users\Lenovo\Downloads\AI-RxOS\services\auth
pnpm exec tsc -p tsconfig.json --noEmit
```

Purpose

Checks that:

- TypeScript code compiles successfully for the Prompt 3 auth service.
- No syntax errors.
- No missing imports.
- No type errors.

Expected Result

```
No TypeScript errors
```

This proves the Prompt 3 backend source code is valid.

Note

Running `pnpm run typecheck` from the repository root triggers the monorepo-wide typecheck and may fail in unrelated packages because those packages require tooling such as `mypy`. For Prompt 3 verification, the correct scope is the `services/auth` directory.

---

# 3. Run Complete Prompt 3 Test Suite

Command

```powershell
pnpm exec vitest run --reporter verbose
```

Purpose

Runs every unit and integration test inside the Auth service.

This verifies:

- BetterAuth
- OIDC
- OAuth2
- SCIM
- MFA
- Passkeys
- RBAC
- ABAC
- JWT
- Refresh Tokens
- Sessions
- Invitations
- Audit Logs
- Rate Limiting
- RLS
- JWKS
- Encryption
- Crypto utilities

Expected Result

```
All test files passed

All tests passed
```

---

# 4. Verify Tenant Isolation (Postgres RLS)

Command

```powershell
pnpm exec vitest run src/rls.integration.test.ts --reporter verbose
```

Purpose

Verifies database-level tenant isolation.

Checks:

- Organization A cannot access Organization B data.
- Session isolation.
- Invitation isolation.
- Audit log isolation.
- Passkey isolation.
- Organization isolation.
- Delete protection.

Expected Result

```
7 tests passed
```

This proves Prompt 3 requirement:

✅ Tenant / Project Isolation

---

# 5. Verify Invitation Workflow

Command

```powershell
pnpm exec vitest run src/invitations.test.ts --reporter verbose
```

Purpose

Verifies:

- Invitation creation
- Invitation acceptance
- Invitation rejection
- Invitation expiration
- Membership creation

Expected Result

```
5 tests passed
```

This proves:

✅ User Invitations

---

# 6. Verify MFA

Command

```powershell
pnpm exec vitest run src/mfa.test.ts --reporter verbose
```

Purpose

Checks:

- MFA setup
- MFA verification
- Organization MFA policy
- Passkey authentication

Expected Result

```
All MFA tests passed
```

This proves:

✅ MFA

---

# 7. Verify Audit Logs

Command

```powershell
pnpm exec vitest run src/audit.test.ts --reporter verbose
```

Purpose

Checks:

- Audit event creation
- Append-only audit logs
- Tamper-evident logging
- Login events
- Session revocation events
- Invitation events

Expected Result

```
Audit tests passed
```

This proves:

✅ Immutable Audit Logs

---

# 8. Verify OIDC

Command

```powershell
pnpm exec vitest run src/oidc.test.ts --reporter verbose
```

Purpose

Checks:

- Provider creation
- Provider update
- Provider deletion
- Dynamic Client Registration
- Metadata Discovery
- Secret Encryption

Expected Result

```
OIDC tests passed
```

This proves:

- OIDC
- OAuth2
- RFC 7591
- Secret Encryption

---

# 9. Verify Passkeys

Command

```powershell
pnpm exec vitest run src/passkeys.test.ts --reporter verbose
```

Purpose

Checks:

- Passkey registration
- Rename
- Revoke
- Device management

Expected Result

```
Passkey tests passed
```

This proves:

✅ Passkeys

---

# 10. Verify JWKS Cache

Command

```powershell
pnpm exec vitest run src/jwks.test.ts --reporter verbose
```

Purpose

Checks:

- JWKS cache
- Refresh
- Key retrieval
- Provider health

Expected Result

```
JWKS tests passed
```

This proves:

- JWKS Cache
- Provider Monitoring

---

# 11. Verify ABAC

Command

```powershell
pnpm exec vitest run src/abac.test.ts --reporter verbose
```

Purpose

Checks:

- Attribute-Based Access Control
- Policy evaluation

Expected Result

```
ABAC tests passed
```

This proves:

✅ ABAC

---

# 12. Verify RBAC

Command

```powershell
pnpm exec vitest run src/rbac.test.ts --reporter verbose
```

Purpose

Checks:

- Role-Based Access Control
- Permission validation
- Role hierarchy

Expected Result

```
RBAC tests passed
```

This proves:

✅ RBAC

---

# 13. Start the Auth Service

Command

```powershell
cd C:\Users\Lenovo\Downloads\AI-RxOS\services\auth
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:DATABASE_URL='postgresql://ai_rxos:changeme@127.0.0.1:15432/ai_rxos'
$env:REDIS_URL='redis://localhost:6379'
$env:PORT='8081'
$env:BETTER_AUTH_SECRET='mysupersecretkey12345678901234567890'
$env:JWT_SECRET='myjwtsecret12345678901234567890'
$env:AUDIT_LOG_HMAC_SECRET='audit-hmac-secret-for-local-dev'
$env:KEY_MANAGEMENT_PROVIDER='env'
$env:ACTIVE_MASTER_KEY='v1'
$env:MASTER_KEY_V1='<replace-with-a-real-32-byte-base64-key>'
pnpm exec tsx src/index.ts
```

Purpose

Starts the Authentication Service using the verified local host Postgres endpoint and Redis endpoint.

Expected Result

The service starts successfully and binds to port `8081`.

Example

```
Database schema initialized successfully (RLS and Immutable Audit Log triggers configured).
{"level":"INFO","msg":"Auth service listening","port":"8081"}
```

Note

If PowerShell reports `EADDRINUSE: address already in use :::8081`, a previous auth process is still bound to port `8081`. Stop that stale process or use a fresh terminal and rerun the command.

---

# 14. Verify Session Management UI

Open

```
http://localhost:8081/admin/sessions
```

Purpose

Checks:

- Active sessions
- Browser
- Operating System
- IP Address
- Last Activity
- Session Expiry
- Force Logout

This proves:

- Session Management
- Session & Device Management UI

---

# 15. Verify Passkey Management UI

Open

```
http://localhost:8081/admin/passkeys
```

Purpose

Checks:

- Passkey list
- Rename
- Revoke

This proves:

✅ Passkey UI

---

# 16. Verify Session API

Request

```
GET /api/v1/auth/sessions
```

Purpose

Returns all active sessions.

Expected Result

JSON containing session information.

---

# 17. Verify Passkey API

Request

```
GET /api/v1/auth/passkeys
```

Purpose

Returns all registered passkeys.

---

# 18. Verify OIDC Provider API

Request

```
GET /api/v1/auth/oidc/providers
```

Purpose

Lists configured OIDC providers.

---

# 19. Verify Dynamic Client Registration

Request

```
POST /api/v1/auth/oidc/register
```

Purpose

Registers a new OAuth/OIDC client dynamically.

This proves:

RFC 7591 Dynamic Client Registration

---

# Prompt 3 Requirement Coverage

| Requirement | Verification |
|-------------|--------------|
| BetterAuth | Full test suite |
| OIDC | oidc.test.ts |
| OAuth2 | oidc.test.ts |
| SSO | Full test suite |
| SCIM | Full test suite |
| MFA | mfa.test.ts |
| Passkeys | passkeys.test.ts |
| RBAC | rbac.test.ts |
| ABAC | abac.test.ts |
| JWT | Full test suite |
| Refresh Tokens | Full test suite |
| Session Management | Session UI + API |
| Session Device UI | Browser |
| Workspace Membership | invitations.test.ts |
| Organization Support | Full test suite |
| Tenant Isolation | rls.integration.test.ts |
| User Invitations | invitations.test.ts |
| Immutable Audit Logs | audit.test.ts |
| Rate Limiting | Full test suite |
| Database Schema | db.ts + Tests |
| Backend APIs | API endpoints |
| Frontend | Sessions UI + Passkeys UI |
| Tests | Vitest |
| Documentation | PROMPT3_README.md + PROMPT3_VERIFICATION.md |

---

# Recommended Verification Order

Run the following commands in order:

```powershell
cd C:\Users\Lenovo\Downloads\AI-RxOS\services\auth

pnpm install

pnpm run typecheck

pnpm exec vitest run --reporter=basic

pnpm exec vitest run src/rls.integration.test.ts --reporter verbose

pnpm exec vitest run src/invitations.test.ts --reporter verbose

pnpm exec vitest run src/mfa.test.ts --reporter verbose

pnpm exec vitest run src/audit.test.ts --reporter verbose

pnpm exec vitest run src/oidc.test.ts --reporter verbose

pnpm exec vitest run src/passkeys.test.ts --reporter verbose

pnpm exec vitest run src/abac.test.ts --reporter verbose

pnpm exec vitest run src/rbac.test.ts --reporter verbose

pnpm exec vitest run src/jwks.test.ts --reporter verbose

Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:DATABASE_URL='postgresql://ai_rxos:changeme@127.0.0.1:15432/ai_rxos'
$env:REDIS_URL='redis://localhost:6379'
$env:PORT='8081'
$env:BETTER_AUTH_SECRET='mysupersecretkey12345678901234567890'
$env:JWT_SECRET='myjwtsecret12345678901234567890'
$env:AUDIT_LOG_HMAC_SECRET='audit-hmac-secret-for-local-dev'
$env:KEY_MANAGEMENT_PROVIDER='env'
$env:ACTIVE_MASTER_KEY='v1'
$env:MASTER_KEY_V1='<replace-with-a-real-32-byte-base64-key>'
pnpm exec tsx src/index.ts
```

After starting the service, verify the UI:

```
http://localhost:8081/admin/sessions

http://localhost:8081/admin/passkeys
```

If all commands and UI checks complete successfully, the implemented Prompt 3 requirements have been verified.
