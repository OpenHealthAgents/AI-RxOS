# AI-RxOS Prompt 3

## Overview

Prompt 3 builds the Enterprise Authentication Service for AI-RxOS. This service lives in `services/auth` and extends the authentication foundation established in Prompt 2.

The Prompt 3 implementation provides enterprise identity, access control, session handling, organization support, invitation management, OIDC/OAuth2 interoperability, SCIM provisioning, passkey support, MFA, tenant isolation, and immutable audit logging for the authentication domain.

## Architecture

The Prompt 3 authentication architecture is a layered enterprise identity stack built around the following components:

- BetterAuth: central authentication engine for user identity, sessions, organization behavior, MFA, passkeys, API keys, SCIM, and SSO integration.
- PostgreSQL: authoritative relational data store for users, accounts, sessions, organizations, invitations, workspaces, projects, members, API keys, and audit log state.
- Neo4j: graph-backed authorization and relationship-aware authorization support used for advanced policy and graph traversal scenarios.
- Redis: rate limiting and session-related caching support.
- OIDC: OpenID Connect provider and client support for enterprise external identity integration.
- OAuth2: authorization and token-related interoperability for service and application access flows.
- SCIM: provisioning model for synchronizing identity data into the organization membership model.
- JWT: legacy gateway-compatible access token creation and downstream token propagation.
- Passkeys: passwordless credential support for secure device-level authentication.
- RBAC: role-based access control for users and organizational membership.
- ABAC: attribute-based authorization evaluation for richer access decisions.
- Session Management: authentication lifecycle, device session awareness, refresh behavior, and session UI support.
- Rate Limiting: request throttling protection for auth endpoints.
- Audit Logs: append-only, tamper-evident logging of compliance-sensitive authentication actions.

## Implemented Features

### BetterAuth

- Full form: BetterAuth
- What it is: The primary authentication framework used to power user authentication, session lifecycle, organization behavior, plugin capabilities, and secure identity flows.
- Why it is required: Prompt 3 requires a single enterprise-grade auth engine to unify authentication, organization support, and plugin-driven security controls.
- How it works: The service initializes `betterAuth` with PostgreSQL-backed persistence and activates plugins for administrator functions, organization support, two-factor authentication, passkeys, API keys, SSO, and SCIM.
- Files: `src/auth.ts`, `src/index.ts`

### OIDC

- Full form: OpenID Connect
- What it is: A standards-based identity layer for provider discovery, client configuration, metadata handling, and external identity broker integration.
- Why it is required: Prompt 3 requires enterprise SSO interoperability and trusted identity provider registration.
- How it works: The service exposes provider CRUD functions, metadata refresh logic, JWKS cache behavior, and dynamic client handling for OIDC integration.
- Files: `src/oidc.ts`, `src/jwksCache.ts`, `src/index.ts`

### OAuth2

- Full form: OAuth 2.0
- What it is: Authorization and token interoperability support for OAuth-style flows.
- Why it is required: Enterprise authentication services must support delegated authorization and external integration patterns.
- How it works: The service configures OAuth-capable flows through BetterAuth and adds token and provider logic in the auth service.
- Files: `src/auth.ts`, `src/index.ts`, `src/legacyToken.ts`, `src/oidc.ts`

### SSO

- Full form: Single Sign-On
- What it is: Shared identity access across enterprise applications using a trusted external identity provider.
- Why it is required: Prompt 3 requires centralized identity access and provider-driven authentication capability.
- How it works: BetterAuth and the SSO plugin are integrated into the auth service, and the runtime exposes SSO-related routes and handling through the main API surface.
- Files: `src/auth.ts`, `src/index.ts`, `src/oidc.ts`

### SCIM

- Full form: System for Cross-domain Identity Management
- What it is: Provisioning support for identity synchronization and organization membership updates.
- Why it is required: Enterprise authentication requires safe automated synchronization of identities into the organization model.
- How it works: SCIM endpoints and sync logic reconcile user data and organization membership, including role mapping and membership updates.
- Files: `src/scim.ts`, `src/scimWorker.ts`, `src/index.ts`, `src/auth.ts`

