#!/bin/bash
# Demo-day helpers for the Volt & Co. demo (RUNBOOK.md section 11a). Run from the repo folder:
#
#   bash deploy/demo.sh seed    # once, on a fresh stack (fallback laptop, brand-new server)
#   bash deploy/demo.sh reset   # the morning of a demo, and again an hour before
#
# On the server (deploy/.env has DOMAIN=) it uses compose.prod.yaml, otherwise the local
# compose.yaml; set COMPOSE_FILE_PATH to choose another file.
#
# seed:  creates the Volt & Co. merchant (webhook to shop.<domain>), the three staff logins
#        and the risk lists if they are missing, saves a new merchant's API key and signing
#        secret into deploy/secrets for the shop and restarts it. Prints new staff passwords
#        once. On a stack that already has them it changes nothing.
# reset: restocks the shop, empties the demo inbox, prints today's fresh demo cards and
#        customer emails (no screening history, so every run behaves the same), then runs
#        demo_check. Exit code 1 if a check FAILs. It deletes no payments, screening records
#        or audit events: those stay as evidence, and fresh cards and emails do the job.
set -uo pipefail
cd "$(dirname "$0")/.."

domain=""
if [ -f deploy/.env ]; then
  domain="$(grep -E '^DOMAIN=' deploy/.env | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
fi
if [ -n "${COMPOSE_FILE_PATH:-}" ]; then
  file="$COMPOSE_FILE_PATH"
elif [ -n "$domain" ]; then
  file=deploy/compose.prod.yaml
else
  file=deploy/compose.yaml
  domain=localhost
fi
P=(docker compose -f "$file")

seed() {
  local url="https://shop.$domain/webhooks/securepay" out key secret
  echo "== Seeding the Volt & Co. demo ($file, webhook $url)"
  if ! out="$("${P[@]}" exec -T gateway python manage.py seed_demo --webhook-url "$url" </dev/null)"; then
    echo "$out"
    echo "FAIL  seed_demo did not finish"
    return 1
  fi
  # Never echo the key or the secret: they go straight into the shop's secret files.
  echo "$out" | grep -vE '^(API key|Signing secret):|^Store both now'
  key="$(echo "$out" | awk '/^API key:/{print $3}')"
  secret="$(echo "$out" | awk '/^Signing secret:/{print $3}')"
  if [ -n "$key" ] && [ -n "$secret" ]; then
    (umask 077 && printf '%s\n' "$key" > deploy/secrets/securepay_api_key \
                && printf '%s\n' "$secret" > deploy/secrets/securepay_signing_secret)
    "${P[@]}" restart merchant >/dev/null
    echo "Saved the new API key and signing secret for the shop and restarted it."
  fi
  "${P[@]}" exec -T merchant python manage.py restock </dev/null
  echo "Done. Share each temporary password privately; staff set up the authenticator app"
  echo "at the first sign-in. Then run: bash deploy/demo.sh reset"
}

reset() {
  local stamp
  stamp="$(date +%d%H%M)"
  echo "== Shop stock back to full"
  "${P[@]}" exec -T merchant python manage.py restock </dev/null
  echo
  echo "== Demo inbox emptied"
  # Mailpit's API is only reachable inside the stack (Caddy puts a password on mail.<domain>).
  "${P[@]}" exec -T gateway python -c "
import urllib.request
req = urllib.request.Request('http://mailpit:8025/api/v1/messages', data=b'{}', method='DELETE',
                             headers={'Content-Type': 'application/json'})
urllib.request.urlopen(req, timeout=10)
print('Mailpit: all messages deleted')" </dev/null || echo "WARN  could not empty Mailpit"
  echo
  echo "== Today's demo cards (fresh numbers, no screening history)"
  "${P[@]}" exec -T simulator python manage.py new_demo_card --set </dev/null
  echo
  echo "== Today's customer emails (new each reset, so email history is empty too)"
  echo "mei.$stamp@example.com     S1, S2 (Mei)"
  echo "tester.$stamp@example.com  S3 (the card tester)"
  echo "alex.$stamp@example.com    S4 (the bank goes quiet)"
  echo "review@example.com / blocked@example.com always ask for a code / are blocked."
  echo
  echo "Screening also counts attempts per IP address for one hour: leave an hour between the"
  echo "last rehearsal and the demo, and run S3 from a phone hotspot."
  echo
  echo "== Health check"
  "${P[@]}" exec -T gateway python manage.py demo_check "$@" </dev/null
}

case "${1:-}" in
  seed) seed ;;
  reset) shift; reset "$@" ;;
  *) echo "usage: bash deploy/demo.sh seed | reset [--merchant mer_...]"; exit 2 ;;
esac
