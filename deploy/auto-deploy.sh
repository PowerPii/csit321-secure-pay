#!/bin/bash
# Update the public server to the latest main: fast-forward the clone, rebuild and restart
# what changed, then run the smoke check. RUNBOOK.md step 10.
#
# GitHub Actions runs this after CI passes on main (.github/workflows/deploy.yml). Its SSH key
# is locked to this one script in ~/.ssh/authorized_keys (deploy/setup-auto-deploy.sh), so the
# key can start a deploy of main and do nothing else. You can also run it by hand:
#   bash ~/csit321-secure-pay/deploy/auto-deploy.sh
#
# It takes no arguments and ignores whatever command the SSH client asked for.
set -euo pipefail

main() {
  local repo log prev now domain tries
  repo="$(cd "$(dirname "$0")/.." && pwd)"
  log="$HOME/deploy.log"
  cd "$repo"

  # One deploy at a time (two quick merges, or a hand run during an automatic one).
  exec 9>"$HOME/.securepay-deploy.lock"
  flock -w 900 9 || { echo "another deploy is still running"; exit 1; }

  exec > >(tee -a "$log") 2>&1
  echo "=== deploy $(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # Demo freeze (deploy/freeze.sh): nothing changes on the server until it ends.
  if bash deploy/freeze.sh status >/dev/null 2>&1; then
    echo "$(bash deploy/freeze.sh status) Not deploying; main is deployed by the first"
    echo "merge after the freeze, or by hand: bash deploy/freeze.sh off, then this script."
    exit 1
  fi

  if [ "$(git rev-parse --abbrev-ref HEAD)" != main ]; then
    echo "the server clone is not on main; refusing to deploy"; exit 1
  fi
  prev="$(git rev-parse --short HEAD)"
  git fetch --quiet origin main
  # Fast-forward only: hand edits on the server are kept, and ones that clash with the new
  # code stop the deploy instead of being thrown away.
  if ! git merge --ff-only --quiet origin/main; then
    echo "the server clone has local changes or commits; fix by hand (git status)"; exit 1
  fi
  now="$(git rev-parse --short HEAD)"
  echo "code: $prev -> $now"

  docker compose -f deploy/compose.prod.yaml up -d --build --remove-orphans
  # Old image layers fill the 30 GB disk after a few dozen deploys.
  docker image prune -f >/dev/null

  # The apps run their migrations on start; give them up to 3 minutes to answer.
  domain="$(sed -n 's/^DOMAIN=//p' deploy/.env | tr -d "\"' ")"
  for tries in $(seq 1 18); do
    if bash deploy/smoke-check.sh "$domain" >/tmp/securepay-smoke.txt 2>&1; then
      cat /tmp/securepay-smoke.txt
      echo "=== deployed $now, smoke check passed"
      return 0
    fi
    sleep 10
  done
  cat /tmp/securepay-smoke.txt
  echo "=== deployed $now, but the smoke check FAILED after $tries tries (see above)"
  docker compose -f deploy/compose.prod.yaml ps
  exit 1
}

# Everything is inside main(), so bash has read the whole script before git replaces this file.
main
