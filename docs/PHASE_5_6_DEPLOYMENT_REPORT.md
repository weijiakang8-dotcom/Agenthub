# Phase 5.6 Production Deployment Report

Date: 2026-08-16

## 1. Deployment Before/After

- Before commit: `62e4e6c`
- After commit: `3c045e5`
- Deploy command: `docker compose -f docker/docker-compose.yml up -d --build`
- No `down`, no `down -v`, no volume removal.

## 2. Backup

- PostgreSQL backup file:
  - `/home/ubuntu/agenthub_backup_2026-08-16_131313.sql`
  - Size: 53K
  - Verified non-empty via `tail`

## 3. Docker Status

All core containers running after deploy:

- backend
- worker
- frontend
- postgres
- redis
- grafana
- prometheus
- jaeger
- otel-collector
- mailhog

## 4. Final Port State

Internal services now bind `127.0.0.1`:

- `8000` backend
- `5433` postgres
- `6379` redis
- `3000` grafana
- `9090` prometheus
- `16686` / `14250` jaeger
- `4317` / `4318` / `9464` otel
- `1025` / `8025` mailhog

Still public:

- `443` frontend HTTPS
- `8080` frontend HTTP preview
- `22` SSH

## 5. HTTPS

- Server local HTTPS `https://127.0.0.1/`: 200
- Domain HTTPS `https://synplex.xyz`: 200
- Domain HTTP `http://synplex.xyz`: connection refused

Remaining issue:

- Port 80 is not published.
- Nginx has no HTTP→HTTPS redirect.

## 6. Smoke Test

- Backend `/health`: PASS
- Frontend HTTPS homepage: PASS
- Document create: PASS
- RAG search: PASS
- Workflow create: PASS
- Execution real LLM: PASS
- Approval/resume: PASS

## 7. Data Preservation

- PostgreSQL volume: `docker_postgres_data`
- Redis volume: `docker_redis_data`
- Volumes preserved during `up -d --build`.

## 8. Errors Encountered

### First extended smoke timed out

- Symptom: `httpx.ReadTimeout` in early document/workflow smoke
- Likely cause: backend was still loading sentence-transformers weights / startup warm-up
- Resolution: reran simplified smoke after backend health and warm-up
- Result: PASS

## 9. Remaining Blockers

- Port `8080` still public; should be closed or mapped to localhost unless explicitly used.
- HTTP port `80` not published and no redirect.
- Tencent Cloud security group still needs to close external access to previously exposed ports.
- Real two-model fallback still unverified.
- Backup restore drill still unverified.

## 10. Next Steps

1. Close `8080` from public or change Compose to `127.0.0.1:8080:80`.
2. Add port `80:80` mapping and HTTP→HTTPS redirect after confirming Nginx config.
3. Update Tencent Cloud security group.
4. Configure and verify real fallback model.
5. Perform backup restore drill.
