#!/bin/bash
# Dump all three databases to a dated folder outside the app directory, and keep the last
# KEEP_DAYS days. Works for the local stack and the public server:
#   deploy/backup/backup.sh                           # compose.prod.yaml if deploy/.env exists
#   COMPOSE_FILE=deploy/compose.yaml deploy/backup/backup.sh
# Nightly on the server (RUNBOOK.md step 9):
#   15 18 * * * /home/securepay/csit321-secure-pay/deploy/backup/backup.sh >> /home/securepay/backup.log 2>&1
# Dumps hold payment records (no card data: the vault keeps only encrypted, short-lived
# rows) and are only useful together with the secrets, which are not copied here.
set -euo pipefail
deploy="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "${COMPOSE_FILE:-}" ]; then
  if [ -e "$deploy/.env" ] && [ -e "$deploy/compose.prod.yaml" ]; then
    COMPOSE_FILE="$deploy/compose.prod.yaml"
  else
    COMPOSE_FILE="$deploy/compose.yaml"
  fi
fi
root="${BACKUP_DIR:-$HOME/fyp-backups}"
out="$root/$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$out"
for db in gateway simulator merchant; do
  docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U postgres -Fc "$db" > "$out/$db.dump"
done
find "$root" -mindepth 1 -maxdepth 1 -type d -mtime +"${KEEP_DAYS:-14}" -exec rm -rf {} +
echo "backups written to $out"