### MFA

- Full form: Multi-Factor Authentication
- What it is: Secondary authentication protection using time-based one-time passwords and recovery/backup codes.
- Why it is required: Prompt 3 requires stronger authentication assurance for privileged and user-facing flows.
- How it works: The service provides TOTP enablement, verification, QR generation, backup code management, recovery code management, and login challenge validation.
- Files: `src/mfa.ts`, `src/index.ts`

### Passkeys

- Full form: WebAuthn Passkeys
- What it is: Passwordless device-bound authentication credentials using platform or cross-device passkeys.
- Why it is required: Prompt 3 requires stronger phishing-resistant login options.
- How it works: The BetterAuth passkey plugin is integrated, and the service exposes passkey challenge and device management routes along with UI pages for passkey management.
- Files: `src/auth.ts`, `src/passkeys.ts`, `src/index.ts`, `public/passkeys.html`

### RBAC

- Full form: Role-Based Access Control
- What it is: Authorization based on predefined roles assigned to users or members.
- Why it is required: Prompt 3 requires the ability to segregate administrative and operational access using identity roles.
- How it works: The service provides role enforcement middleware and role-aware authorization helpers to validate access decisions.
- Files: `src/rbac.ts`, `src/index.ts`

### ABAC

- Full form: Attribute-Based Access Control
- What it is: Policy evaluation based on attributes such as organization, ownership, project, environment, clearance, and lock state.
- Why it is required: Prompt 3 requires more context-aware authorization than static roles alone can deliver.
- How it works: The ABAC engine evaluates access requests using subject, resource, action, and environment attributes and returns authorization decisions.
- Files: `src/abac.ts`, `src/index.ts`

### JWT

- Full form: JSON Web Token
- What it is: Token format used for authenticated access propagation between auth and downstream API components.
- Why it is required: Prompt 3 requires downstream service interoperability and a gateway-compatible token representation.
- How it works: The service signs a legacy HS256 access token with organization and role claims that can be consumed by the gateway layer.
- Files: `src/legacyToken.ts`, `src/index.ts`

### Refresh Tokens

- Full form: Refresh Token Support
- What it is: Token renewal capability for authenticated sessions.
- Why it is required: Prompt 3 requires long-lived user sessions without requiring full re-login for every short-lived token expiration.
- How it works: The session management flow issues and refreshes session state through the authentication service and database-backed session records.
- Files: `src/index.ts`, `src/auth.ts`, `src/db.ts`

### Session Management

- Full form: Session Management
- What it is: Creation, validation, tracking, refresh, and administration of authenticated sessions.
- Why it is required: Prompt 3 requires proper handling of active sessions, user identity continuity, and device-aware authentication state.
- How it works: BetterAuth manages session state through PostgreSQL-backed tables, while the service adds explicit session endpoints and UI support.
- Files: `src/index.ts`, `src/auth.ts`, `public/sessions.html`, `src/tenantContext.ts`

### Session & Device UI

- Full form: Session and Device User Interface
- What it is: Lightweight admin UI pages that allow users to inspect and manage sessions and passkey devices.
- Why it is required: Prompt 3 requires visible administration of active session state and passkey/device management.
- How it works: Static HTML pages are served from the auth service at `/admin/sessions` and `/admin/passkeys`.
- Files: `public/sessions.html`, `public/passkeys.html`, `src/index.ts`

### Workspace Membership

- Full form: Workspace Membership
- What it is: Assignment of users to workspace-level collaboration boundaries within an organization.
- Why it is required: Prompt 3 requires organization-scoped workspaces and collaborative access assignment.
- How it works: The schema and service layer manage workspace and membership relations that extend organization membership.
- Files: `src/db.ts`, `src/index.ts`, `src/scim.ts`

### Organization Support

- Full form: Organization Support
- What it is: Multi-tenant organization model for users, members, policies, and membership lifecycle.
- Why it is required: Prompt 3 requires enterprise identity separation by organization.
- How it works: BetterAuth organization plugin support and database schema enforce organization ownership and membership behavior.
- Files: `src/auth.ts`, `src/db.ts`, `src/index.ts`, `src/tenantContext.ts`

