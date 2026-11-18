#!/usr/bin/env bash
# One Python service's CI checks (.github/workflows/ci.yml, job `python`), in its own virtual
# environment: lint, Django checks, migrations, tests on Postgres, dependency and code audits.
# Usage: bash .github/ci-python.sh gateway|simulator|merchant
set -euo pipefail
svc="$1"
cd "$(dirname "$0")/../$svc"
python -m venv --clear "../.venv-$svc"
# shellcheck disable=SC1090
. "../.venv-$svc/bin/activate"
# A new venv gets the pip bundled with Python, which can be old enough for pip-audit to flag.
python -m pip install -q --upgrade pip
# Exact versions with hashes, the same as the images (requirements-dev.lock adds the dev tools).
pip install -q --require-hashes --no-deps -r requirements-dev.lock
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
# JUnit results feed the non-functional test report (job ci-ok).
pytest --junitxml="junit-$svc.xml"
pip-audit -r requirements.lock --require-hashes --disable-pip
bandit -q -r apps -x "*/tests.py,*/test_*.py"
