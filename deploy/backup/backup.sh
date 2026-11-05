#!/bin/bash
# Dump all three databases to a dated folder outside the VM's app directory.
set -euo pipefail
out="${BACKUP_DIR:-$HOME/fyp-backups}/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$out"
for db in gateway simulator merchant; do
  docker compose -f "$(dirname "$0")/../compose.yaml" exec -T db pg_dump -U postgres -Fc "$db" > "$out/$db.dump"
done
echo "backups written to $out"
