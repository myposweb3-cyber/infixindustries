# Production Operations Guide

This guide describes the minimum operational controls required for a reliable customer deployment of the Infix Industries POS.

## Database backups

The repository includes `scripts/backup_postgres.sh`. It creates a compressed plain-SQL backup from the running `pos_db` container, writes to a temporary file first, atomically publishes the completed file, restricts file permissions, and removes backups older than the configured retention period.

On the production server, run:

```bash
cd /home/appuser/infixindustries
chmod 700 scripts/backup_postgres.sh scripts/restore_postgres.sh scripts/install_backup_cron.sh
mkdir -p backups
./scripts/backup_postgres.sh
```

To install a daily 02:30 UTC backup schedule:

```bash
cd /home/appuser/infixindustries
./scripts/install_backup_cron.sh
cat /etc/cron.d/infixindustries-pos-backup
```

Backups stored on the same server protect against application mistakes and container recreation, but they do not protect against server loss. For a customer deployment, copy encrypted backup files to a separate storage location and periodically test a restore on a separate database.

## Restore procedure

A restore is a data-changing operation. Create a fresh backup first, stop active sales, and confirm the selected file with the business owner. The restore script requires the explicit `--confirm` flag and does not remove the Docker volume.

```bash
cd /home/appuser/infixindustries
./scripts/backup_postgres.sh
./scripts/restore_postgres.sh --confirm /home/appuser/infixindustries/backups/pos_db_YYYYMMDDTHHMMSSZ.sql.gz
docker compose -f docker-compose.production.yml up -d
```

After a restore, verify a customer, product, historical sale, stock quantity, and report total before reopening the POS.

## Release checklist

Before a production release, pull the intended GitHub commit, validate the Compose file, build the image, restart only after a fresh backup, and verify the health endpoint and HTTPS URL.

```bash
cd /home/appuser/infixindustries
git pull origin main
docker compose -f docker-compose.production.yml config
docker compose -f docker-compose.production.yml up -d --build --force-recreate
docker compose -f docker-compose.production.yml ps
curl -fsS https://pos.infixindustries.com/health
curl -I https://pos.infixindustries.com/
```

Never use `docker compose down -v` in production. Removing volumes can destroy the database.
