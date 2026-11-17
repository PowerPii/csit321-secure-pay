#!/bin/bash
# Move the whole SecurePay stack to a new server and/or domain (RUNBOOK.md "Moving to a new
# server"; sprint 12: Google Cloud trial -> DigitalOcean, sslip.io -> Student Pack domain).
#
#   On the OLD server:  bash deploy/move-server.sh export
#   On the NEW server:  bash deploy/move-server.sh import ~/securepay-move-<time>.tar.gz.enc <new-domain>
#
# export stops the apps (the database stays up), dumps the three databases and packs them
# with deploy/secrets/*, deploy/.env and the fraud model folder into ONE encrypted file
# (AES-256, a passphrase you type twice). The secrets include the vault and field master
# keys: without them the copied data cannot be read, and anyone with them and the dumps can
# read it, so the file is encrypted and should be deleted everywhere once the move is done.
#
# import (new server, after RUNBOOK.md steps 1 to 3, before step 4) unpacks it, sets DOMAIN,
# restores the databases into a fresh database volume, starts the stack and moves the
# merchants' webhook URLs to the new domain (manage.py change_domain). It refuses to run on
# a server that already has secrets, deploy/.env or a database volume.
#
# Not carried over: Mailpit messages (the demo inbox starts empty), Caddy's certificates (the
# new server gets its own), the GitHub deploy key (run setup-auto-deploy.sh again).
#
# For a script run, set MOVE_PASSPHRASE in the environment instead of typing it.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
C=(docker compose -f deploy/compose.prod.yaml)
DBS=(gateway simulator merchant)
APPS=(caddy merchant gateway-worker gateway simulator)
umask 077
work=""
trap '[ -z "$work" ] || rm -rf "$work"' EXIT

die() { echo "move-server: $*" >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" "$2" | tail -n1 | tr -d "\"' "; }
pass_args() { if [ -n "${MOVE_PASSPHRASE:-}" ]; then echo "-pass env:MOVE_PASSPHRASE"; fi; }

wait_for_db() {  # until the real server listens on TCP (the init-time one only has a socket)
  local i
  for i in $(seq 1 60); do
    if "${C[@]}" exec -T db pg_isready -q -h 127.0.0.1 -U postgres 2>/dev/null; then return 0; fi
    sleep 2
  done
  die "the database did not start; see: ${C[*]} logs db"
}

do_export() {
  [ -e deploy/.env ] || die "deploy/.env is missing: is this the server?"
  local stamp out model
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  out="$HOME/securepay-move-$stamp.tar.gz.enc"
  work="$(mktemp -d)"
  mkdir -p "$work/move/secrets" "$work/move/dumps"

  echo "Stopping the apps so no payment lands after the copy (the database stays up)..."
  "${C[@]}" stop "${APPS[@]}"
  wait_for_db
  for db in "${DBS[@]}"; do
    "${C[@]}" exec -T db pg_dump -U postgres -Fc "$db" > "$work/move/dumps/$db.dump"
    echo "  dumped $db ($(du -h "$work/move/dumps/$db.dump" | cut -f1))"
  done

  find deploy/secrets -maxdepth 1 -type f ! -name '*.example' ! -name README.md \
    -exec cp -p {} "$work/move/secrets/" \;
  cp -p deploy/.env "$work/move/env"
  model="$(env_value RISK_MODEL_VERSION deploy/.env)"
  if [ -n "$model" ] && [ -d "gateway/apps/risk/model_artifacts/$model" ]; then
    mkdir -p "$work/move/model"
    cp -rp "gateway/apps/risk/model_artifacts/$model" "$work/move/model/"
  fi
  printf 'from_domain=%s\nmade_at=%s\ncommit=%s\n' "$(env_value DOMAIN deploy/.env)" \
    "$stamp" "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" > "$work/move/ABOUT"

  echo "Choose a passphrase for the move file (you type it again on the new server):"
  # shellcheck disable=SC2046
  tar -C "$work" -czf - move | openssl enc -e -aes-256-cbc -pbkdf2 -iter 600000 -salt \
    $(pass_args) -out "$out"
  chmod 600 "$out"
  cat <<EOF

Done: $out
SHA-256: $(sha256sum "$out" | cut -d' ' -f1)

The apps on THIS server are now stopped (the database and Mailpit still run). If you call
the move off, start them again with: ${C[*]} up -d

Next, from your laptop (the file never needs to be anywhere else):
  scp securepay@<old-ip>:$(basename "$out") .
  scp $(basename "$out") securepay@<new-ip>:
Then on the new server: bash deploy/move-server.sh import ~/$(basename "$out") <new-domain>
EOF
}

