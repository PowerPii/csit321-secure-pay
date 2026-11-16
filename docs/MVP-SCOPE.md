# SecurePay MVP scope

This is the first buildable slice of the gateway. It is taken from the requirements document (Chapter 4, the "Must" functional requirements), the Figma wireframes (screens C1 to C9 and D1 to D6) and the architecture recommendation (`docs/architecture/ARCHITECTURE-RECOMMENDATION.md`).

## 1. The MVP in one sentence

A customer buys something in the demo shop, pays on the SecurePay hosted checkout with a synthetic card, gets screened by the rules-then-model fraud pipeline (allow, verify by code, or block), the simulated bank authorises or declines, the shop learns the result through a signed webhook, and a staff member can sign in with TOTP, see the payment, why it was screened that way, and capture, cancel or refund it.

If the demo shows that path end to end, plus the three failure stories below, the MVP is done.

## 2. Demo stories the MVP must pass

| # | Story | Proves |
| --- | --- | --- |
| S1 | Happy path: low-risk card, Allow, Authorised, merchant captures | Lifecycle, outbox, signed webhook, capture |
| S2 | Risky attempt: Simulated verification, correct code, Authorised | Risk pipeline, verification flow, Mailpit |
| S3 | Blocked: blocklisted card or burst of attempts, Blocked with reasons shown to the analyst | Rules, decision record, fraud review queue |
| S4 | Lost response: simulator times out, payment Unresolved, worker reconciles it with the original operation ID | Operation identity, reconciliation, no double charge |
| S5 | Duplicate request: merchant retries `POST /v1/payments` with the same Idempotency-Key | Idempotency (same body returns the stored response, different body returns 409) |
| S6 | Partial refunds, including two at the same time that would exceed the payment | Refund reservation under a row lock |

## 3. In and out

**In the MVP (Must requirements)**

| Area | What we build | Requirement IDs (Ch. 4.3) | Screens |
| --- | --- | --- | --- |
| Checkout & payment | Hosted checkout, card tokenised in the vault, amount bound server-side, screening, verification code, simulator call, unique payment reference, idempotent retry, Unresolved handling, result pages, emailed receipt with guest status link | CP 1 to 15 (verification: 3 attempts, then Blocked, as Fifa decided on 5 Nov 2026) | C3 to C7, C9 |
| Merchant API | `POST /v1/payments`, `GET /v1/payments/{id}`, capture, cancel, refunds, signed responses, API key auth (digest stored, shown once) | MM 3, TL 4 to 10 | none (API) |
| Webhooks | Outbox in the same transaction as the state change, HMAC-signed events, retries with backoff, approved HTTPS endpoints only | TL 6, 7, AS 13 | none |
| Reconciliation | Worker sweeps Unresolved payments with the original operation ID, escalates after max checks; 7-day auto-cancel of uncaptured authorisations | TL 11, 12 | D3 filter |
| Staff access | Sign-in with password + TOTP, lockout after 5 failures for 15 minutes, audit entry for every sign-in and state change | AA 14, 15, AS 10 | D1, D2 |
| Merchant onboarding | Admin creates/approves merchants (self-registration form can wait), one API key per merchant, webhook URL approved by admin | MM 1 to 3, 10, AS 1 | D3 (admin view) |
| Dashboard | Payments list and detail with the fraud decision, refund dialog, fraud review queue with case detail | FM 1, (FM 5, 7 as Should, cheap once D4 exists) | D3 to D6b |
| Fraud | Feature builder (current + prior-activity counts), deterministic rules, HistGradientBoosting model behind an adapter (fixed policy stub until the model is trained), versioned policy, `screening_unavailable` block | CP 4, FM 1 | C4, D4, D6 |
| Simulator | Approve / decline / timeout by test card number, status query by operation ID, capture, cancel, refund | SD 1 to 4 | none |
| Demo store | Products, cart, order summary, start checkout, order page; verify webhook and confirm via API before marking paid | SD 6, 7 | C1, C2, C8 |

**Not in the MVP (do later, in this order)**

