#!/bin/bash
# One-time set-up of automatic deploys (RUNBOOK.md step 10). Run on the server as securepay:
#   bash ~/csit321-secure-pay/deploy/setup-auto-deploy.sh
#
# Makes a new SSH key for GitHub Actions and adds it to ~/.ssh/authorized_keys locked to
# deploy/auto-deploy.sh: with this key, GitHub can start a deploy of main and nothing else
# (no shell, no file copy, no port forwarding). Prints the three values to paste into GitHub,
# then deletes the private key from the server.
#
# To replace the key (for example if it may have leaked): ROTATE=1 bash deploy/setup-auto-deploy.sh
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
tag=securepay-github-deploy
auth="$HOME/.ssh/authorized_keys"

[ "$(id -un)" = securepay ] || { echo "run this as the securepay user"; exit 1; }
[ -e "$repo/deploy/.env" ] || { echo "deploy/.env is missing: finish RUNBOOK.md steps 4 to 6 first"; exit 1; }

if grep -q "$tag" "$auth" 2>/dev/null; then
  if [ "${ROTATE:-0}" != 1 ]; then
    echo "A GitHub deploy key is already set up. To replace it: ROTATE=1 bash $0"; exit 1
  fi
  { grep -v "$tag" "$auth" || true; } > "$auth.new"
  mv "$auth.new" "$auth"
  chmod 600 "$auth"
  echo "Old GitHub deploy key removed."
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
ssh-keygen -q -t ed25519 -N "" -C "$tag" -f "$tmp/key"
printf 'restrict,command="/bin/bash %s/deploy/auto-deploy.sh" %s\n' "$repo" "$(cat "$tmp/key.pub")" >> "$auth"

domain="$(sed -n 's/^DOMAIN=//p' "$repo/deploy/.env" | tr -d "\"' ")"
ip="$(echo "${domain%%.sslip.io}" | tr - .)"

cat <<EOF

Done. Paste these three values into GitHub: the repository's Settings, then
Secrets and variables, then Actions.

1) Secrets tab, "New repository secret"
   Name:  DEPLOY_SSH_KEY
   Value: everything between the lines below, including the BEGIN and END lines
------------------------------------------------------------------------
$(cat "$tmp/key")
------------------------------------------------------------------------

2) Variables tab, "New repository variable"
   Name:  DEPLOY_HOST
   Value: $ip

3) Variables tab, "New repository variable"
   Name:  DEPLOY_KNOWN_HOSTS
   Value: $ip $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)

The private key is deleted from this server when this script ends; GitHub keeps the only copy.
Run "clear" once you have copied it.
EOF
