#!/bin/bash
# Deploy freeze on the server (demo sprint 16, RUNBOOK.md section 10a). While it is on,
# deploy/auto-deploy.sh refuses to deploy, so a merge to main cannot restart the stack in
# the hours before a demo. GitHub has its own switch too (the MERGE_FREEZE_UNTIL variable,
# which marks pull requests red and stops the deploy workflow); use both.
#
#   bash deploy/freeze.sh on                     # 48 hours from now
#   bash deploy/freeze.sh on 72                  # 72 hours from now
#   bash deploy/freeze.sh until "2027-04-02 18:00"   # Singapore time unless a zone is given
#   bash deploy/freeze.sh status                 # exit code 0 = frozen now
#   bash deploy/freeze.sh off
#
# The freeze ends by itself at its time. To deploy anyway while frozen, turn it off first.
set -euo pipefail
file="${FREEZE_FILE:-$HOME/.securepay-freeze}"
export TZ="${TZ:-Asia/Singapore}"

show() { date -d "@$1" '+%a %d %b %Y %H:%M %Z'; }

case "${1:-status}" in
  on)
    hours="${2:-48}"
    [[ "$hours" =~ ^[0-9]+$ ]] || { echo "hours must be a whole number"; exit 2; }
    until=$(( $(date +%s) + hours * 3600 ))
    echo "$until" > "$file"
    echo "Deploys frozen until $(show "$until")." ;;
  until)
    until="$(date -d "${2:?give a date and time, e.g. \"2027-04-02 18:00\"}" +%s)"
    [ "$until" -gt "$(date +%s)" ] || { echo "that time has already passed"; exit 2; }
    echo "$until" > "$file"
    echo "Deploys frozen until $(show "$until")." ;;
  off)
    rm -f "$file"
    echo "Deploy freeze off: the next merge to main deploys as usual." ;;
  status)
    until="$(cat "$file" 2>/dev/null || echo 0)"
    if [ "$until" -gt "$(date +%s)" ]; then
      echo "FROZEN until $(show "$until"): auto-deploy.sh will not deploy."
      exit 0
    fi
    echo "Not frozen: a merge to main deploys within minutes."
    exit 1 ;;
  *) echo "usage: freeze.sh on [hours] | until \"YYYY-MM-DD HH:MM\" | off | status"; exit 2 ;;
esac
