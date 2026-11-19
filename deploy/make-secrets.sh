#!/bin/bash
# Makes fresh secrets for the public server (deploy/RUNBOOK.md step 4). Run on the server,
# from anywhere:  bash deploy/make-secrets.sh
#
# - Fills every deploy/secrets/<name> that does not exist yet (never overwrites one, so it is
#   safe to run again). Never copy the development values to the server.
# - Makes the Mailpit sign-in for https://mail.<domain>, prints the password once and keeps
#   only its bcrypt hash in deploy/.env.
#
# Permissions: the secrets folder is 0700 (only you can list or open it on the server); the
# files inside are 0644 because Compose mounts each file into its container as-is, and the
# apps run as a non-root user there.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p secrets
chmod 700 secrets

token() { openssl rand -base64 48 | tr -d '\n/+='; }
# 32 random bytes, URL-safe base64 with padding: the AES-256-GCM vault key and the Fernet
# field key both use this format.
key32() { openssl rand 32 | base64 | tr '+/' '-_'; }

made=()
for example in secrets/*.example; do
  f="${example%.example}"
  [ -e "$f" ] && continue
  case "$(basename "$f")" in
    vault_encryption_key|field_encryption_key) key32 > "$f" ;;
    simulator_api_key) echo "simk_$(token)" > "$f" ;;
    simulator_test_control_key) echo "simc_$(token)" > "$f" ;;
    *) token > "$f" ;;
  esac
  made+=("$(basename "$f")")
done
chmod 644 secrets/*
chmod 700 secrets

if [ ${#made[@]} -gt 0 ]; then
  echo "Made: ${made[*]}"
else
  echo "All secrets already exist; nothing changed."
fi

# deploy/.env (DOMAIN, ACME_EMAIL, ...): start from the example on the first run.
if [ ! -e .env ]; then
  cp prod.env.example .env
  echo "Made deploy/.env from prod.env.example: set DOMAIN and ACME_EMAIL in it."
fi
chmod 600 .env

if ! grep -q '^MAIL_PASSWORD_HASH=' .env; then
  pw="$(openssl rand -base64 18 | tr -d '\n/+=')"
  hash="$(docker run --rm caddy:2.11.9@sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b caddy hash-password --plaintext "$pw")"
  # Single quotes: the hash contains '$', which Compose would otherwise read as a variable.
  echo "MAIL_PASSWORD_HASH='$hash'" >> .env
  user="$(grep '^MAIL_USER=' .env | cut -d= -f2)"
  echo
  echo "Demo inbox sign-in (https://mail.<domain>): user '${user:-team}', password: $pw"
  echo "Put it in the team password manager now; only its hash is kept on the server."
fi

cat <<'EOF'

Next: keep an offline copy of vault_encryption_key, field_encryption_key and
card_fingerprint_key in the team password manager. Losing the vault or field key makes the
data they protect unreadable; losing the fingerprint key resets fraud history.
EOF
