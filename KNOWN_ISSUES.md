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
- Production Kubernetes/TLS/DNS.
- Real SMTP/Resend provider.
- PostgreSQL backup/restore.

## MANUAL_REQUIRED

- Cloud server and DNS/HTTPS verification.
- Production secrets in external secret manager.
- Real backup recovery drill.