### Tenant Isolation

- Full form: Tenant Isolation
- What it is: Strict data isolation between organizations and tenant-scoped request context.
- Why it is required: Prompt 3 requires one organization’s data to remain invisible to another organization.
- How it works: PostgreSQL RLS policies and tenant context middleware bind each request to the current organization and enforce isolation at the database layer.
- Files: `src/tenantContext.ts`, `src/db.ts`, `src/index.ts`, `migrations/001_rls_row_level_security.sql`

### User Invitations

- Full form: User Invitations
- What it is: Organization invitation lifecycle for sending, accepting, rejecting, and resending invitations.
- Why it is required: Prompt 3 requires controlled onboarding of users to organizations and role assignment during membership creation.
- How it works: The invitation service inserts invitation records, validates expiration, accepts membership, records consent or rejection, and sends invitation email content.
- Files: `src/invitations.ts`, `src/index.ts`, `src/audit.ts`

### Immutable Audit Logs

- Full form: Immutable Audit Logs
- What it is: Append-only audit trail of sensitive identity actions with tamper-evident integrity fields.
- Why it is required: Prompt 3 requires compliance-oriented auditing for authentication and authorization actions.
- How it works: Audit events are inserted into `audit_log`, and database triggers protect the table from update/delete mutation while generating `prev_hash`, `current_hash`, and `signature` values.
- Files: `src/audit.ts`, `src/auditVerification.ts`, `migrations/001_rls_row_level_security.sql`, `migrations/002_audit_log_hashing.sql`

### Rate Limiting

- Full form: Rate Limiting
- What it is: Request throttling for authentication API endpoints to reduce abuse and overload.
- Why it is required: Prompt 3 requires service protection against repeated requests and brute-force style behavior.
- How it works: Redis-backed request counting middleware tracks client requests per IP and path and returns a rate limit response when thresholds are exceeded.
- Files: `src/rateLimit.ts`, `src/index.ts`

### Database Schema

- Full form: Database Schema
- What it is: The relational foundation for all auth, organization, workspace, project, session, invitation, passkey, and audit records.
- Why it is required: Prompt 3 requires a storage model that supports tenant isolation, audit immutability, organization membership, and auth lifecycle records.
- How it works: The service initializes schema through SQL migrations and runtime database bootstrap logic.
- Files: `src/db.ts`, `src/initDatabase.ts`, `migrations/001_rls_row_level_security.sql`, `migrations/002_audit_log_hashing.sql`

### Backend APIs

- Full form: Backend API Surface
- What it is: Express routes that expose authentication, session, OIDC, invitation, MFA, and admin capabilities.
- Why it is required: Prompt 3 requires a backend interface for all enterprise authentication actions.
- How it works: `src/index.ts` mounts BetterAuth routes and adds auth-specific endpoints for MFA, invitations, audit verification, and admin capabilities.
- Files: `src/index.ts`

### Frontend

- Full form: Frontend Admin UI
- What it is: Lightweight static pages for session and passkey administration.
- Why it is required: Prompt 3 requires visible administrative management surfaces for active sessions and device credentials.
- How it works: The service serves HTML UI pages under `/admin` and exposes them through route aliases.
- Files: `public/sessions.html`, `public/passkeys.html`, `src/index.ts`

### Tests

- Full form: Automated Test Coverage
- What it is: Regression and integration tests that validate authentication, OIDC, SCIM, JWT, passkeys, RBAC, ABAC, sessions, MFA, audit logs, and database isolation.
- Why it is required: Prompt 3 requires measurable verification of the enterprise authentication behavior.
- How it works: The service ships a suite of Vitest tests that exercise each relevant behavior.
- Files: `src/*.test.ts`

### Documentation

- Full form: Auth Documentation
- What it is: Implementation and verification documentation for Prompt 3.
- Why it is required: Prompt 3 requires a clear explanation of the architecture, behavior, and verification procedure.
- How it works: The repository includes the Prompt 3 documentation set in `services/auth/docs`.
- Files: `services/auth/docs/PROMPT3_README.md`, `services/auth/docs/PROMPT3_VERIFICATION.md`

