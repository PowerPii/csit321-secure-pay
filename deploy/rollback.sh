#!/bin/bash
# Go back to an earlier commit on main after a bad deploy (RUNBOOK.md section 10b,
# docs/RECOVERY.md). Run on the server as the securepay user:
#
#   bash deploy/rollback.sh                 # the revision that ran before the newest deploy
#   bash deploy/rollback.sh <commit>        # any older commit on main (40 characters)
#   bash deploy/rollback.sh --allow-migrations <commit>   # see "Migrations" below
#
# What it does:
#   1. picks the target: by default the "previous" revision of the newest deploy record in
#      ~/deploy-history.jsonl (release-record.sh); refuses a commit that is not an older
#      commit on main;
#   2. refuses if a database migration was added between the target and what runs now,
#      unless --allow-migrations (Migrations below);
#   3. checks the target out (detached; main itself is not moved), rebuilds and restarts the
#      services labelled with that commit, checks every app container runs it, records the
#      revision and image digests, then runs the smoke check and the recovery check (an
#      existing payment still agrees with the simulator).
#
# Moving forward again: the next deploy (a merge, or deploy/auto-deploy.sh by hand) returns
# the clone to main. If the bad commit is still the newest on main, freeze deploys first
# (deploy/freeze.sh on) so a merge of something unrelated does not bring it back.
#
# Migrations: Django migrations are applied on start and are not undone by checking out old
# code. If the target is older than a migration, the old code meets a newer schema; added
# tables and nullable columns are harmless, but a removed or renamed column or a NOT NULL
# column without a default breaks it. Read the listed migrations; if they only add, pass
# --allow-migrations. Otherwise restore the backup taken before the bad deploy instead
# (deploy/backup/restore.sh), which brings back the old schema with the data.
set -euo pipefail

main() {
  local repo target allow now domain
  allow=0; target=""
  for arg in "$@"; do
    case "$arg" in
      --allow-migrations) allow=1 ;;
      -h|--help) sed -n '2,32p' "$0"; return 0 ;;
      *) target="$arg" ;;
    esac
  done
  repo="$(cd "$(dirname "$0")/.." && pwd)"
  cd "$repo"
  export COMPOSE_FILE="${COMPOSE_FILE:-$repo/deploy/compose.prod.yaml}"
  # The target commit may predate release-record.sh: keep this copy for after the checkout.
  tmp="$(mktemp -d)"  # global: the EXIT trap runs after main() returns
  trap 'rm -rf "$tmp"' EXIT
  cp deploy/release-record.sh "$tmp/release-record.sh"
  record() { bash "$tmp/release-record.sh" "$@"; }

  # One deploy or rollback at a time (macOS has no flock: a laptop rehearsal runs without).
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$HOME/.securepay-deploy.lock"
    flock -w 900 9 || { echo "a deploy is still running"; return 1; }
  fi
  exec > >(tee -a "$HOME/deploy.log") 2>&1
  echo "=== rollback $(date -u +%Y-%m-%dT%H:%M:%SZ)"

  now="$(git rev-parse HEAD)"
  if [ -z "$target" ]; then
    target="$(record previous || true)"
    [ -n "$target" ] || { echo "no earlier deploy recorded; name the commit: rollback.sh <commit>"; return 2; }
    echo "no commit named: going back to the revision before the newest deploy"
  fi
  [[ "$target" =~ ^[0-9a-f]{40}$ ]] || { echo "refusing: give a full 40-character commit"; return 2; }
  git fetch --quiet origin main
  if ! git merge-base --is-ancestor "$target" origin/main; then
    echo "refusing: $target is not a commit on main"; return 1
  fi
  if [ "$target" = "$now" ]; then echo "already running $target; nothing to do"; return 0; fi
  if ! git merge-base --is-ancestor "$target" "$now"; then
    echo "refusing: $target is not older than what runs now ($now); deploy it with auto-deploy.sh"; return 1
  fi
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "the server clone has local changes; fix by hand (git status)"; return 1
  fi

  migrations="$(git diff --name-only --diff-filter=A "$target" "$now" -- '*/migrations/0*.py')"
  if [ -n "$migrations" ]; then
    echo "migrations added since $target:"; echo "$migrations" | sed 's/^/  /'
    if [ $allow -eq 0 ]; then
      echo "refusing: the old code would meet a newer schema. Read them; if they only add"
      echo "tables or nullable columns, run again with --allow-migrations. Otherwise restore"
      echo "the backup taken before the bad deploy (deploy/backup/restore.sh)."
      return 1
    fi
    echo "--allow-migrations: going ahead; the schema stays as it is"
  fi

  echo "code: ${now:0:12} -> ${target:0:12} ($target)"
  git checkout --quiet --detach "$target"
  echo "rollback from $now on $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$HOME/.securepay-rolled-back"
  GIT_REVISION="$target" docker compose -f "$COMPOSE_FILE" up -d --build --remove-orphans
  if ! record check "$target"; then
    record record rollback-failed "$target" "$now" >/dev/null || true
    echo "=== rollback to $target FAILED the revision check"; return 1
  fi
  echo "$target" > "$HOME/deployed-revision"
  record record rollback "$target" "$now"

  if [ "$(basename "$COMPOSE_FILE")" = compose.prod.yaml ]; then
    domain="$(sed -n 's/^DOMAIN=//p' deploy/.env | tr -d "\"' ")"
    for _ in $(seq 1 18); do
      bash deploy/smoke-check.sh "$domain" >"$tmp/smoke.txt" 2>&1 && break
      sleep 10
    done
    cat "$tmp/smoke.txt"
  else
    for _ in $(seq 1 60); do
      docker compose -f "$COMPOSE_FILE" exec -T gateway python manage.py migrate --check >/dev/null 2>&1 && break
      sleep 3
    done
  fi
  # recovery_check only exists from 19 Nov 2026 on; older targets skip it.
  if docker compose -f "$COMPOSE_FILE" exec -T gateway python manage.py help recovery_check >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" exec -T gateway python manage.py recovery_check --payments 10
  else
    echo "(this revision has no recovery_check; check one payment by hand: docs/RECOVERY.md)"
  fi
  echo "=== rolled back to ${target:0:12}. Freeze deploys if main still holds the bad commit:"
  echo "    bash deploy/freeze.sh on 24"
}

# Everything is inside main(), so bash has read the whole script before git replaces this file.
main "$@"
