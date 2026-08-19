# AgentHub Project State

Last updated: 2026-08-16 (Phase 7)

## Overall Status

Phase 2 P1 fixes completed. Phase 3 added real API multi-tenant, real resume concurrency, and current-step persistence verification. Phase 4 added live auth/multi-tenant/boundary/state-machine security checks. Phase 5 completed production port hardening and backup/restore verification. Phase 6 productized authentication (forgot/reset password, refresh token, unified errors, SMTP/MailHog). Phase 7 added enterprise SaaS capabilities (RBAC, member management, action-level audit, tenant isolation tests).

## Current Verified

- Backend tests: `137 passed`
- Frontend Vitest: `18 passed`
- Frontend typecheck/build: pass
- Backend Black/Ruff: pass
- Docker services: running
- Backend health: `database=true`, `redis=true`, `llm=true`
- Real multi-tenant API test: cross-org workflow access returns 404
- Real resume concurrency test: one request 202, one 409
- Real Execution current_step_index persisted as 3 after completion
- Phase 4: no-auth/bad-JWT normal API returns 401
- Phase 4: ADMIN_API_KEY does not grant normal `/api/executions` access
- Phase 4: cross-org list isolation verified for documents/models/conversations/workflows/executions
- Phase 4: RAG search returns 0 cross-org results
- Phase 4: upload empty/invalid file returns 422
- Phase 4: terminal execution cancel/resume returns 409
- Phase 5.7: public listening ports are 22/80/443
- Phase 5.7 final: PostgreSQL backup and independent restore drill passed
- Phase 6: auth unit tests cover register/login/forgot/reset/refresh/token expiry
- Phase 7: RBAC permission tests, audit action classification tests, member management tests pass

## Phase 6 Changes

- Access token lifetime reduced to 30 minutes; refresh token remains 7 days.
- `POST /api/auth/refresh` distinguishes expired vs invalid refresh tokens.
- Frontend auto-refreshes on 401 with single-flight refresh and retry.
- Added forgot/reset password APIs and unified auth error codes.
- Email service now prefers SMTP (MailHog) and falls back to Resend.

## Phase 7 Changes

- Added RBAC roles `admin` / `member` / `viewer` via `app/core/permissions.py`.
- Wired `require_permission()` into model/execution/workflow/document/audit routes.
- Added organization member management API.
- Extended `AuditLog` with `action`, `resource_type`, `resource_id`, `ip_address`.

## Known Gaps

See `KNOWN_ISSUES.md`.

## Next Phase

Remaining production items: real two-model fallback verification and optional refresh-token migration to HttpOnly cookies. Production email now uses Resend (`no-reply@synplex.xyz`, verified) with SMTP disabled.
