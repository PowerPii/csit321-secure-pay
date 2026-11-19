#!/bin/bash
# Put a backup made by backup.sh back into the running stack's databases (RUNBOOK.md step 9b).
#
#   deploy/backup/restore.sh                       # newest complete backup, local stack
#   deploy/backup/restore.sh ~/fyp-backups/20270401T181500Z
#   deploy/backup/restore.sh --replace-live-data   # required on the public server
#
# What it does, in order:
#   1. checks the folder is a complete backup (MANIFEST written by backup.sh, checksums match)
#      and that it restores into scratch databases (verify.sh), before anything is touched;
#   2. takes a safety backup of the current data (backup.sh), so the restore can be undone;
#   3. stops the apps (the database, Caddy and Mailpit stay up) and restores all three
#      databases together, so the gateway and the simulator agree about every payment;
#   4. starts the apps again and waits until the gateway answers with its migrations applied;
#   5. prints what came back: payments by status, open operations, and the vault row count,
#      which must be 0 (backups never hold card data). A payment that was between card entry
#      and submission when the backup ran is still there, but its card is not: the payment
#      page asks for the card again (checkout/service.py, "Please enter your card details
#      again"). Nothing is charged twice: the simulator's own records came back with it.
#
# Restoring overwrites everything written since the backup: payments, refunds, staff
# changes and audit entries made after it are gone (the safety backup still has them).
# The secrets must be the ones the backup was made with (RUNBOOK.md step 4), or encrypted
# fields such as webhook signing secrets cannot be read.
set -euo pipefail
deploy="$(cd "$(dirname "$0")/.." && pwd)"
here="$deploy/backup"
live=0
dir=""
for arg in "$@"; do
  case "$arg" in
    --replace-live-data) live=1 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    -*) echo "unknown option $arg"; exit 2 ;;
    *) dir="$arg" ;;
  esac
done
if [ -z "${COMPOSE_FILE:-}" ]; then
  if grep -qE '^DOMAIN=.+' "$deploy/.env" 2>/dev/null; then
    COMPOSE_FILE="$deploy/compose.prod.yaml"
  else
    COMPOSE_FILE="$deploy/compose.yaml"
  fi
fi
export COMPOSE_FILE
if [ "$(basename "$COMPOSE_FILE")" = compose.prod.yaml ] && [ $live -eq 0 ]; then
  echo "This is the public server (compose.prod.yaml). Restoring replaces its live data."
  echo "Run again with --replace-live-data if that is what you want (RUNBOOK.md step 9b)."
  exit 2
fi
C() { docker compose -f "$COMPOSE_FILE" "$@"; }
psql() { C exec -T -e PGOPTIONS='-c client_min_messages=warning' db psql -U postgres -v ON_ERROR_STOP=1 -qAt "$@"; }

root="${BACKUP_DIR:-$HOME/fyp-backups}"
if [ -z "$dir" ]; then
  for d in $(ls -1d "$root"/2*/ 2>/dev/null | sort -r); do
    [ -f "${d}MANIFEST" ] && { dir="${d%/}"; break; }
  done
fi
dir="${dir%/}"
[ -n "$dir" ] && [ -f "$dir/MANIFEST" ] || { echo "FAIL  no complete backup (folder with a MANIFEST) to restore"; exit 1; }
start=$(date +%s)
echo "== Restore of $dir into $(basename "$COMPOSE_FILE") ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
sed -n 's/^source_revision=/   made while running /p; s/^created_utc=/   taken at /p' "$dir/MANIFEST"

echo "-- 1. checking the backup restores into scratch databases"
bash "$here/verify.sh" "$dir" || { echo "FAIL  the backup did not pass verify.sh; nothing was changed"; exit 1; }

echo "-- 2. safety backup of the current data"
if [ "${SKIP_SAFETY_BACKUP:-0}" = 1 ]; then
  echo "   skipped (SKIP_SAFETY_BACKUP=1)"
else
  BACKUP_DIR="$root/safety" bash "$here/backup.sh"
fi

echo "-- 3. stopping the apps and restoring the three databases"
apps="$(C config --services | grep -vxE 'db|caddy|mailpit|integration-tests' | tr '\n' ' ')"
# shellcheck disable=SC2086  # one word per service
C stop $apps
for db in gateway simulator merchant; do
  psql -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                       WHERE datname = '$db' AND pid <> pg_backend_pid()" >/dev/null
  C exec -T db pg_restore -U postgres --clean --if-exists --exit-on-error -d "$db" < "$dir/$db.dump"
  echo "   restored $db"
done

echo "-- 4. starting the apps"
# shellcheck disable=SC2086
C up -d --no-build $apps
ready=0
for _ in $(seq 1 60); do
  if C exec -T gateway python manage.py migrate --check >/dev/null 2>&1; then ready=1; break; fi
  sleep 3
done
[ $ready -eq 1 ] || { echo "FAIL  the gateway did not come back within 3 minutes (logs: docker compose logs gateway)"; exit 1; }
# Ready = its databases answer and the worker has written a fresh heartbeat (GET /readyz).
ready=0
for _ in $(seq 1 60); do
  # Over HTTP inside the container, so gunicorn is serving too (port 8002 on the server's
  # compose.prod.yaml, 8000 on the laptop's compose.yaml).
  if C exec -T gateway python -c "
import sys, urllib.request as u
for port in (8002, 8000):
    try:
        u.urlopen(u.Request(f'http://127.0.0.1:{port}/readyz', headers={'Host': 'gateway', 'X-Forwarded-Proto': 'https'}), timeout=5)
        sys.exit(0)
    except Exception:
        pass
sys.exit(1)" >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 3
done
[ $ready -eq 1 ] || { echo "FAIL  the gateway is up but not ready after 3 more minutes (is gateway-worker running?)"; exit 1; }

echo "-- 5. what came back"
psql -d gateway -F ' ' -c "SELECT status, count(*) FROM payments_payment GROUP BY 1 ORDER BY 1" \
  | sed 's/^/   payments /'
psql -d gateway -c "SELECT count(*) FROM payments_operation WHERE status IN ('pending','unresolved')" \
  | sed 's/^/   open operations (reconciliation will check them): /'
cards="$(psql -d gateway -c "SELECT count(*) FROM vault.vault_storedcard")"
echo "   vault rows: $cards"
[ "$cards" = 0 ] || { echo "FAIL  the restored gateway holds $cards stored card(s)"; exit 1; }
echo "== Restored $dir in $(( $(date +%s) - start )) s. Payments that were waiting for card"
echo "   submission ask for the card again. Run: bash deploy/recovery-check.sh"
