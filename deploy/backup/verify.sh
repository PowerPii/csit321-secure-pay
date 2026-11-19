#!/bin/bash
# Prove the newest backup can be restored (demo sprint 16, RUNBOOK.md step 9). Restores each
# dump into a scratch database in the same Postgres (restorecheck_gateway and so on), counts
# the tables and rows, then drops the scratch databases. The live databases are not touched.
#
#   deploy/backup/verify.sh                         # newest folder in ~/fyp-backups
#   deploy/backup/verify.sh ~/fyp-backups/20270401T181500Z
#
# Weekly on the server (Sunday 03:30 Singapore time), next to the nightly backup:
#   30 19 * * 6 /home/securepay/csit321-secure-pay/deploy/backup/verify.sh >> /home/securepay/backup.log 2>&1
# Exit code 0 = every dump restored and has rows.
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
# The newest complete backup: backup.sh writes MANIFEST last, after every dump succeeded, and
# publishes the folder only then (hidden .incomplete-* folders are never picked).
newest_complete() {
  local d
  for d in $(ls -1d "$root"/2*/ 2>/dev/null | sort -r); do
    [ -f "${d}MANIFEST" ] && { echo "${d%/}"; return 0; }
  done
  return 0
}
dir="${1:-$(newest_complete)}"
dir="${dir%/}"
[ -n "$dir" ] && [ -d "$dir" ] || { echo "FAIL  no complete backup folder (with a MANIFEST) found in $root"; exit 1; }

psql() { docker compose -f "$COMPOSE_FILE" exec -T -e PGOPTIONS='-c client_min_messages=warning' db psql -U postgres -v ON_ERROR_STOP=1 -qAt "$@"; }

echo "== Restore test of $dir ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
fail=0
sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}
if [ ! -f "$dir/MANIFEST" ]; then
  echo "FAIL  $dir has no MANIFEST: it was not completed by backup.sh (or predates 19 Nov 2026)"; fail=1
else
  while read -r entry _ digest; do
    name="${entry#dump=}"; digest="${digest#sha256=}"
    if [ ! -f "$dir/$name" ] || [ "$(sha256 "$dir/$name")" != "$digest" ]; then
      echo "FAIL  $name does not match its MANIFEST checksum"; fail=1
    fi
  done < <(grep '^dump=' "$dir/MANIFEST")
  [ $fail -eq 0 ] && echo "ok    MANIFEST: $(grep -c '^dump=' "$dir/MANIFEST") dumps match their checksums ($(sed -n 's/^source_revision=//p' "$dir/MANIFEST" | cut -c1-12))"
fi
for db in gateway simulator merchant; do
  scratch="restorecheck_$db"
  if [ ! -s "$dir/$db.dump" ]; then
    echo "FAIL  $db: $db.dump missing or empty"; fail=1; continue
  fi
  psql -d postgres -c "DROP DATABASE IF EXISTS $scratch" -c "CREATE DATABASE $scratch" >/dev/null
  # --no-owner/--no-acl: the scratch copy belongs to postgres; the app roles never see it.
  if ! docker compose -f "$COMPOSE_FILE" exec -T db \
       pg_restore -U postgres --no-owner --no-acl --exit-on-error -d "$scratch" < "$dir/$db.dump"; then
    echo "FAIL  $db: pg_restore stopped (see above)"; fail=1
  else
    psql -d "$scratch" -c "ANALYZE" >/dev/null
    read -r tables rows < <(psql -d "$scratch" -F ' ' -c "
      SELECT count(*), coalesce(sum(greatest(c.reltuples, 0))::bigint, 0)
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')")
    if [ "$tables" -gt 0 ] && [ "$rows" -gt 0 ]; then
      echo "ok    $db: $tables tables, about $rows rows restored"
    else
      echo "FAIL  $db: restored, but $tables tables and $rows rows"; fail=1
    fi
    if [ "$db" = gateway ]; then
      # Card data must never be in a backup (backup.sh leaves the vault rows out).
      cards="$(psql -d "$scratch" -c "SELECT CASE WHEN to_regclass('vault.vault_storedcard') IS NULL
        THEN -1 ELSE (SELECT count(*) FROM vault.vault_storedcard) END")"
      if [ "$cards" = -1 ]; then
        echo "FAIL  gateway: the vault table is missing from the backup"; fail=1
      elif [ "$cards" != 0 ]; then
        echo "FAIL  gateway: the backup holds $cards stored card(s); make backups with the current backup.sh"; fail=1
      else
        echo "ok    gateway: vault table present and empty (no card data in the backup)"
      fi
      # The vault's own migration history must be there, or the restored gateway tries to
      # create the vault tables again and does not start.
      vmig="$(psql -d "$scratch" -c "SELECT CASE WHEN to_regclass('vault.django_migrations') IS NULL
        THEN 0 ELSE (SELECT count(*) FROM vault.django_migrations) END")"
      if [ "$vmig" = 0 ]; then
        echo "FAIL  gateway: the vault's migration history is missing; restore needs RUNBOOK.md step 9b's fix"; fail=1
      else
        echo "ok    gateway: vault migration history present ($vmig rows)"
      fi
    fi
  fi
  psql -d postgres -c "DROP DATABASE IF EXISTS $scratch" >/dev/null
done
[ $fail -eq 0 ] && echo "== Backup $dir restores." || echo "== Backup $dir FAILED the restore test."
exit $fail
