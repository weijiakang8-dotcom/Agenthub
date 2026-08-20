#!/usr/bin/env bash
# Staging 预发布：独立 compose 项目，全部内部端口，先验证再提示上线。
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
docker compose -f docker/docker-compose.staging.yml up -d --build
sleep 8

STATUS=$(curl -fsS http://127.0.0.1:8001/health || true)
echo "staging health: ${STATUS:-unavailable}"
if ! curl -fsS http://127.0.0.1:8001/health >/dev/null; then
  echo "STAGING_FAIL: health check failed"
  exit 1
fi
echo "STAGING_OK: backend=127.0.0.1:8001 frontend=127.0.0.1:8081"
