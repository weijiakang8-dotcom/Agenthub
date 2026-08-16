# Known Issues

## P1 Resolved in Phase 2

- Workflow version/list/rollback/validate/delete endpoints lacked organization checks.
- Explicit workflow agent_chain could be overwritten by task classification.
- Celery max_retries did not retry normal execution failures because runner swallowed exceptions.
- Resume endpoint was not atomic, allowing duplicate/concurrent enqueue.

## P2 Remaining

- ~~`Execution.current_step_index` is not persisted from final LangGraph state after completion.~~ Resolved in Phase 3.
- ADMIN_API_KEY fallback is documented but not implemented in `get_current_user()`.
- RAG stores whole documents without chunking and scans all documents in memory.
- No automated IDOR concurrency suite beyond the new unit-level tests.
- Frontend global 401/JWT expiry handling is incomplete.

## UNVERIFIED

- Real multi-model fallback.
- Celery retry end-to-end with delayed failures was not fully observed in this phase.
- `GET /api/documents/{id}` and `GET /api/models/{id}` are not implemented and return 405. List endpoints are correctly isolated.

## Phase 5 Production Blockers

- HTTPS/TLS is not working on `synplex.xyz`.
- Public HTTP root is empty; frontend/Nginx public entry is not verified.
- Real two-model fallback is unverified.
- PostgreSQL backup/restore is unverified.
- Redis/DB/LLM fault injection is not complete.
- Email/Resend domain verification is unverified.

## Phase 5.5 New Evidence

- Production SSH is not authorized for this agent: `Permission denied (publickey,password)`.
- Public port scan shows many internal services exposed:
  - 5433 PostgreSQL
  - 6379 Redis
  - 9090 Prometheus
  - 3000 Grafana
  - 16686 Jaeger
  - 4317/4318 OTel
  - 1025/8025 MailHog
- This is a critical production firewall/security blocker.
- Production Kubernetes/TLS/DNS.
- Real SMTP/Resend provider.
- PostgreSQL backup/restore.

## MANUAL_REQUIRED

- Cloud server and DNS/HTTPS verification.
- Production secrets in external secret manager.
- Real backup recovery drill.
