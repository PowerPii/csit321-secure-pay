#!/bin/bash
# Creates the three logical databases and their roles on first start.
# Role passwords are read from the mounted secrets so nothing is hard-coded. Every secret is
# checked before anything is created: a missing, unreadable or empty one stops the start-up
# instead of leaving a role with a guessable password (Codex release review, 18 Nov 2026).
set -euo pipefail

declare -A password
missing=()
for role in gateway vault simulator merchant; do
  file="/run/secrets/${role}_db_password"
  value=""
  if [ -r "$file" ]; then
    value="$(tr -d '\r\n' < "$file")"
  fi
  if [ -z "$value" ]; then
    missing+=("$file")
  elif [[ "$value" == *"'"* ]]; then
    echo "01-databases.sh: $file contains a single quote; make a new one with deploy/make-secrets.sh" >&2
    exit 1
  fi
  password[$role]="$value"
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "01-databases.sh: missing, unreadable or empty secret(s): ${missing[*]}" >&2
  echo "Create them (deploy/make-secrets.sh, or copy deploy/secrets/*.example), check they can be read, then remove the database volume and start again." >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username postgres <<SQL
CREATE ROLE gateway LOGIN PASSWORD '${password[gateway]}';
CREATE ROLE vault LOGIN PASSWORD '${password[vault]}';
CREATE ROLE simulator LOGIN PASSWORD '${password[simulator]}';
CREATE ROLE merchant LOGIN PASSWORD '${password[merchant]}';
CREATE DATABASE gateway OWNER gateway;
CREATE DATABASE simulator OWNER simulator;
CREATE DATABASE merchant OWNER merchant;
SQL

# The vault gets its own schema inside the gateway database; only the vault role can use it.
psql -v ON_ERROR_STOP=1 --username postgres --dbname gateway <<SQL
CREATE SCHEMA vault AUTHORIZATION vault;
REVOKE ALL ON SCHEMA vault FROM PUBLIC;
ALTER ROLE vault SET search_path = vault;
SQL