do_import() {
  local file="${1:-}" new="${2:-}" old
  [ -f "$file" ] || die "usage: move-server.sh import <file.tar.gz.enc> [new-domain]"
  [ ! -e deploy/.env ] || die "deploy/.env already exists: import only runs on a fresh server"
  if find deploy/secrets -maxdepth 1 -type f ! -name '*.example' ! -name README.md | grep -q .; then
    die "deploy/secrets already holds secrets: import only runs on a fresh server"
  fi
  if docker volume ls -q --filter label=com.docker.compose.volume=pgdata | grep -q .; then
    die "a database volume already exists (docker volume ls): import only runs on a fresh server"
  fi

  work="$(mktemp -d)"
  echo "Passphrase for the move file:"
  # shellcheck disable=SC2046
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 $(pass_args) -in "$file" \
    | tar -C "$work" -xzf - || die "could not decrypt or unpack $file (wrong passphrase?)"
  [ -f "$work/move/env" ] && [ -f "$work/move/secrets/vault_encryption_key" ] \
    || die "$file is not a SecurePay move file"

  old="$(env_value DOMAIN "$work/move/env")"
  new="${new:-$old}"
  new="$(echo "$new" | tr 'A-Z' 'a-z' | sed 's/\.$//')"
  [[ "$new" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || die "not a domain name: $new"

  # Secrets with the permissions make-secrets.sh uses (files 0644 for the containers'
  # non-root users, the folder 0700 so only securepay can list it).
  mkdir -p deploy/secrets
  cp -p "$work"/move/secrets/* deploy/secrets/
  chmod 644 deploy/secrets/*
  chmod 700 deploy/secrets
  # .env from the old server with the new DOMAIN; PUBLIC_IP belonged to the old server.
  grep -v -e '^DOMAIN=' -e '^PUBLIC_IP=' "$work/move/env" > deploy/.env
  echo "DOMAIN=$new" >> deploy/.env
  chmod 600 deploy/.env
  if [ -d "$work/move/model" ]; then
    cp -rp "$work"/move/model/* gateway/apps/risk/model_artifacts/
    chmod -R a+rX gateway/apps/risk/model_artifacts
  fi
  echo "Secrets, deploy/.env (DOMAIN=$new) and the fraud model are in place."

  echo "Starting a fresh database and restoring the dumps..."
  "${C[@]}" up -d db
  wait_for_db
  for db in "${DBS[@]}"; do
    "${C[@]}" exec -T db pg_restore -U postgres --clean --if-exists --exit-on-error -d "$db" \
      < "$work/move/dumps/$db.dump"
    echo "  restored $db"
  done

  echo "Building and starting the stack (a few minutes the first time)..."
  "${C[@]}" up -d --build
  local i
  for i in $(seq 1 60); do
    if "${C[@]}" exec -T gateway python manage.py migrate --check >/dev/null 2>&1; then break; fi
    sleep 3
  done
  if [ "$old" != "$new" ]; then
    "${C[@]}" exec -T gateway python manage.py change_domain --from "$old" --to "$new"
  fi

  cat <<EOF

Imported (old domain $old, now $new). Next:
 1. DNS: A records for gateway, shop and mail (or one * record) -> this server's IPv4.
    Caddy gets the certificates by itself once the names point here.
 2. bash deploy/smoke-check.sh $new
 3. ${C[*]} exec gateway python manage.py demo_check --merchant mer_...
 4. bash deploy/setup-auto-deploy.sh, and replace DEPLOY_HOST and DEPLOY_KNOWN_HOSTS
    (and the DEPLOY_SSH_KEY secret) on GitHub, so merges deploy here, not to the old server.
 5. Backups: add the crontab line from RUNBOOK.md step 9.
 6. Delete the move file here and on your laptop; turn the old server off once this one
    has run fine for a few days.
EOF
}

case "${1:-}" in
  export) do_export ;;
  import) shift; do_import "$@" ;;
  *) die "usage: move-server.sh export | import <file> [new-domain]" ;;
esac
