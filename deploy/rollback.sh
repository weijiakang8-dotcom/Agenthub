#!/usr/bin/env bash
# 手动/自动回滚：回到上一个稳定提交并重建，健康门禁兜底。
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
COMPOSE="docker compose -f docker/docker-compose.yml"
STABLE_FILE="deploy/.last-good-commit"

target="${1:-$(cat "$STABLE_FILE" 2>/dev/null)}"
if [ -z "$target" ]; then
  echo "rollback: no target commit (pass -- <sha> or deploy/.last-good-commit)"
  exit 1
fi

current="$(git rev-parse HEAD)"
git checkout --force "$target" || exit 1
if ! $COMPOSE up -d --build backend worker frontend embedding; then
  echo "rollback build failed; restoring $current"
  git checkout --force "$current"
  $COMPOSE up -d --build backend worker frontend embedding
  exit 1
fi
$COMPOSE restart frontend
sleep 10
if ! bash scripts/core_health_gate.sh; then
  echo "rollback health failed; restoring $current"
  git checkout --force "$current"
  $COMPOSE up -d --build backend worker frontend embedding
  $COMPOSE restart frontend
  exit 1
fi
echo "ROLLBACK_OK to $(git rev-parse --short HEAD)"
