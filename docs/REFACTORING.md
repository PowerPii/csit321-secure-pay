# Refactoring notes — 17 November 2026

Applied to `main` at the project owner’s request.

The changes consolidate repeated boundary code and separate UI and backend responsibilities. The follow-up repository-wide structural audit is recorded in `docs/CODEBASE-AUDIT.md`. Database fields, migrations, payment state transitions, ledger rules, deployment configuration, and dependency versions were not changed; an empty reconciliation models scaffold was removed.

## Code map

- `frontend/checkout/src/http.ts`: common same-origin JSON transport for checkout, customer accounts and guest status. API modules still define their own response types and errors; lockout delays and remaining verification attempts are preserved.
- `frontend/checkout/src/Account.tsx`: account navigation and session lifecycle (738 lines reduced to 153). Individual pages now live in `account/SignIn.tsx`, `History.tsx`, `Profile.tsx`, `Password.tsx` and `Reset.tsx`. Shared account fields and validation live in `account/forms.tsx`.
- `frontend/checkout/src/ui.tsx`: shared form fields and definition-list rows, formerly imported from the payment application.
- `gateway/apps/common/views.py`: the common JSON-only public view configuration, no-store/noindex response headers, strict object validation, and a separate tolerant body helper for endpoints that validate fields themselves. Each API still owns its authentication/session checks. Removed the unused 501 placeholder.
- `simulator/apps/common/validation.py`: shared JSON object parsing, invalid-input errors and integer checks, used by operation and fault-rule validation.

The initial refactor removed 88 net production lines. The follow-up structural refactor adds 37 production lines, chiefly imports and module boundaries, for a combined net reduction of 51 lines from PR #33. Tests are excluded from those counts. Moving a page into its own module is not counted as deleting its functionality.

## Boundaries retained

Gateway, merchant and simulator remain independently deployable. Similar signature, settings and payment-domain code across these services was not merged: CONTRIBUTING.md explicitly forbids cross-service imports. The two frontend idle hooks remain local to their builds under the existing shared-code policy. Payment concurrency, idempotency, vault isolation, audit and reconciliation logic were left intact.

Large dashboard type definitions and reference content were not compressed merely to reduce line count. The merchant regression suite was run unchanged. Dashboard pagination now has dedicated regression coverage.

## Validation

| Suite | Result |
| --- | --- |
| Gateway | 491 passed, 1 skipped |
| Simulator | 77 passed |
| Merchant | 36 passed |
| Checkout | 55 passed, including transport and session-expiry regression cases |
| Dashboard | 46 passed, including shared-pagination regression cases |

- Checkout, dashboard and marketing website TypeScript checks and production builds passed.
- Contracts passed: 20 schema/OpenAPI documents and 21 examples.
- All deployment shell scripts passed syntax checks.
- Ruff passed for all three Python services.
- Django system checks and migration-drift checks passed for all three services.
- Backend tests used an isolated local PostgreSQL 18 database on port 55432. GitHub CI uses PostgreSQL 17 and should still run before merging.
- The optional installed-model test was skipped because the trained model artifact is absent from this clone.
- The dashboard build retains its existing large-bundle warning.
- Full Docker cross-service integration tests, deployed-site tests and separate dependency/security scans were not run locally in this refactor. GitHub CI retains its audit and scan jobs.

These results describe local validation before publication. GitHub CI and any subsequent deployment report their own results.
