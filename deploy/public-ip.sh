# Sourced by smoke-check.sh, setup-auto-deploy.sh and move-server.sh (not run on its own).
# public_ip <domain>: the server's public IPv4 for a DOMAIN from deploy/.env.
#   PUBLIC_IP set (environment or deploy/.env) -> that value
#   203-0-113-5.sslip.io                        -> 203.0.113.5 (the name carries the IP)
#   a real domain, e.g. securepay-demo.me       -> what DNS says for gateway.<domain>
# Prints nothing if the IP cannot be found; callers treat that as a failure.
public_ip() {
  local domain="$1" ip=""
  if [ -n "${PUBLIC_IP:-}" ]; then
    echo "$PUBLIC_IP"; return
  fi
  case "$domain" in
    *.sslip.io) echo "${domain%.sslip.io}" | tr - . ; return ;;
  esac
  if command -v getent >/dev/null 2>&1; then
    ip="$(getent ahostsv4 "gateway.$domain" 2>/dev/null | awk 'NR==1{print $1}')"
  fi
  if [ -z "$ip" ] && command -v dig >/dev/null 2>&1; then  # macOS laptops have no getent
    ip="$(dig +short A "gateway.$domain" 2>/dev/null | grep -E '^[0-9.]+$' | tail -n1)"
  fi
  echo "$ip"
}
