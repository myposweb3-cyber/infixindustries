#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.production}"
DB_CONTAINER="${DB_CONTAINER:-pos_db}"

if [[ $EUID -ne 0 ]]; then
    echo "Run this restore command as root." >&2
    exit 1
fi

if [[ $# -ne 2 || "$1" != "--confirm" ]]; then
    echo "Usage: $0 --confirm /absolute/path/to/pos_db_YYYYMMDDTHHMMSSZ.sql.gz" >&2
    echo "Create a fresh backup before restoring. This operation changes application data." >&2
    exit 2
fi

backup_file="$2"
if [[ ! -f "$backup_file" ]]; then
    echo "Backup file not found: $backup_file" >&2
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing environment file: $ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if ! docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q '^true$'; then
    echo "Database container is not running: $DB_CONTAINER" >&2
    exit 1
fi

case "$backup_file" in
    *.sql.gz) gzip -dc "$backup_file" ;;
    *.sql) cat "$backup_file" ;;
    *) echo "Restore accepts only .sql or .sql.gz files" >&2; exit 1 ;;
esac | docker exec -i "$DB_CONTAINER" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql --set ON_ERROR_STOP=1 --dbname="$POSTGRES_DB" --username="$POSTGRES_USER"'

printf 'Restore completed from: %s\n' "$backup_file"
