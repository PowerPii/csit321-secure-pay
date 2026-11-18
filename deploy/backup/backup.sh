#!/bin/bash
# Dump all three databases to a dated folder outside the app directory, and keep the last
# KEEP_DAYS days. Works for the local stack and the public server:
#   deploy/backup/backup.sh                           # compose.prod.yaml if deploy/.env sets DOMAIN
#   COMPOSE_FILE=deploy/compose.yaml deploy/backup/backup.sh
# Nightly on the server (RUNBOOK.md step 9):
#   15 18 * * * /home/securepay/csit321-secure-pay/deploy/backup/backup.sh >> /home/securepay/backup.log 2>&1
# Dumps hold payment records and are only useful together with the secrets, which are not
# copied here. They never hold card data: the vault schema's rows (encrypted card numbers and
# security codes, kept only between card entry and submission) are left out and only its
# table definitions are dumped, so a deleted card cannot live on in a backup (Codex release
# review, 18 Nov 2026). A payment in progress when the backup ran needs its card entered again
# after a restore.
set -euo pipefail
deploy="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "${COMPOSE_FILE:-}" ]; then
  # The server's deploy/.env sets DOMAIN; a laptop's may hold only RISK_MODEL_VERSION.
  if grep -qE '^DOMAIN=.+' "$deploy/.env" 2>/dev/null; then
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
  extra=()
  [ "$db" = gateway ] && extra=(--exclude-table-data='vault.*')
  docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U postgres -Fc "${extra[@]}" "$db" > "$out/$db.dump"
done
find "$root" -mindepth 1 -maxdepth 1 -type d -mtime +"${KEEP_DAYS:-14}" -exec rm -rf {} +
echo "backups written to $out"
