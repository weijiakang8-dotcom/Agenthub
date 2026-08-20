#!/usr/bin/env bash
# 生产安全部署：记录稳定点 → 拉取 → 构建 → 健康门禁 → 失败自动回滚。
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
COMPOSE="docker compose -f docker/docker-compose.yml"
STABLE_FILE="deploy/.last-good-commit"

previous="$(git rev-parse HEAD)"
if ! git pull --ff-only origin main; then
  echo "DEPLOY_ABORT: git pull failed; nothing changed"
  exit 1
fi

echo "$previous" > "$STABLE_FILE"

if ! $COMPOSE up -d --build backend worker frontend; then
  echo "DEPLOY_FAIL: build/up failed, rolling back to $previous"
  git checkout "$previous"
  $COMPOSE up -d --build backend worker frontend
  exit 1
fi

sleep 10
if ! bash scripts/core_health_gate.sh; then
  echo "DEPLOY_FAIL: health gate failed, rolling back to $previous"
  git checkout "$previous"
  $COMPOSE up -d --build backend worker frontend
  exit 1
fi

echo "DEPLOY_OK at $(git rev-parse --short HEAD)"