1. Admin-editable fraud rules and the screening fallback setting (FM 2 to 4). The MVP hard-codes rules and always blocks when screening is unavailable.
2. Analyst search by card token, email or IP, blocklist UI, findings (FM 6, 7, 9). The MVP seeds the blocklist from a fixture.
3. API key rotation and revocation, merchant self-registration with email verification (MM 1, 4, 5). Self-registration was built in sprint 10. Rotation and revocation with the authenticator code, the last-key warning and logging of cross-merchant access attempts (FR-MER-04, 05, 09) followed in sprint 12.
4. Rate limits per key configurable by admin, security alerts, integrity hashes, key rotation, PCI self-checks (AS 8, 9, 12, 14, 15). DRF default throttles are on from day one. Security alerts (FR-ADM-08: locked accounts and repeated cross-merchant access, grouped with a count, on the dashboard and by email) were built in sprint 12.
5. Customer accounts, payment history, password reset, idle session warnings, PDPA data view (AA 1 to 13). Guests only in the MVP. Password reset was built in sprint 10 (staff accounts); customer accounts, sign-in lockout, payment history and customer password reset in sprint 11. The idle warning at 13 minutes (customer pages and dashboard), the privacy notice with consent at sign-up and checkout, and the customer's view and correction of their details (FR-ACC-10 to FR-ACC-13) followed on 16 Nov 2026.
6. Fraud reports and CSV export (FM 10), real-time analyst alerts (FM 8). Built on 16 Nov 2026: Fraud alerts (one per flagged payment, per-analyst read state, unread badge polled every 5 s) and Fraud reports (period, merchant, day or week trend, CSV export, audit-logged) on the staff dashboard.
7. PayNow QR (CP 16 to 18, SD 5). "Could" in the requirements; out unless the team decides otherwise.

## 4. Where each piece lives

| Piece | Code |
| --- | --- |
| Payment states and allowed transitions | `gateway/apps/payments/states.py` (tested) |
| Business rules (amount limits, TTLs, timeouts) | `GATEWAY_RULES` in `gateway/config/settings.py` |
| Merchant API routes | `gateway/apps/payments/urls.py`, `gateway/apps/refunds/urls.py` |
| Hosted checkout API | `gateway/apps/checkout/urls.py`; UI in `frontend/checkout/` |
| Staff API | `gateway/apps/internal/urls.py`; UI in `frontend/dashboard/` |
| Card fingerprint | `gateway/apps/vault/fingerprint.py` (tested) |
| Screening pipeline | `gateway/apps/risk/pipeline.py` (rules, model adapter, policy; tested) |
| Webhook signing | `gateway/apps/events/signing.py` (tested); verifier copy in `merchant/apps/webhooks/` |
| Worker jobs | `gateway/apps/events/management/commands/run_worker.py` |
| Test cards | `simulator/apps/operations/test_cards.py` |
| Shop pages | `merchant/apps/shop/` |

Every endpoint is routed but returns `501 Not Implemented` until someone builds it. Search for `NotImplementedView` to see what is left (after sprint 8, nothing in the MVP).

| Piece (sprint 8) | Code |
| --- | --- |
| Customer emails (receipts, guest status codes) | `gateway/apps/events/emails.py` (outbox, sent by the worker); receipt text in `gateway/apps/guest/receipts.py` |
| Guest status check | `gateway/apps/guest/` (API under `/guest/status/`); page `frontend/checkout/src/GuestStatus.tsx` at `https://gateway.localhost/guest/status` |
| Simulator notifications to the gateway | `gateway/apps/reconciliation/views.py` (`POST /internal/simulator/notifications`) |
| Simulator fault controls | `simulator/apps/faults/` (`/sim/faults`, only with `SIM_TEST_CONTROLS=1`) |
| Cross-service tests | `tests/integration/` |

## 5. Suggested build order (2-week sprints, risk first)