## Folder Structure

### `src/`

The core implementation lives in `src/`.

#### `auth.ts`
- Purpose: BetterAuth initialization and plugin wiring.
- What it does: Creates the `auth` instance, enables BetterAuth plugins, and sets up PostgreSQL-backed identity behavior.
- Why it exists: It is the central authentication runtime for Prompt 3.

#### `index.ts`
- Purpose: Main Express entry point for the auth service.
- What it does: Mounts BetterAuth endpoints, adds direct service endpoints for MFA, sessions, audit verification, and enterprise admin flows, and serves the frontend static pages.
- Why it exists: It exposes the complete Prompt 3 runtime surface.

#### `db.ts`
- Purpose: Database bootstrap and schema initialization.
- What it does: Creates the relational schema and applies the RLS and audit-log protections at runtime.
- Why it exists: It establishes the database foundation required by Prompt 3.

#### `audit.ts`
- Purpose: Audit event writer.
- What it does: Appends audit records into the `audit_log` table.
- Why it exists: It records compliance-sensitive authentication activity.

#### `oidc.ts`
- Purpose: OIDC provider and client management.
- What it does: Manages provider metadata, discovery, JWKS behavior, and dynamic client registration-related helpers.
- Why it exists: It implements enterprise identity-provider interoperability.

#### `passkeys.ts`
- Purpose: Passkey business logic.
- What it does: Supports passkey device state and secure passwordless credential handling.
- Why it exists: It enables prompt-required passkey authentication capability.

#### `abac.ts`
- Purpose: ABAC evaluation engine.
- What it does: Makes authorization decisions based on organization, ownership, environment, and policy attributes.
- Why it exists: It provides richer authorization than RBAC alone.

#### `rbac.ts`
- Purpose: RBAC enforcement.
- What it does: Evaluates role-based access decisions for users and organization members.
- Why it exists: It enforces role separation within the enterprise auth service.

#### `legacyToken.ts`
- Purpose: Legacy JWT issuance.
- What it does: Mints the gateway-compatible HS256 JWT used by downstream consumers.
- Why it exists: It preserves compatibility with existing gateway token expectations.

#### `jwksCache.ts`
- Purpose: JWKS cache support.
- What it does: Stores and reuses OIDC provider JWKS metadata.
- Why it exists: It supports safe and efficient provider verification.

#### `rateLimit.ts`
- Purpose: Rate limiting middleware.
- What it does: Tracks request counts in Redis and rejects excess traffic.
- Why it exists: It protects the auth service from abusive request patterns.

#### `neo4j.ts`
- Purpose: Graph authorization support.
- What it does: Supports Neo4j-backed authorization state and graph permissions.
- Why it exists: It adds graph-based authorization support for advanced enterprise scenarios.

#### `public/sessions.html`
- Purpose: Session management UI.
- What it does: Displays active session information and related device context.
- Why it exists: It provides a lightweight frontend surface for session administration.

#### `public/passkeys.html`
- Purpose: Passkey management UI.
- What it does: Provides passkey/device administration visibility.
- Why it exists: It gives a simple frontend surface for passwordless management.

### `src/*.test.ts`

The Prompt 3 test suite is implemented directly in the `src/` tree. The main verification files are:

- `auth.ts` is the runtime entry point for BetterAuth.
- `oidc.test.ts` validates OIDC behavior.
- `jwks.test.ts` validates JWKS behavior.
- `crypto.test.ts` validates security primitives.
- `crypto.keys.test.ts` validates crypto key flows.
- `passkeys.test.ts` validates passkey integration.
- `abac.test.ts` validates attribute-based authorization.
- `rbac.test.ts` validates role-based authorization.
- `sessions.test.ts` validates session flow behavior.
- `scim.test.ts` validates SCIM provisioning behavior.
- `mfa.test.ts` validates MFA behavior.
- `audit.test.ts` validates audit logging and integrity fields.
- `rls.integration.test.ts` validates tenant isolation via RLS.
- `invitations.test.ts` validates invitation lifecycle behavior.
- `db.init.test.ts` validates database initialization behavior.

## API Summary

