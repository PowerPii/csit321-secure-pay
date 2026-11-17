# Codebase structural audit — 17 November 2026

The audit starts from `955eb29` (the first refactor on main). It covers the repository's application areas, using a source inventory, file sizes, Python function-body duplication, import/dependency review, reference searches for unused scaffolding, and focused reading of candidate modules. This is a maintainability audit, not a claim that every line has received a security review.

## Decisions by area

| Area | Finding | Action |
| --- | --- | --- |
| Hosted checkout | A 524-line file combined routing, card entry, verification, expiry timers and all result screens. Card entry and verification repeated their expiry handling. Guest status imported its shell from the whole checkout app. | Extract focused checkout modules, share the expiry hook, and move the shell into UI primitives. |
| Customer accounts | Payment-history queries and display labels lived alongside passwords, sessions and registration. | Move read-only history into `apps/customers/history.py`; retain customer scoping and existing authentication behavior. |
| Staff backend | Seven view modules and a test imported query-parameter helpers from the payment endpoint file. Payment-detail serialization and timeline construction also lived there. | Move query helpers into `apps/internal/query_params.py` and payment-detail construction into `apps/internal/payment_details.py`. Callers use explicit imports. |
| Staff dashboard | Six lists repeated page-count and previous/next controls. Fraud rules, history search, blocklist management and the reusable dialog shared one 420-line file. | Add shared pagination and split fraud tools by responsibility, retaining the route export surface. |
| Payments, refunds, vault and reconciliation | Explicit state transitions, atomic operations, idempotency and domain-specific failure handling are meaningful code, even where operations resemble one another. | Retain these boundaries and algorithms. Remove only confirmed comment-only scaffolds. |
| Simulator | Operation/fault input primitives were already consolidated by the first refactor. Ledger, fault injection and operation handling have distinct responsibilities. | Keep runtime logic intact; remove two comment-only ledger scaffold files. |
| Merchant | Storefront views, gateway HTTP calls, settlement behavior and webhook verification already have distinct modules. | Keep the existing structure; run its regression suite. |
| Research | Offline replay and runtime feature construction are deliberately separate and checked by parity tests. The training script encodes temporal splits and feature availability explicitly. | Preserve experiment logic, data boundaries and artifacts; rely on existing parity coverage. No training run or dataset access. |
| Marketing website | Large reference files are content, and pages already reuse layout/documentation components. Routes already use lazy loading. | Retain source structure; verify types and production build. |
| Contracts and deployment | Contracts provide executable schema/example checks. Deployment scripts have separate provisioning, secrets, backup, smoke-check and rollout responsibilities. | Keep behavior unchanged; validate contracts and shell syntax. |

## New module map

- `frontend/checkout/src/App.tsx`: 88-line session loading, polling and step selection, down from 524 lines.
- `frontend/checkout/src/checkout/CardForm.tsx`: card-entry form and submission.
- `frontend/checkout/src/checkout/VerifyCode.tsx`: emailed-code verification and resend.
- `frontend/checkout/src/checkout/Results.tsx`: processing, approved and incomplete results.
- `frontend/checkout/src/checkout/session.ts`: shared expiry clock/reload behavior and form props.
- `frontend/checkout/src/checkout/OrderSummary.tsx` and `icons.tsx`: checkout presentation.
- `frontend/dashboard/src/components/Pagination.tsx`: controls shared by payments, audit, fraud alerts, security alerts, reviews and history search. Filter changes remain owned by each route.
- `frontend/dashboard/src/components/BlocklistDialog.tsx`: reusable blocklist action.
- `frontend/dashboard/src/routes/Blocklist.tsx`, `HistorySearch.tsx`, `FraudRules.tsx`: focused routes. `FraudTools.tsx` preserves their public exports.
- `gateway/apps/internal/query_params.py`: date parsing, bounded integers and dashboard time zone, independent of HTTP endpoint modules.
- `gateway/apps/internal/payment_details.py`: payment serialization, action availability and timeline assembly. Payment access checks remain in the callers.
- `gateway/apps/customers/history.py`: owner-scoped payment history and customer-visible details.

The staff payment view file is now 233 lines rather than 421. The customer account service is 443 rather than 505. Extracted Python function bodies were compared structurally with the originals; only the intended helper names changed.

## Removed scaffolds

Twelve files contained only Django-generated placeholder comments and had no code or imports. Reference searches found no explicit consumers. They were removed from gateway accounts, audit, merchants, events, risk, vault, internal and reconciliation, and simulator ledger. Django app/package files and migrations remain. The vault admin file was retained because it documents the intentional absence of card data from the admin interface.

## Why some duplication remains

Service-local settings loaders, signature code and service entry points remain independent under CONTRIBUTING.md's cross-service import rule. The frontend idle hooks remain local under the repository's existing shared-code policy. This pass does not introduce a shared package or change the Docker build architecture solely to save a few lines.

Large API type declarations, reference content and explicit security/payment checks are not dead code. They were not shortened just to lower file-size totals. More focused modules add imports: this pass adds 37 net production lines while removing duplicated behavior and twelve empty files. Combined with the initial refactor, production source is 51 lines shorter than PR #33. Regression tests are additional.

## Validation and limits

- Gateway: 491 passed, one optional installed-model test skipped.
- Simulator: 77 passed.
- Merchant: 36 passed.
- Checkout: 55 passed, including two new expiry/cleanup cases.
- Dashboard: 46 passed, including four new pagination cases.
- All three frontend production builds and type checks passed.
- Ruff, Django system checks and migration-drift checks passed for all Python services.
- Contracts: 20 schema/OpenAPI files and 21 examples passed.
- Deployment scripts: shell syntax passed without running the scripts.

Total: 705 passing tests and one skip. Tests use isolated local PostgreSQL 18; CI uses PostgreSQL 17. The dashboard retains its existing large-bundle warning. Full Compose integration tests, live deployment verification and separate vulnerability/security scans were not run locally. Existing CI scan/audit jobs still need to report their own results on the published commit.

No database schema, payment behavior, public API contract or dependency version change is intended. Screens retain their existing markup, labels and styling; no visual redesign was performed.