| Sprint | Goal | Done when |
| --- | --- | --- |
| 1 | Foundations: models for Merchant, ApiKey, Payment, Operation, IdempotencyRecord, OutboxEvent, AuditEvent; API key auth; `POST/GET /v1/payments` with idempotency | S5 passes as an API test (done 13 Nov 2026) |
| 2 | Checkout + vault + simulator authorise; result pages; demo shop starts checkout | S1 passes without screening (stub policy = Allow) (done 13 Nov 2026) |
| 3 | Outbox worker, signed webhooks, merchant verifies and confirms; capture / cancel; 7-day expiry job | S1 passes fully (done 13 Nov 2026) |
| 4 | Risk pipeline with rules + stub model; verification code via Mailpit; decision record | S2, S3 pass (done 13 Nov 2026; analyst view is the Django admin until sprint 6) |
| 5 | Reconciliation sweep, refunds with reservations | S4, S6 pass (done 13 Nov 2026; escalated operations and the admin re-check are in the Django admin until sprint 6) |
| 6 | Dashboard D1 to D6b on top of the APIs; TOTP and lockout | Staff can do every demo step from the UI (done 13 Nov 2026; plus merchant approval and the audit log for administrators) |
| 7 | Swap stub model for trained HistGradientBoosting artefact; parity test; latency check at 20 req/s | p95 screening <= 200 ms (done 13 Nov 2026: `hgb-fs02-2026-11-13` on feature schema fs-0.2, parity test against `research/features/gateway_schema.py`, p95 21.6 ms at 20/s; see `research/evaluation/hgb-fs02-2026-11-13.md`) |
| 8 | Close the MVP against the contracts: emailed receipt with guest status link (FR-CHK-15), guest status check by emailed code and screen C9 (API-CONTRACT.md section 8), simulator fault controls, record list and notifications (SIMULATOR-CONTRACT.md sections 8 and 9), cross-service tests | S1-S6 pass as automated tests on the Compose stack (done 13 Nov 2026: `tests/integration`, 11 tests with the trained model) |

After the MVP (roadmap in the team folder, `05-architecture/NEXT-PHASE-PLAN.md`):

| Sprint | Goal | Done when |
| --- | --- | --- |
| 9 | Deploy the stack on one server (`deploy/compose.prod.yaml`, `deploy/RUNBOOK.md`) | S1 to S3 work on the public URLs (done 16 Nov 2026: live on Google Cloud, smoke checks and all 11 integration tests pass on the server). **Milestone M2 (due 4 Dec 2026) met on 16 Nov 2026** |
| 10 | Accounts part 1: password reset by emailed link (FR-ACC-07 to FR-ACC-09), merchant self-registration with email verification and administrator notice (FR-MER-01, FR-MER-02), webhook address submitted by the merchant (FR-MER-10), D7 and D8 screens | A new merchant signs up, verifies its email, is approved, gets a key and receives a webhook (`gateway/apps/merchants/test_registration.py`) |
| 11 | Accounts part 2: customer registration, sign-in with lockout, payment history (FR-ACC-01 to FR-ACC-04), customer password reset and ending sessions on a password change (FR-ACC-07, FR-ACC-08), screens C10 to C12 under `/account/` (`gateway/apps/customers`, `frontend/checkout/src/Account.tsx`) | A customer pays signed in and sees the payment in their history (`gateway/apps/customers/tests.py`) |

The research track (IEEE-CIS experiment in `research/`) runs alongside and hands over a versioned model artefact by sprint 7.

## 6. Open points to confirm with the team

1. **Guest status access.** Fifa chose (5 Nov 2026) that guests check status with a one-time code rather than only a long-lived link. Designed in `contracts/API-CONTRACT.md` section 8 (confirmed by Fifa 13 Nov 2026): the receipt link only pre-fills the payment reference; the guest enters reference + checkout email, receives a 6-digit code valid 10 minutes, and 3 wrong codes lock the check for 15 minutes. This replaces the `checkout/status/<token>` route; `GUEST_STATUS_LINK_TTL_DAYS` is removed from `GATEWAY_RULES`.
2. **Amount check against the merchant's order record (CP FR 3).** Settled 13 Nov 2026 (`contracts/API-CONTRACT.md` section 11): the payment the merchant created is the order record, as with a Stripe PaymentIntent.
3. **Signed transaction responses (TL FR 8).** The MVP signs API responses with the merchant's webhook secret in a `SecurePay-Signature` header, the same scheme as webhooks.
