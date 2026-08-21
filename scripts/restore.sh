#!/usr/bin/env bash
set -euo pipefail

# AgentHub PostgreSQL 恢复脚本。
# 用法：bash scripts/restore.sh <备份文件.sql.gz> [目标库]（默认 agenthub_restore）
#
# 警告：恢复会覆盖目标数据库。生产恢复前必须确认目标库名。

BACKUP_FILE="${1:?usage: restore.sh <backup.sql.gz> [target_db]}"
TARGET_DB="${2:-agenthub_restore}"
CONTAINER="${AGENTHUB_PG_CONTAINER:-agenthub-postgres}"
PG_USER="${POSTGRES_USER:-postgres}"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

echo "restoring $BACKUP_FILE -> $TARGET_DB"
docker exec "$CONTAINER" dropdb -U "$PG_USER" --if-exists "$TARGET_DB" >/dev/null 2>&1 || true
docker exec "$CONTAINER" createdb -U "$PG_USER" "$TARGET_DB"
gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER" psql -U "$PG_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1 >/dev/null
echo "restore ok: $TARGET_DB"
