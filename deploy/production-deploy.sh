#!/usr/bin/env bash
# 生产安全部署：记录稳定点 → 拉取 → 构建 → 健康门禁 → 失败自动回滚。
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
COMPOSE="docker compose -f docker/docker-compose.yml"
# 4C/4G 生产机并行构建 backend/frontend 会触发长时间资源饥饿；串行构建换稳定性。
export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}"
STABLE_FILE="deploy/.last-good-commit"

if ! git fetch origin main || ! git reset --hard origin/main; then
  echo "DEPLOY_ABORT: sync to origin/main failed; nothing changed"
  exit 1
fi
git checkout -B main origin/main

# 回滚目标 = 上一个 GitHub main 提交（patch 时代码分叉时也能正确回退）
previous="$(git rev-parse 'origin/main@{1}' 2>/dev/null || git rev-parse HEAD~1)"
echo "$previous" > "$STABLE_FILE"

if ! $COMPOSE up -d --build backend worker frontend embedding; then
  echo "DEPLOY_FAIL: build/up failed, rolling back to $previous"
  git checkout --force "$previous"
  $COMPOSE up -d --build backend worker frontend embedding
  exit 1
fi

# backend 重建后容器 IP 可能变化，必须重启 frontend 刷新 nginx 上游 DNS
$COMPOSE restart frontend

sleep 10
if ! bash scripts/core_health_gate.sh; then
  echo "DEPLOY_FAIL: health gate failed, rolling back to $previous"
  git checkout --force "$previous"
  $COMPOSE up -d --build backend worker frontend embedding
  $COMPOSE restart frontend
  exit 1
fi

echo "DEPLOY_OK at $(git rev-parse --short HEAD)"
