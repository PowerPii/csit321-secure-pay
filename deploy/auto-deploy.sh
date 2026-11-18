#!/bin/bash
# Update the public server: fast-forward the clone, rebuild and restart what changed, check
# that every running container was built from that commit, then run the smoke check.
# RUNBOOK.md step 10.
#
# GitHub Actions runs this after CI passes on main (.github/workflows/deploy.yml) and names the
# exact commit CI tested: the SSH command is "deploy <40-character commit>". The server then
# deploys that commit, never a newer main that has not passed its own checks (Codex release
# review, 18 Nov 2026). Its SSH key is locked to this one script in ~/.ssh/authorized_keys
# (deploy/setup-auto-deploy.sh), so the key can deploy a commit on main and do nothing else;
# any other command is refused.
#
# By hand (you have run the checks yourself, for example while Actions is paused):
#   bash ~/csit321-secure-pay/deploy/auto-deploy.sh            # the newest  main "$@"
#   bash ~/csit321-secure-pay/deploy/auto-deploy.sh <commit>   # one commit on  main "$@"
set -euo pipefail

main() {
  local repo log prev now domain tries want request bad
  # What to deploy: a commit named by GitHub Actions (forced SSH command) or on the command
  # line, else the newest main.
  request="${SSH_ORIGINAL_COMMAND:-${1:-}}"
  want=""
  if [ -n "$request" ]; then
    if [[ "$request" =~ ^(deploy\ )?([0-9a-f]{40})$ ]]; then
      want="${BASH_REMATCH[2]}"
    else
      echo "refusing: expected \"deploy <40-character commit>\", got something else"; exit 2
    fi
  fi
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
  git fetch --quiet origin  main "$@"
  if [ -z "$want" ]; then
    want="$(git rev-parse origin/main)"
    echo "no commit named: deploying the newest main ($want)"
  elif ! git merge-base --is-ancestor "$want" origin/main 2>/dev/null; then
    echo "refusing: $want is not a commit on main"; exit 1
  elif [ "$(git rev-parse HEAD)" != "$want" ] && git merge-base --is-ancestor "$want" HEAD; then
    # A slower run for an older merge arrived after a newer one was deployed: never go back.
    echo "already running $prev, which is newer than $want; nothing to do"; return 0
  fi
  # Fast-forward only: hand edits on the server are kept, and ones that clash with the new
  # code stop the deploy instead of being thrown away.
  if ! git merge --ff-only --quiet "$want"; then
    echo "the server clone has local changes or commits; fix by hand (git status)"; exit 1
  fi
  now="$(git rev-parse HEAD)"
  echo "code: $prev -> ${now:0:7} ($now)"

  # Every image is labelled with the commit it was built from (compose.prod.yaml).
  GIT_REVISION="$now" docker compose -f deploy/compose.prod.yaml up -d --build --remove-orphans
  bad=0
  for container in $(docker compose -f deploy/compose.prod.yaml ps -q); do
    built="$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$container")"
    name="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' "$container")"
    case "$name" in gateway|gateway-worker|simulator|merchant|caddy) ;; *) continue ;; esac
    if [ "$built" != "$now" ]; then
      echo "MISMATCH: $name is running an image built from ${built:-an unknown commit}, not $now"; bad=1
    fi
  done
  [ $bad -eq 0 ] || { echo "=== deploy of $now FAILED the revision check"; exit 1; }
  echo "$now" > "$HOME/deployed-revision"
  echo "every app container runs $now"
  # Old image layers fill the 30 GB disk after a few dozen deploys.
  docker image prune -f >/dev/null

  # The apps run their migrations on start; give them up to 3 minutes to answer.
  domain="$(sed -n 's/^DOMAIN=//p' deploy/.env | tr -d "\"' ")"
  for tries in $(seq 1 18); do
    if bash deploy/smoke-check.sh "$domain" >/tmp/securepay-smoke.txt 2>&1; then
      cat /tmp/securepay-smoke.txt
      echo "=== deployed ${now:0:7}, smoke check passed"
      return 0
    fi
    sleep 10
  done
  cat /tmp/securepay-smoke.txt
  echo "=== deployed ${now:0:7}, but the smoke check FAILED after $tries tries (see above)"
  docker compose -f deploy/compose.prod.yaml ps
  exit 1
}

# Everything is inside main(), so bash has read the whole script before git replaces this file.
main "$@"
