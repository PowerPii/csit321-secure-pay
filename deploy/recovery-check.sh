#!/bin/bash
# After a restore (backup/restore.sh) or a rollback (rollback.sh): does the gateway still
# agree with the simulator about recent payments? Read-only; docs/RECOVERY.md.
#   bash deploy/recovery-check.sh                       # the 20 newest payments with an answer
#   bash deploy/recovery-check.sh --payment SP-ABCD-1234
set -euo pipefail
deploy="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${COMPOSE_FILE:-}" ]; then
  if grep -qE '^DOMAIN=.+' "$deploy/.env" 2>/dev/null; then COMPOSE_FILE="$deploy/compose.prod.yaml"
  else COMPOSE_FILE="$deploy/compose.yaml"; fi
fi
exec docker compose -f "$COMPOSE_FILE" exec -T gateway python manage.py recovery_check "$@"
