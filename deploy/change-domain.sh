#!/bin/bash
# Move the live stack to a new domain on the SAME server (RUNBOOK.md section 13a; 19 Nov 2026:
# 35-213-144-96.sslip.io -> securepaysg.me). For a new server as well, use move-server.sh.
#
#   bash deploy/change-domain.sh securepaysg.me              # on the server, as securepay
#   bash deploy/change-domain.sh securepaysg.me --keep-old   # same (the default)
#   bash deploy/change-domain.sh securepaysg.me --drop-old   # no redirects from the old names
#
# Before: the DNS A records for gateway, shop and mail point at this server (the script
# checks), and the code is up to date (auto-deploy.sh after the merge).
# It sets DOMAIN (and OLD_DOMAIN, for 308 redirects from the old names) in deploy/.env,
# rebuilds and restarts the stack (Caddy gets Let's Encrypt certificates for the new names),
# moves the merchants' webhook URLs (manage.py change_domain) and runs the smoke check.
# Nothing in the databases is lost; payments, staff, keys and orders stay as they are.
# To go back: bash deploy/change-domain.sh <old-domain> --drop-old
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
. deploy/public-ip.sh
C=(docker compose -f deploy/compose.prod.yaml)
die() { echo "change-domain: $*" >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" deploy/.env | tail -n1 | tr -d "\"' "; }
set_env() {  # set_env NAME value: replace the line, or add it at the end
  if grep -q "^$1=" deploy/.env; then
    sed -i "s|^$1=.*|$1=$2|" deploy/.env
  else
    printf '%s=%s\n' "$1" "$2" >> deploy/.env
  fi
}

new="$(echo "${1:-}" | tr 'A-Z' 'a-z' | sed 's/\.$//')"
keep_old=1
case "${2:-}" in
  ""|--keep-old) ;;
  --drop-old) keep_old=0 ;;
  *) die "usage: change-domain.sh <new-domain> [--keep-old | --drop-old]" ;;
esac
[[ "$new" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]] \
  || die "usage: change-domain.sh <new-domain> [--keep-old | --drop-old] (got '${1:-}')"
[ -f deploy/.env ] || die "deploy/.env is missing: run this on the server"
old="$(env_value DOMAIN)"
[ -n "$old" ] || die "DOMAIN is not set in deploy/.env"
[ "$old" != "$new" ] || die "DOMAIN is already $new"

# DNS must point at this server, or Let's Encrypt cannot issue the certificates (and the
# failed tries count against its rate limit).
PUBLIC_IP="${PUBLIC_IP:-$(env_value PUBLIC_IP)}"
here="$(public_ip "$old")"
[ -n "$here" ] || die "cannot tell this server's IP from $old: set PUBLIC_IP=<ip> in deploy/.env"
for name in gateway shop mail; do
  got="$(getent ahostsv4 "$name.$new" 2>/dev/null | awk 'NR==1{print $1}')"
  [ "$got" = "$here" ] || die "$name.$new resolves to '${got:-nothing}', not $here. Add the A record (RUNBOOK.md 13a) and wait a few minutes."
done
echo "DNS ok: gateway, shop and mail.$new -> $here"

cp -p deploy/.env "deploy/.env.before-$new"
set_env DOMAIN "$new"
if [ $keep_old -eq 1 ]; then set_env OLD_DOMAIN "$old"; else set_env OLD_DOMAIN ""; fi
echo "deploy/.env: DOMAIN=$new, OLD_DOMAIN=$(env_value OLD_DOMAIN) (copy of the old file: deploy/.env.before-$new)"

echo "Rebuilding and restarting the stack on the new names..."
GIT_REVISION="$(git rev-parse HEAD 2>/dev/null || echo unknown)" "${C[@]}" up -d --build

echo "Waiting for the gateway..."
for i in $(seq 1 36); do
  if "${C[@]}" exec -T gateway python manage.py migrate --check >/dev/null 2>&1; then
    break
  fi
  [ "$i" -lt 36 ] || die "the gateway did not start; see: ${C[*]} logs gateway"
  sleep 5
done
"${C[@]}" exec -T gateway python manage.py change_domain --from "$old" --to "$new"

echo "Smoke check on $new (Caddy may need a minute for the certificates)..."
for tries in $(seq 1 18); do
  if bash deploy/smoke-check.sh "$new" "$here" > /tmp/securepay-smoke.txt 2>&1; then
    cat /tmp/securepay-smoke.txt
    break
  fi
  if [ "$tries" -eq 18 ]; then
    cat /tmp/securepay-smoke.txt
    die "the smoke check still fails after 3 minutes; see: ${C[*]} logs caddy"
  fi
  sleep 10
done

cat <<EOF

Done: the stack answers on https://gateway.$new, https://shop.$new and https://mail.$new.
$( [ $keep_old -eq 1 ] && echo "The old names (*.$old) redirect there. Drop them in a few weeks: set OLD_DOMAIN= in deploy/.env, then ${C[*]} up -d" )
Next (RUNBOOK.md 13a, step 4): bash deploy/demo.sh preflight, then change the uptime
monitors and Vercel's VITE_GATEWAY_URL / VITE_SHOP_URL to the new names.
EOF
