#!/bin/bash
# NFR-ENC-01 / M-ENC-01: TLS versions, cipher policy and plain-HTTP behaviour of every external
# entry point. Run it from a laptop on an ordinary network (not from the server, and not from a
# network whose proxy inspects TLS, or you measure the proxy instead of the server):
#
#   bash tests/tls/check-tls.sh                      # securepaysg.me
#   bash tests/tls/check-tls.sh example.org > out.txt
#
# Needs bash, openssl and curl (macOS and Linux both have them). Prints one line per check and a
# PASS or FAIL summary; save the output as the evidence file for M-ENC-01. If testssl.sh is on
# the PATH it also runs it for the full report (optional).
#
# Entry points checked:
#   gateway., shop., mail.<domain>  Caddy on the Google Cloud VM, ports 443 (TLS) and 80
#   <domain>, www.<domain>          the marketing website on Vercel
#   gateway.<domain>:8443           the private simulator hop: must not answer from outside
#
# A network that intercepts TLS (a company or ISP filter, an antivirus "web shield") answers with
# its own certificate and its own HTTP redirects, so the results describe that filter, not our
# server. The script checks every certificate's issuer against EXPECT_ISSUER (default: the CAs
# Caddy and Vercel use) and every HTTP redirect's target host; on a mismatch it stops with
# INVALID (exit 2) and records nothing as a pass. Use another network (a phone hotspot) then.
set -u
D="${1:-securepaysg.me}"
DEFAULT_ISSUERS="Let's Encrypt|ZeroSSL|Google Trust Services"
EXPECT_ISSUER="${EXPECT_ISSUER:-$DEFAULT_ISSUERS}"
invalid=()
CADDY=(gateway shop mail)
fail=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $*"; fail=1; }
ok()  { say "ok    $*"; }

# One handshake at one protocol version; prints the negotiated cipher or nothing.
hs() { # host version [cipher-args...]
  local host=$1 v=$2; shift 2
  timeout 10 openssl s_client -connect "$host:443" -servername "$host" "-$v" "$@" </dev/null 2>/dev/null \
    | sed -n 's/^New, [^,]*, Cipher is \(.*\)$/\1/p' | grep -v '(NONE)' | head -1
}

say "# M-ENC-01 TLS check for $D, $(date -u +%Y-%m-%dT%H:%M:%SZ), $(openssl version)"
for name in "${CADDY[@]/%/.$D}" "$D" "www.$D"; do
  say "== $name"
  # certificate (issuer and dates only); a foreign issuer means something in between
  cert=$(timeout 10 openssl s_client -connect "$name:443" -servername "$name" </dev/null 2>/dev/null \
    | openssl x509 -noout -issuer -enddate 2>/dev/null)
  printf '%s\n' "$cert" | sed 's/^/      /'
  issuer=$(printf '%s\n' "$cert" | sed -n 's/^issuer=//p')
  if [ -n "$issuer" ] && ! printf '%s' "$issuer" | grep -Eq "$EXPECT_ISSUER"; then
    invalid+=("$name certificate issued by '$issuer', not $EXPECT_ISSUER")
    say "INVALID $name: certificate from '$issuer' (TLS is being intercepted on this network)"
  fi
  for v in tls1 tls1_1; do
    c=$(hs "$name" "$v" -cipher 'ALL:@SECLEVEL=0')
    [ -z "$c" ] && ok "$name $v refused" || bad "$name $v OFFERED ($c)"
  done
  modern=0
  for v in tls1_2 tls1_3; do
    c=$(hs "$name" "$v")
    if [ -n "$c" ]; then ok "$name $v offered ($c)"; modern=1; else say "info  $name $v not offered"; fi
  done
  # no handshake at all: unreachable or broken, so the "refused" lines above prove nothing
  [ $modern -eq 1 ] || bad "$name: no TLS 1.2 or 1.3 handshake (unreachable?)"
  # TLS 1.2 cipher suites one by one: only ECDHE + AEAD (GCM or ChaCha20-Poly1305) may pass
  acc=(); weak=()
  for c in $(openssl ciphers 'ALL:@SECLEVEL=0' 2>/dev/null | tr ':' ' '); do
    case "$c" in TLS_*) continue;; esac
    if [ -n "$(hs "$name" tls1_2 -cipher "$c:@SECLEVEL=0")" ]; then
      acc+=("$c")
      case "$c" in ECDHE-*GCM*|ECDHE-*CHACHA20*) ;; *) weak+=("$c");; esac
    fi
  done
  say "      TLS 1.2 suites accepted: ${acc[*]:-none}"
  [ ${#weak[@]} -eq 0 ] && ok "$name no weak TLS 1.2 suite" || bad "$name weak TLS 1.2 suites: ${weak[*]}"
  # plain HTTP must redirect to HTTPS
  r=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{redirect_url}' "http://$name/")
  code=${r%% *}; target=${r#* }
  thost=$(printf '%s' "$target" | sed -E 's#^[a-z]+://([^/:]+).*#\1#')
  if [ "${code:0:1}" = 3 ] && [ "$thost" != "$name" ] && [ "${thost%".$D"}" = "$thost" ] && [ "$thost" != "$D" ]; then
    invalid+=("$name http:// redirected to another host ($r)")
    say "INVALID $name: plain HTTP redirected off our domain (a network filter answered)"
  elif { [ "$code" = 301 ] || [ "$code" = 308 ]; } && [ "${target#https://}" != "$target" ]; then
    ok "$name http:// -> $r"
  else
    bad "$name http:// answered '$r'"
  fi
  # HSTS on the HTTPS answer
  h=$(curl -sI -m 10 "https://$name/" | tr -d '\r' | grep -i '^strict-transport-security:' | head -1)
  [ -n "$h" ] && ok "$name $h" || say "info  $name no HSTS header"
done
say "== private port"
if timeout 6 bash -c "exec 3<>/dev/tcp/gateway.$D/8443" 2>/dev/null; then
  bad "gateway.$D:8443 accepts connections from outside"
else
  ok "gateway.$D:8443 not reachable from outside"
fi
if command -v testssl.sh >/dev/null; then
  for h in "${CADDY[@]}"; do testssl.sh --quiet --color 0 --protocols --std --severity HIGH "https://$h.$D"; done
fi
say
if [ ${#invalid[@]} -gt 0 ]; then
  say "INVALID: this network intercepts TLS or HTTP, so these results describe it, not the server:"
  printf '  - %s\n' "${invalid[@]}"
  say "Run again from another network (a phone hotspot). Do not record this run."
  exit 2
fi
[ $fail -eq 0 ] && say "PASS: only TLS 1.2/1.3, no weak suite, HTTP redirects to HTTPS on every name" || say "FAIL: see the FAIL lines above"
exit $fail
