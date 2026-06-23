# External User Platform Integration Design

## Goal

Expose the existing dashboard and newly completed multi-user system as a first external-facing platform where:

- the root domain `/` is the product entry
- unauthenticated visitors see the login view
- authenticated users enter the dashboard shell
- admins manage user accounts from inside the dashboard
- regular users access official research views plus their own watchlist and reviews

This v1 is an external deployment and integration step, not a new user-platform rebuild.

## Product Boundary

This version keeps the current scope deliberately narrow:

- admin-created accounts only
- no self-registration
- no forgot-password or email reset flow
- no user-defined strategy builder
- no user backtesting platform
- no multiple private watchlists per user
- no separate marketing homepage

The product entry is the dashboard itself.

## Current Baseline

`main` already contains the multi-user platform layer and the auth-aware dashboard shell:

- `dashboard/src/main.tsx` renders `DashboardRoot`
- `DashboardRoot` handles login bootstrap and role-aware navigation
- official workspaces remain available through `DashboardShell`
- private user areas exist for:
  - 我的观察池
  - 我的复盘
- admin-only user management exists inside the dashboard
- backend auth/session/CSRF/admin/user-watchlist/user-review routes already exist in `src/stock_research/dashboard/app.py`

That means the external integration work should focus on product entry, deployment shape, runtime configuration, and operational closure rather than rebuilding user-domain behavior.

## Recommended Architecture

### Entry Model

Use the current dashboard root entry directly:

- external domain root `/` serves the dashboard frontend
- `DashboardRoot` remains the app entrypoint
- unauthenticated state renders `LoginView`
- authenticated state renders:
  - `官方`
  - `我的`
  - `管理` for admins only

This avoids introducing a second outer shell or landing page.

### Deployment Model

Use a same-origin deployment:

- `https://your-domain/` serves the frontend
- `https://your-domain/api/*` serves the FastAPI dashboard API

This is the recommended v1 model because it preserves the existing cookie/session/CSRF design with minimal change and avoids cross-origin cookie complexity.

### Runtime Topology

Recommended production topology:

1. Reverse proxy terminates TLS
2. Reverse proxy serves frontend assets at `/`
3. Reverse proxy forwards `/api/*` to the dashboard FastAPI service
4. FastAPI runs on an internal port only

Two acceptable frontend serving patterns:

- preferred: reverse proxy serves `dashboard/dist`
- acceptable: reverse proxy forwards `/` to a frontend process if the deployment environment already uses that pattern

The design should support either, but the deployment documentation should recommend static asset serving first.

## URL And Navigation Model

### Public URL

The external dashboard occupies the root path:

- `https://your-domain/`

Do not use a subpath like `/dashboard/` for v1.

### Internal Navigation

Inside the authenticated shell:

- official content stays grouped under `官方`
- user-private content stays under `我的`
- admin-only account operations stay under `管理`

The existing query-parameter navigation model may remain for v1. No routing rewrite is required unless external deployment constraints force it.

## Authentication And Security Requirements

### Session Model

Keep the current session-cookie design:

- username/password login
- server-issued session cookie
- CSRF protection for session-authenticated mutations
- server-side login throttling

Do not replace this with bearer tokens in v1.

### External Deployment Security

The external deployment must satisfy:

- HTTPS required
- auth cookies must be issued with `Secure`
- same-origin frontend/API deployment
- CSRF protection remains enabled
- FastAPI should not be exposed directly to the internet without the reverse proxy

### Admin Safety

The current admin safety requirements stay in force:

- admins cannot disable themselves
- the last active admin cannot be disabled
- blank admin-created credentials are rejected server-side

## Admin Operations Model

Admins use the dashboard itself to manage users.

Supported operations in v1:

- login as admin
- create a user
- assign initial username/password
- enable a disabled user
- disable a user
- reset a user's password

No additional admin console is needed outside the dashboard.

## Operational Closure Requirements

The external integration is not complete until operators can answer:

- how is the first admin account created?
- how does an admin log in after deployment?
- how does an admin create the first standard user?
- how does an admin reset a user's password?
- how does an operator recover if an account is disabled?
- where do audit logs and service logs live?

That means the implementation must include a minimal operator runbook alongside the code changes.

## Implementation Scope

The integration implementation should cover four work areas.

### 1. External Entry Alignment

Align the target external branch so it uses the merged `DashboardRoot`-based entry and current multi-user shell behavior rather than any older `App`-only root entry.

### 2. Same-Origin Deployment Shape

Add or update deployment-facing configuration and documentation for:

- frontend root serving
- `/api/*` reverse proxying
- internal API bind host/port
- production environment assumptions for cookies and CSRF

### 3. Admin Lifecycle Runbook

Document the operator flow for:

- initial admin bootstrap
- user creation
- reset password
- enable/disable users

### 4. External Readiness Verification

Add or tighten verification so the external-root login behavior is proven:

- unauthenticated root path shows login
- admin login succeeds
- admin sees management entry
- non-admin does not see management entry
- official and private views remain reachable after login

## Out Of Scope

The following are explicitly deferred:

- self-registration
- forgot-password/email recovery
- MFA
- organization/team hierarchy
- billing
- user-created strategy definitions
- user-run backtests
- public landing page or pricing page
- large-scale dashboard redesign

## Risks And Mitigations

### Risk: Mixing With Older Dashboard Entry State

Some non-`main` branches may still be rooted in the older `App` entry.

Mitigation:

- do the work only from the merged `main` baseline
- verify `dashboard/src/main.tsx` renders `DashboardRoot`

### Risk: Cross-Origin Cookie Misconfiguration

If frontend and API are deployed on different origins, login/cookie behavior becomes fragile.

Mitigation:

- same-origin deployment is the default design
- do not introduce cross-origin deployment in v1

### Risk: “External Launch” Expands Into SaaS Rebuild

Requests for registration, strategy building, or backtesting can easily widen the project.

Mitigation:

- keep the external launch definition fixed to admin-managed accounts + private user workspace

## Testing Strategy

The implementation must preserve the existing merged baseline and add external-entry verification where needed.

Minimum validation target:

- relevant Python dashboard user/auth tests pass
- dashboard Vitest suite passes
- dashboard Playwright smoke passes
- production build passes

Additional external-entry checks should specifically validate root-path unauthenticated and authenticated behavior.

## Recommended Implementation Sequence

1. Start from `main`
2. Create a fresh integration worktree/branch
3. Align the external branch entrypoint and shell assumptions
4. Add deployment/runbook materials
5. Add external-entry verification
6. Run full regression

## Final Positioning

This v1 should be treated as:

> the existing research dashboard, now externally deployable as a same-origin login-first platform with admin-managed accounts, official read-only research views, and user-private watchlist/review workspaces.

That positioning keeps the launch narrow, shippable, and compatible with future expansion.
