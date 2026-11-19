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
#
# All or nothing (Codex completion audit, 19 Nov 2026): the dumps are written to a hidden
# .incomplete-<time> folder first. Only when all three dumps succeeded and are non-empty does
# the script write MANIFEST (sizes, SHA-256, revision) and rename the folder to <time>, so a
# backup that stopped half-way can never look like the newest complete one. verify.sh and
# restore.sh only pick folders that have a MANIFEST.
#
# Runs on the macOS system Bash (3.2) as well as Linux: no empty-array expansions under set -u.
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
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$root/$stamp"
work="$root/.incomplete-$stamp"
umask 077
mkdir -p "$root"
[ ! -e "$out" ] || { echo "FAIL  $out already exists; try again in a second"; exit 1; }
mkdir "$work"
# Anything that stops the script before the rename leaves nothing that looks like a backup.
trap 'rm -rf "$work"' EXIT

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

for db in gateway simulator merchant; do
  if [ "$db" = gateway ]; then
    # vault.vault_*: every table of the vault app (Django names them vault_<model>). The
    # schema's own vault.django_migrations keeps its rows: without them a restored gateway
    # tries to create the vault tables again and does not start (found by the restore drill,
    # 19 Nov 2026; backups made before then need the fix in RUNBOOK.md step 9b).
    docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U postgres -Fc \
      --exclude-table-data='vault.vault_*' "$db" > "$work/$db.dump"
  else
    docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U postgres -Fc "$db" > "$work/$db.dump"
  fi
  [ -s "$work/$db.dump" ] || { echo "FAIL  $db.dump is empty; no backup published"; exit 1; }
done

revision="$(git -C "$deploy/.." rev-parse HEAD 2>/dev/null || echo unknown)"
{
  echo "# SecurePay backup, complete. Written by deploy/backup/backup.sh after every dump succeeded."
  echo "created_utc=$stamp"
  echo "source_revision=$revision"
  echo "compose_file=$(basename "$COMPOSE_FILE")"
  echo "vault_rows=excluded (vault.vault_* tables: definitions only)"
  for db in gateway simulator merchant; do
    echo "dump=$db.dump bytes=$(wc -c < "$work/$db.dump" | tr -d ' ') sha256=$(sha256 "$work/$db.dump")"
  done
} > "$work/MANIFEST"
mv "$work" "$out"
trap - EXIT

# Prune only after a new complete backup exists: old complete ones past KEEP_DAYS, and
# leftovers of runs that were killed outright (kill -9, power cut) after a day.
find "$root" -mindepth 1 -maxdepth 1 -type d -name '2*' -mtime +"${KEEP_DAYS:-14}" -exec rm -rf {} +
find "$root" -mindepth 1 -maxdepth 1 -type d -name '.incomplete-*' -mtime +0 -exec rm -rf {} +
echo "backups written to $out"
