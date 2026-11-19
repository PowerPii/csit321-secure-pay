#!/bin/bash
# Tests for deploy/backup/backup.sh with a stand-in `docker` (no database needed).
#
#   bash deploy/tests/backup-test.sh                   # with this machine's Bash
#   docker run --rm -v "$PWD:/repo:ro" bash:3.2 bash /repo/deploy/tests/backup-test.sh
#                                                      # with the Bash macOS ships (3.2)
#
# Covers the Codex completion audit (19 Nov 2026): the script must not stop after the first
# dump on Bash 3.2 ("extra[@]: unbound variable"), and a run that fails part-way must not
# leave anything that looks like the newest complete backup.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
script="$here/../backup/backup.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin"
# The stand-in: `docker compose -f X exec -T db pg_dump ... <db>` prints a fake dump of <db>,
# fails for FAIL_DB and prints nothing for EMPTY_DB. It records every call.
cat > "$tmp/bin/docker" <<'FAKE'
#!/bin/sh
echo "$*" >> "$CALLS"
for last in "$@"; do :; done
[ "$last" = "${FAIL_DB:-}" ] && { echo "pg_dump: connection lost" >&2; exit 1; }
[ "$last" = "${EMPTY_DB:-}" ] && exit 0
echo "PGDMP fake dump of $last"
FAKE
chmod +x "$tmp/bin/docker"
export PATH="$tmp/bin:$PATH" CALLS="$tmp/calls" COMPOSE_FILE=/dev/null
pass=0; fail=0
ok()  { echo "ok    $1"; pass=$((pass + 1)); }
bad() { echo "FAIL  $1"; fail=$((fail + 1)); }
complete() { ls -1d "$1"/2*/ 2>/dev/null | wc -l | tr -d ' '; }
leftovers() { ls -1d "$1"/.incomplete-* 2>/dev/null | wc -l | tr -d ' '; }
run() { "$BASH" "$script" >"$tmp/out" 2>&1; }

echo "== backup.sh tests with Bash $BASH_VERSION"

# 1. Every dump succeeds: one complete folder with three dumps and a MANIFEST.
export BACKUP_DIR="$tmp/b1"; : > "$CALLS"
if run; then ok "a full run exits 0"; else bad "a full run failed: $(cat "$tmp/out")"; fi
[ "$(complete "$BACKUP_DIR")" = 1 ] && ok "one complete folder" || bad "expected one complete folder"
d="$(ls -1d "$BACKUP_DIR"/2*/ | head -1)"
for db in gateway simulator merchant; do
  [ -s "$d/$db.dump" ] && ok "$db.dump written" || bad "$db.dump missing"
  grep -q "^dump=$db.dump bytes=[0-9]* sha256=[0-9a-f]\{64\}$" "$d/MANIFEST" \
    && ok "MANIFEST lists $db.dump" || bad "MANIFEST does not list $db.dump"
done
grep -q -- "--exclude-table-data=vault.vault_\* gateway$" "$CALLS" && ok "gateway dump leaves vault rows out" \
  || bad "gateway dump does not exclude vault rows: $(grep gateway "$CALLS")"
if grep -E "(simulator|merchant)$" "$CALLS" | grep -q exclude; then bad "other dumps exclude data"
else ok "simulator and merchant dumps are whole"; fi
[ "$(leftovers "$BACKUP_DIR")" = 0 ] && ok "no .incomplete folder left" || bad ".incomplete folder left"

# 2. The second dump fails: no new complete folder, nothing left behind, older one kept.
for case in FAIL_DB EMPTY_DB; do
  export BACKUP_DIR="$tmp/b-$case"
  mkdir -p "$BACKUP_DIR/20200101T000000Z"; touch "$BACKUP_DIR/20200101T000000Z/MANIFEST"
  touch -d "2020-01-01 00:00" "$BACKUP_DIR/20200101T000000Z"
  if env "$case=simulator" "$BASH" "$script" >"$tmp/out" 2>&1; then
    bad "$case: exits 0 though the simulator dump failed"
  else
    ok "$case: exits non-zero when the simulator dump fails"
  fi
  [ "$(complete "$BACKUP_DIR")" = 1 ] && [ -d "$BACKUP_DIR/20200101T000000Z" ] \
    && ok "$case: only the older complete backup is there (and it was not pruned)" \
    || bad "$case: a partial backup was published or the old one pruned: $(ls -a "$BACKUP_DIR")"
  [ "$(leftovers "$BACKUP_DIR")" = 0 ] && ok "$case: the partial folder was removed" \
    || bad "$case: .incomplete folder left behind"
done

# 3. After a successful run, complete backups past KEEP_DAYS and stale leftovers are pruned.
export BACKUP_DIR="$tmp/b3"
mkdir -p "$BACKUP_DIR/20200101T000000Z" "$BACKUP_DIR/.incomplete-20200101T000000Z"
touch -d "2020-01-01 00:00" "$BACKUP_DIR/20200101T000000Z" "$BACKUP_DIR/.incomplete-20200101T000000Z"
run || bad "run with old folders failed: $(cat "$tmp/out")"
[ ! -e "$BACKUP_DIR/20200101T000000Z" ] && ok "old complete backup pruned" || bad "old backup kept"
[ "$(leftovers "$BACKUP_DIR")" = 0 ] && ok "stale .incomplete folder pruned" || bad "stale leftover kept"
[ "$(complete "$BACKUP_DIR")" = 1 ] && ok "the new backup is there" || bad "new backup missing"

echo "== $pass passed, $fail failed"
[ "$fail" -eq 0 ]
