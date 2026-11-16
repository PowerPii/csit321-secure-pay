# Refactoring notes — 17 November 2026

Applied to `main` at the project owner’s request.

The changes consolidate repeated boundary code and separate account pages by responsibility. No database models, migrations, payment state transitions, ledger rules, deployment configuration, or dependency versions were changed.

## Code map

- `frontend/checkout/src/http.ts`: common same-origin JSON transport for checkout, customer accounts and guest status. API modules still define their own response types and errors; lockout delays and remaining verification attempts are preserved.
- `frontend/checkout/src/Account.tsx`: account navigation and session lifecycle (738 lines reduced to 153). Individual pages now live in `account/SignIn.tsx`, `History.tsx`, `Profile.tsx`, `Password.tsx` and `Reset.tsx`. Shared account fields and validation live in `account/forms.tsx`.
- `frontend/checkout/src/ui.tsx`: shared form fields and definition-list rows, formerly imported from the payment application.
- `gateway/apps/common/views.py`: the common JSON-only public view configuration, no-store/noindex response headers, strict object validation, and a separate tolerant body helper for endpoints that validate fields themselves. Each API still owns its authentication/session checks. Removed the unused 501 placeholder.
- `simulator/apps/common/validation.py`: shared JSON object parsing, invalid-input errors and integer checks, used by operation and fault-rule validation.

Production source across the changed and new files is 88 lines shorter overall. Splitting the account pages improves navigation but is not counted as deleting their functionality. The new transport regression tests add 60 lines of coverage.

## Boundaries retained

Gateway, merchant and simulator remain independently deployable. Similar signature, settings and payment-domain code across these services was not merged: CONTRIBUTING.md explicitly forbids cross-service imports. The two frontend idle hooks remain local to their builds under the existing shared-code policy. Payment concurrency, idempotency, vault isolation, audit and reconciliation logic were left intact.

Large dashboard type definitions and reference content were not compressed merely to reduce line count. The dashboard and merchant regression suites were run unchanged.

## Validation

| Suite | Result |
| --- | --- |
| Gateway | 491 passed, 1 skipped |
| Simulator | 77 passed |
| Merchant | 36 passed |
| Checkout | 53 passed, including 17 new transport regression cases |
| Dashboard | 42 passed |

- Checkout and dashboard TypeScript checks and production builds passed.
- Ruff passed for all three Python services.
- Django system checks and migration-drift checks passed for all three services.
- Backend tests used an isolated local PostgreSQL 18 database on port 55432. GitHub CI uses PostgreSQL 17 and should still run before merging.
- The optional installed-model test was skipped because the trained model artifact is absent from this clone.
- The dashboard build retains its existing large-bundle warning.
- Full Docker cross-service integration tests, deployed-site tests, dependency audits, and the unchanged marketing website build were not run in this refactor.

These results describe local validation before publication. GitHub CI and any subsequent deployment report their own results.
