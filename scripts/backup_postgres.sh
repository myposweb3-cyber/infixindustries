#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.production}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
DB_CONTAINER="${DB_CONTAINER:-pos_db}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing environment file: $ENV_FILE" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Load only the deployment variables needed by the database container.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

backup_name="pos_db_$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
tmp_file="$BACKUP_DIR/.${backup_name}.tmp"
final_file="$BACKUP_DIR/$backup_name"
trap 'rm -f "$tmp_file"' EXIT

if ! docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q '^true$'; then
    echo "Database container is not running: $DB_CONTAINER" >&2
    exit 1
fi

docker exec "$DB_CONTAINER" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --no-owner --no-privileges --format=plain --dbname="$POSTGRES_DB" --username="$POSTGRES_USER"' | gzip -9 > "$tmp_file"

if [[ ! -s "$tmp_file" ]]; then
    echo "Backup output is empty; refusing to publish it" >&2
    exit 1
fi

mv -f "$tmp_file" "$final_file"
chmod 600 "$final_file"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'pos_db_*.sql.gz' -mtime "+$RETENTION_DAYS" -delete

printf 'Backup created: %s\n' "$final_file"
