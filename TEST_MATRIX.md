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
| Full backend suite | `pytest -q` | `93 passed` |

## Frontend

| Area | Test | Result |
|---|---|---|
| Formatting utilities | `format.test.ts` | PASS |
| API client token/error | `api.test.ts` | PASS |
| Sidebar | `Sidebar.test.tsx` | PASS |
| Settings panels | `SettingsPanels.test.tsx`, `SettingsTabs.test.tsx` | PASS |
| Playwright browser smoke | `e2e/app.spec.ts` | PASS |
| Vitest full suite | `vitest run` | `14 passed` |

## Deployment

| Check | Command | Result |
|---|---|---|
| Docker Compose config | `docker compose config --quiet` | PASS |
| Backend health | `/health` | PASS |
| Backend image build | `docker compose build backend worker` | PASS |
| Real multi-tenant API attack | live backend script | PASS |
| Real resume concurrency | live backend script | PASS |
| Real current_step persistence | live execution | PASS |

## Not Covered Yet

- Multi-tenant real API integration tests.
- Celery retry end-to-end with delayed failures.
- Real multi-model fallback.
