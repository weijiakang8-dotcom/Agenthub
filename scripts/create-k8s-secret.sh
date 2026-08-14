#!/usr/bin/env bash
set -euo pipefail

# 从本地 .env 读取真实密钥并创建 K8s Secret（不把真实值写入仓库）。
NAMESPACE="${NAMESPACE:-agenthub}"
ENV_FILE="${ENV_FILE:-.env}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 ${ENV_FILE}，请先 cp .env.example .env 并填写密钥" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

kubectl -n "$NAMESPACE" create secret generic agenthub-secrets \
  --from-literal=POSTGRES_USER="${POSTGRES_USER:-postgres}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}" \
  --from-literal=DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:postgres@postgres:5432/agenthub}" \
  --from-literal=REDIS_URL="${REDIS_URL:-redis://redis:6379/0}" \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
  --from-literal=ADMIN_API_KEY="${ADMIN_API_KEY:-}" \
  --from-literal=TAVILY_API_KEY="${TAVILY_API_KEY:-}" \
  --from-literal=SMTP_USERNAME="${SMTP_USERNAME:-}" \
  --from-literal=SMTP_PASSWORD="${SMTP_PASSWORD:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secret agenthub-secrets 已从本地 .env 安全创建（真实值未写入仓库）。"
