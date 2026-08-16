# Test Matrix

## Backend

| Area | Test | Result |
|---|---|---|
| Workflow DAG validation | `test_workflow_logic.py` | PASS |
| Workflow cross-org IDOR | `test_workflow_logic.py` | PASS |
| Workflow agent_chain classification | `test_workflow_execution.py` | PASS |
| Runner interrupt / failure / retry | `test_runner.py` | PASS |
| Resume idempotency | `test_execution_resume.py` | PASS |
| Celery DLQ helper | `test_tasks_retry.py` | PASS |
| Auth / refresh / reset code | `test_auth_code.py` | PASS |
| RBAC permissions | `test_rbac.py` | PASS |
| Audit action classification | `test_audit_classification.py` | PASS |
| Organization members | `test_organization_members.py` | PASS |
| Full backend suite | `pytest -q` | `137 passed` |

## Frontend

| Area | Test | Result |
|---|---|---|
| Formatting utilities | `format.test.ts` | PASS |
| API client token/error | `api.test.ts` | PASS |
| Sidebar | `Sidebar.test.tsx` | PASS |
| Settings panels | `SettingsPanels.test.tsx`, `SettingsTabs.test.tsx` | PASS |
| Playwright browser smoke | `e2e/app.spec.ts` | PASS |
| Vitest full suite | `vitest run` | `18 passed` |

## Deployment

| Check | Command | Result |
|---|---|---|
| Docker Compose config | `docker compose config --quiet` | PASS |
| Backend health | `/health` | PASS |
| Backend image build | `docker compose build backend worker` | PASS |
| Real multi-tenant API attack | live backend script | PASS |
| Real resume concurrency | live backend script | PASS |
| Real current_step persistence | live execution | PASS |
| Phase 4 no-auth/bad-JWT | live API script | PASS |
| Phase 4 ADMIN_API_KEY scope | live API script | PASS |
| Phase 4 cross-org list isolation | live API script | PASS |
| Phase 4 RAG cross-org search | live API script | PASS |
| Phase 4 upload boundary | live API script | PASS |
| Phase 4 terminal state transitions | live API script | PASS |
| Phase 5 public backend health | `curl http://193.112.130.181:8000/health` | PASS |
| Phase 5 HTTPS check | `curl https://synplex.xyz` | FAIL |
| Phase 5 HTTP root | `curl http://193.112.130.181/` | FAIL |
| Phase 5 Compose port hardening | `docker compose config --quiet` | PASS |
| Phase 5.5 production SSH | `ssh ubuntu@193.112.130.181` | FAIL |
| Phase 5.5 production port scan | Python socket scan | FAIL |
| Phase 5.5 DNS resolution | DNS-over-HTTPS | PASS |
| Phase 5.5 HTTPS | `curl https://synplex.xyz` | FAIL |
| Phase 5.6 production deploy | `docker compose up -d --build` | PASS |
| Phase 5.6 port hardening | `sudo ss -lntp` | PASS |
| Phase 5.6 HTTPS server-local | `curl -k https://synplex.xyz` | PASS |
| Phase 5.6 production smoke | document/RAG/execution/approval | PASS |
| Phase 5.7 final port scan | `sudo ss -lntp` | PASS |
| Phase 5.7 HTTP redirect | `curl -I http://synplex.xyz` | PASS |
| Phase 5.7 HTTPS | `curl -I https://synplex.xyz` | PASS |
| Phase 5.7 backup | `pg_dump` | PASS |
| Phase 5.7 restore drill | temp database restore | PASS |
| Phase 6 auth refresh / reset tests | `pytest` unit tests | PASS |
| Phase 7 RBAC / audit / members tests | `pytest` unit tests | PASS |

## Not Covered Yet

- Multi-tenant real API integration tests.
- Celery retry end-to-end with delayed failures.
- Real multi-model fallback.
