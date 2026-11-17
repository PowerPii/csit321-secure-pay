#!/bin/bash
# Checks the public server from outside (RUNBOOK.md step 8). Run from a laptop or the server:
#   bash deploy/smoke-check.sh 203-0-113-5.sslip.io
#   bash deploy/smoke-check.sh securepay-demo.me          # a real domain: IP from DNS
# Exit code 0 = every check passed.
set -uo pipefail
. "$(dirname "$0")/public-ip.sh"
domain="${1:?usage: smoke-check.sh <domain, e.g. 203-0-113-5.sslip.io> [ip]}"
ip="${2:-$(public_ip "$domain")}"  # optional 2nd argument: the IP
fail=0

check() {  # description, expected HTTP status, curl arguments...
  local what="$1" want="$2"; shift 2
  local got
  got="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@")"
  if [ "$got" = "$want" ]; then echo "ok    $what ($got)"; else echo "FAIL  $what: got $got, want $want"; fail=1; fi
}

check "gateway health"                    200 "https://gateway.$domain/healthz"
check "checkout page served"              200 "https://gateway.$domain/pay/cs_test"
check "guest status page served"          200 "https://gateway.$domain/guest/status"
check "customer account pages served"   200 "https://gateway.$domain/account/sign-in"
check "staff dashboard served"            200 "https://gateway.$domain/dashboard/"
check "Django admin off (gateway)"        404 "https://gateway.$domain/admin/"
check "API needs a key"                   401 "https://gateway.$domain/v1/payments"
check "demo shop"                         200 "https://shop.$domain/"
check "Django admin off (shop)"           404 "https://shop.$domain/admin/"
check "API schema not public"             404 "https://gateway.$domain/api/schema/"
check "demo inbox needs sign-in"          401 "https://mail.$domain/"
check "HTTP redirects to HTTPS"           308 "http://gateway.$domain/healthz"

if [ -z "$ip" ]; then
  echo "FAIL  no IP for gateway.$domain (DNS not set up yet?); pass it as the 2nd argument"
  exit 1
fi

# The simulator must not answer from outside: port 8443 is not published, and the private
# names have no certificate on the public port.
if curl -sk --max-time 5 -o /dev/null "https://$ip:8443/"; then
  echo "FAIL  port 8443 answers from outside"; fail=1
else
  echo "ok    port 8443 closed from outside"
fi
# Caddy answers unknown names on 443 with an empty reply; the simulator's health check
# would say "ok". Try the private name both as SNI and as a Host header.
body="$(curl -sk --max-time 5 --resolve "simulator.securepay.internal:443:$ip" \
     "https://simulator.securepay.internal/healthz")"
body2="$(curl -s --max-time 5 -H "Host: simulator.securepay.internal" "https://gateway.$domain/healthz" \
     )"
if grep -q ok <<<"$body$body2"; then
  echo "FAIL  simulator reachable through port 443"; fail=1
else
  echo "ok    simulator not reachable through port 443"
fi

hdrs="$(curl -sI --max-time 15 "https://gateway.$domain/pay/cs_test")"
for h in strict-transport-security content-security-policy x-content-type-options; do
  if grep -qi "^$h:" <<<"$hdrs"; then echo "ok    header $h"; else echo "FAIL  header $h missing"; fail=1; fi
done

exit $fail
