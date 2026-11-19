#!/usr/bin/env bash
# Decides which parts of CI a change needs (.github/workflows/ci.yml, job `changes`).
# Writes to $GITHUB_OUTPUT:
#   python=   the Python services to test, e.g. "gateway merchant" (empty: none)
#   frontend= the front-end apps (and the Node.js SDK, "sdk") to test, e.g. "checkout sdk" (empty: none)
#   deploy=   true when the public server's config or the Caddy image's inputs changed
# Everything runs for a manual run, a first push, a history it cannot diff, or a change to
# the CI files themselves.
#
# Try it locally:  EVENT=pull_request BASE_SHA=origin/main HEAD_SHA=HEAD bash .github/ci-changes.sh
set -euo pipefail

ALL_PYTHON="gateway simulator merchant"
ALL_FRONTEND="checkout dashboard website sdk"
out="${GITHUB_OUTPUT:-/dev/stdout}"
summary="${GITHUB_STEP_SUMMARY:-/dev/null}"

full=false
files=""
case "${EVENT:-}" in
  pull_request)
    if files="$(git diff --name-only "$BASE_SHA...$HEAD_SHA")"; then :; else full=true; fi ;;
  push)
    if [[ -z "${BEFORE:-}" || "$BEFORE" =~ ^0+$ ]] || ! git cat-file -e "$BEFORE^{commit}" 2>/dev/null; then
      full=true
    elif files="$(git diff --name-only "$BEFORE" "${GITHUB_SHA:-HEAD}")"; then :; else full=true; fi ;;
  *) full=true ;;
esac

# Markdown files (READMEs, runbooks, notes) never change what a test checks, so a change
# made only of them runs no tests (the always-on checks still run).
code="$(grep -vE '\.md$' <<<"$files" || true)"
touches() { grep -qE "$1" <<<"$code"; }

if [ "$full" = false ] && touches '^\.github/(workflows/|ci-[a-z]+\.sh$)'; then full=true; fi

if [ "$full" = true ]; then
  python="$ALL_PYTHON"; frontend="$ALL_FRONTEND"; deploy=true
else
  python=""; frontend=""; deploy=false
  # The gateway's tests also read contracts/, research/ (feature parity) and the brand files.
  touches '^(gateway|contracts|research|frontend/brand)/|^frontend/[^/]+/public/favicon\.svg$|^frontend/checkout/src/Brand\.tsx$' \
    && python="$python gateway"
  touches '^simulator/' && python="$python simulator"
  touches '^merchant/' && python="$python merchant"
  for app in checkout dashboard website; do
    touches "^frontend/$app/" && frontend="$frontend $app"
  done
  # The Node.js SDK (sdk/node) generates its types from the bundled contract.
  touches '^(sdk/node|contracts)/' && frontend="$frontend sdk"
  touches '^deploy/|^frontend/(checkout|dashboard)/|^\.dockerignore$' && deploy=true
  python="${python# }"; frontend="${frontend# }"
fi

{
  echo "python=$python"
  echo "frontend=$frontend"
  echo "deploy=$deploy"
} >> "$out"

{
  echo "### What this run tests"
  if [ "$full" = true ]; then echo "Everything (manual run, first push, or the CI files changed)."; fi
  echo "- Python services: ${python:-none}"
  echo "- Front-end apps: ${frontend:-none}"
  echo "- Deploy config: $deploy"
  echo "- Always: merge freeze (pull requests), gitleaks, contracts, test report"
} | tee -a "$summary"
