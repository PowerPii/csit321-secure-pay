# Test report for the non-functional requirements (M6)

The M6 test report checks every non-functional requirement in URS Section 4.4 (29 of them,
Tables 4.4.1.1 to 4.4.9.1) against its acceptance criterion.

| File | What it is | Who edits it |
| --- | --- | --- |
| `requirements.json` | The 29 requirements as the final URS states them (text, method, acceptance, priority) | Nobody; regenerate only if the URS changes |
| `evidence.yaml` | For each requirement: the CI tests, the integration (stack) tests and the manual checks that verify it | Whoever adds or renames a test |
| `MANUAL-TESTS.md` | Step-by-step procedures for the 19 checks that need the live server, a browser or people | The test lead (Noppawut) |
| `manual-results.yaml` | Results of those checks, newest last | Whoever runs a check |
| `ACCESSIBILITY.md` | The accessibility and mobile pass (NFR-USE-01, NFR-USE-02): what was found, fixed and measured | Whoever re-runs `tests/a11y/scan.mjs` |
| `TEST-REPORT.md` | The generated report: status per requirement and all evidence | Generated, never by hand |

## Getting the report

Every CI run builds it: open the run on GitHub (Actions, `ci`), the report is on the summary
page and in the `test-report` artifact. The `ci-ok` job is red if a requirement fails, and
the `changes` job if `evidence.yaml` names a test that no longer exists. CI tests only the
parts a change touches, so the rest show as "Not run"; for a full report, Actions, `ci`,
"Run workflow" on `main`.

Locally, after running the suites with JUnit output:

```bash
(cd gateway && pytest --junitxml=../reports/junit-gateway.xml)
(cd merchant && pytest --junitxml=../reports/junit-merchant.xml)
(cd frontend/checkout && npx vitest run --reporter=junit --outputFile.junit=../../reports/junit-checkout.xml)
(cd frontend/dashboard && npx vitest run --reporter=junit --outputFile.junit=../../reports/junit-dashboard.xml)
pip install pyyaml
python tests/report/build_report.py --junit reports --out docs/test-report/TEST-REPORT.md
```

## How a requirement's status is worked out

- **Pass:** every CI test named for it passed, and every manual check has a passing newest result.
- **Pending:** the CI tests passed; a manual check has no result yet.
- **Fail:** a CI test failed or the newest result of a manual check is a fail.
- **Not run:** no test results were given (for example a local build without `--junit`).

Integration tests (`tests/integration`) run against the real stack and are listed as extra
evidence; their run is recorded once under `STACK` in `manual-results.yaml`.

## Where the automated evidence lives

- `gateway/acceptance/`: one test per acceptance criterion at the URS's own numbers (20
  cross-merchant records, 20 sign-ins per staff role, the whole permission matrix for 6
  principals, 100 retries of one request, 50 simultaneous refunds, 150 requests a minute,
  20 unanswered payments, 50 payments during a screening outage, a card-number scan after a
  full run, the vault import boundary).
- `merchant/apps/webhooks/test_acceptance.py`: 50 tampered and 50 valid webhooks and status
  replies (NFR-INT-01).
- Older unit tests across the services that cover part of a requirement.

## Manual checks still to do

All 19 are listed with their time estimate at the top of `MANUAL-TESTS.md`. Most need the
demonstration server, so they are best run after the move to DigitalOcean and the new domain,
and at least 48 hours before any demo. NFR-USE-04 needs five people outside the team.