The Prompt 3 API surface is organized into major groups.

### Authentication
- User registration and login flows
- BetterAuth-managed account and session behavior
- Legacy token issuance and authentication routing

### Sessions
- Session introspection
- Session refresh behavior
- Session/device management via admin UI endpoints

### Passkeys
- Challenge and verification endpoints for WebAuthn/passkey flows
- Device credential management

### OIDC
- Provider registration and update
- Metadata refresh
- Dynamic client handling
- JWKS verification support

### Organizations
- Organization membership behavior
- Organization scoped access and context
- Member management and tenant-scoped operations

### Invitations
- Invitation creation
- Invitation acceptance
- Invitation rejection
- Invitation expiration
- Invitation resend

### Admin APIs
- Audit verification endpoints
- MFA administrative endpoints
- Organization identity administration endpoints
- Session and device management surface

## Database Tables

The Prompt 3 schema stores identity and access state in the following primary relational tables.

### `users`
- Purpose: Stores the end-user identity record.
- Why it exists: It provides the nominal identity reference for authentication and account association.

### `account`
- Purpose: Stores authentication account relationships and linked account metadata.
- Why it exists: It supports flows such as password login, social login, and provider-backed account mapping.

### `session`
- Purpose: Stores session records and their security lifecycle data.
- Why it exists: It enables session validation, refresh, and device-level management.

### `passkey_device`
- Purpose: Stores passkey credential and device-associated data.
- Why it exists: It supports passwordless authentication and device-level credential organization.

### `organization`
- Purpose: Stores organization-level identity and configuration state.
- Why it exists: It provides the top-level tenant boundary for enterprise auth.

### `member`
- Purpose: Stores organization membership relationships between users and organizations.
- Why it exists: It enables RBAC, organization-scoped access, and tenant-aware authorization.

### `workspace`
- Purpose: Stores workspace metadata and membership boundaries within an organization.
- Why it exists: It supports workspace-level collaboration and authorization contexts.

### `project`
- Purpose: Stores project records that are scoped within organization and workspace domains.
- Why it exists: It provides finer-grained access boundaries.

### `audit_log`
- Purpose: Stores immutable audit entries for authentication and authorization actions.
- Why it exists: It enables append-only and tamper-evident compliance logging.

### `invitation`
- Purpose: Stores organization invitation records and status transitions.
- Why it exists: It supports user onboarding, expiration, acceptance, rejection, and resend behavior.

### `api_key`
- Purpose: Stores API key-related identity and ownership metadata.
- Why it exists: It enables service-to-service and organization-scoped key usage.

## Test Coverage

The Prompt 3 test suite validates the core enterprise authentication requirements.

- `oidc.test.ts`: validates OIDC provider and client behavior.
- `jwks.test.ts`: validates JWKS lookup and provider key handling.
- `crypto.test.ts`: validates cryptographic primitives used by the auth service.
- `crypto.keys.test.ts`: validates key material and related security flows.
- `passkeys.test.ts`: validates passkey authentication behavior.
- `abac.test.ts`: validates ABAC decisions and policy evaluation.
- `rbac.test.ts`: validates role assignment and role-based enforcement.
- `sessions.test.ts`: validates session lifecycle behavior.
- `scim.test.ts`: validates SCIM synchronization logic.
- `mfa.test.ts`: validates MFA enablement, verification, and backup/recovery flows.
- `audit.test.ts`: validates audit log writes, integrity fields, and immutability behavior.
- `rls.integration.test.ts`: validates tenant separation and row-level security isolation.
- `invitations.test.ts`: validates invitation creation, acceptance, rejection, expiration, and resend flow.
- `db.init.test.ts`: validates the database initialization path and startup consistency.

## Conclusion

Prompt 3 requirements are implemented in the `services/auth` service. The implementation provides the enterprise authentication capability described by the Prompt 3 scope, including BetterAuth integration, organization and tenant separation, OIDC/OAuth2/SSO support, SCIM provisioning, MFA, passkeys, RBAC and ABAC, JWT and refresh/session handling, invitation management, immutable audit logs, rate limiting, and a complete relational schema with test coverage.
