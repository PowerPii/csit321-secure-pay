#!/usr/bin/env bash
# One front-end app's CI checks (.github/workflows/ci.yml, job `frontend`): clean install,
# type check, lint (checkout and dashboard), tests (JUnit for the test report; the website's
# public-site journey too), the website's build, and the audit.
# Usage: bash .github/ci-frontend.sh checkout|dashboard|website|sdk
# `sdk` is the Node.js SDK in sdk/node (published to npm as securepaysg).
set -euo pipefail
app="$1"
if [ "$app" = sdk ]; then
  cd "$(dirname "$0")/../sdk/node"
  npm ci --no-audit --no-fund
  npm run check:generated   # types match contracts/generated/merchant-api.v1.json
  npm run typecheck
  npm test
  npm run build
  npm pack --dry-run
  # The published package has no runtime dependencies; audit the build tools for high issues.
  npm audit --audit-level=high
  exit 0
fi
cd "$(dirname "$0")/../frontend/$app"
npm ci --no-audit --no-fund
npx tsc --noEmit
if [ "$app" = website ]; then
  # The public-site journey (src/journey.test.tsx): routes, status states, axe WCAG scan.
  npm test -- --reporter=default --reporter=junit --outputFile.junit="junit-$app.xml"
  npm run build
else
  npm run lint
  npm test -- --passWithNoTests --reporter=default --reporter=junit --outputFile.junit="junit-$app.xml"
fi
# Audit what ships to the browser. Build tools (vite and its file matchers) never reach the
# site; an advisory there with no fixed version blocked every merge and deploy (picomatch
# GHSA-fc5q-39xc-vjpf, 17 Nov 2026). Decided by Fifa, 17 Nov 2026.
npm audit --audit-level=high --omit=dev
