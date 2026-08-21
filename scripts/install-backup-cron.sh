#!/usr/bin/env bash
set -euo pipefail

# 安装每日备份 cron（03:00 Asia/Shanghai，保留最近 7 份）。
# 用法：bash scripts/install-backup-cron.sh [仓库目录]（默认 ~/agenthub）

REPO_DIR="${1:-$HOME/agenthub}"
BACKUP_DIR="$HOME/backups"
mkdir -p "$BACKUP_DIR"
CRON_LINE="0 3 * * * cd \"$REPO_DIR\" && bash scripts/backup.sh \"$BACKUP_DIR\" >> \"$BACKUP_DIR/backup.log\" 2>&1"

(
  crontab -l 2>/dev/null | grep -v "scripts/backup.sh" || true
  echo "$CRON_LINE"
) | crontab -

echo "installed backup cron:"
crontab -l | grep "scripts/backup.sh"
