#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this installer as root." >&2
    exit 1
fi

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_SCRIPT="$PROJECT_DIR/scripts/backup_postgres.sh"
CRON_FILE="/etc/cron.d/infixindustries-pos-backup"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/backups/backup.log}"

if [[ ! -x "$BACKUP_SCRIPT" ]]; then
    echo "Backup script is missing or not executable: $BACKUP_SCRIPT" >&2
    exit 1
fi

mkdir -p "$PROJECT_DIR/backups"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

cat > "$CRON_FILE" <<EOF
# Infix Industries POS PostgreSQL backup — daily at 02:30 UTC
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
30 2 * * * root flock -n /var/lock/infixindustries-pos-backup.lock "$BACKUP_SCRIPT" >> "$LOG_FILE" 2>&1
EOF

chmod 644 "$CRON_FILE"

echo "Installed daily backup schedule: $CRON_FILE"
