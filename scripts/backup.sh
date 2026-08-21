#!/usr/bin/env bash
set -euo pipefail

# AgentHub PostgreSQL 备份脚本（生产：容器内 pg_dump）。
# 用法：bash scripts/backup.sh [备份目录]（默认 /backups）
#
# 只读备份；不会修改生产数据。备份文件名含时间戳，保留最近 7 份。

BACKUP_DIR="${1:-/backups}"
CONTAINER="${AGENTHUB_PG_CONTAINER:-agenthub-postgres}"
PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-agenthub}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/agenthub-$TS.sql.gz"

echo "backing up $PG_DB -> $OUT"
docker exec "$CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" --no-owner --no-privileges \
  | gzip > "$OUT"

SIZE="$(du -h "$OUT" | cut -f1)"
echo "backup ok: $OUT ($SIZE)"

# 保留最近 7 份
ls -1t "$BACKUP_DIR"/agenthub-*.sql.gz 2>/dev/null | tail -n +8 | while read -r OLD; do
  echo "pruning $OLD"
  rm -f "$OLD"
done
