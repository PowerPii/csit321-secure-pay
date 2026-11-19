# Gateway

Modular Django + DRF gateway (merchant API, hosted checkout, dashboards' API, vault, risk) plus the outbox worker.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install --require-hashes --no-deps -r requirements-dev.lock
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py runserver 8000
```

Needs PostgreSQL; the easiest way is `docker compose -f ../deploy/compose.yaml up db`.

## Try the merchant API (sprint 1)

```bash
python manage.py create_merchant "Demo Shop"     # prints the API key and signing secret once
curl -X POST http://localhost:8000/v1/payments \
  -H "Authorization: Bearer sp_test_..." \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"amount": 4590, "currency": "SGD", "order_reference": "ORD-1", "return_url": "https://shop.localhost/return"}'
curl http://localhost:8000/v1/payments/pay_... -H "Authorization: Bearer sp_test_..."
```

Built so far: `POST /v1/payments` and `GET /v1/payments/{id}` as in `contracts/API-CONTRACT.md`
(API key auth, signed replies, request IDs, contract error bodies, idempotency, 100 requests a
minute per key). Demo story S5 is `apps/payments/test_idempotency.py::test_s5_duplicate_request`.

| Where | What |
| --- | --- |
| `apps/merchants/auth.py`, `apps/merchants/api.py` | API key auth, merchant status check, per-key throttle, reply signing |
| `apps/payments/idempotency.py` | Idempotency-Key handling (contract section 5) |
| `apps/payments/views.py`, `serializers.py` | Create and read payments; the Payment object |
| `apps/common/errors.py` | Contract error format for every DRF error |
| `apps/events/outbox.py` | `record_payment_event`: outbox row in the state change's transaction |
| `apps/audit/models.py` | Append-only audit trail (also enforced by a database trigger) |

Tests check every reply against `contracts/schemas/*.schema.json`.

## Hosted checkout (sprint 2)

The payment's `checkout_url` opens `frontend/checkout` at `/pay/cs_...`, which calls the
same-origin JSON API under `/checkout/`:

| Route | What |
| --- | --- |
| `GET /checkout/{cs}` | Order summary and state (C3; C6/C7 after a reload). Expires the session after 1 hour (`payment.expired`) |
| `POST /checkout/{cs}/card` | Card to the vault; the payment keeps token, brand, last four and fingerprint |
| `POST /checkout/{cs}/submit` | Screening, then: Allow -> operation row committed, then `/sim/authorise` (`authorised`, `declined` or `unresolved`); Verify -> `verification_required` and a code by email; Block -> `blocked` |
| `POST /checkout/{cs}/verify` | `{code}` (C5). Right code: on to the simulator. Wrong: `400 code_incorrect`; the 3rd wrong code blocks (`verification_failed`). Old code: `400 code_expired` |
| `POST /checkout/{cs}/verify/resend` | New code, replaces the old one; 30 s cooldown (`429 resend_too_soon`), at most 5 codes (`429 too_many_codes`) |
| `GET /checkout/{cs}/result` | Same object as the session |

| Where | What |
| --- | --- |
| `apps/vault/service.py` | `tokenise` / `take` (decrypt and delete on submit) / `discard`; AES-256-GCM with `VAULT_ENCRYPTION_KEY`, own DB alias |
| `apps/checkout/service.py` | The checkout flow and the customer-facing result (no fraud reasons) |
| `apps/payments/processor.py` | Simulator client: bearer key, 2 s / 10 s timeouts (proposal S1), only signed replies count |
| `apps/payments/processing.py` | Applies an answer (approved, declined, no_record, none) to the operation and payment, with outbox event and audit. Reconciliation reuses it in sprint 5 |
| `apps/risk/screening.py` | Runs the pipeline (sprint 4, below) and writes the decision record |

## Fraud screening (sprint 4)

`apps/risk` screens every payment when the customer pays, before the simulator: **features -> lists and rules -> model -> policy** (architecture section 7).

| Where | What |
| --- | --- |
| `apps/risk/features.py` | Feature schema `fs-0.1`: amount plus prior-activity counts per card fingerprint, email hash and IP hash (10 min to 30 days), only from earlier attempts |
| `apps/risk/pipeline.py` | `rules-0.1` (block list, review list, 5+ attempts on one card in 10 minutes -> block, over S$500 -> verify) and `policy-0.1` (score >= 0.5 verify, >= 0.9 block) |
| `apps/risk/scoring.py` | Model interface. `StubModel` (`stub-0`, score 0) until a trained HistGradientBoosting artefact is installed (`model_artifacts/README.md`) |
| `apps/risk/screening.py` | Savepoint + Postgres `statement_timeout` of 500 ms; any error or overrun -> `blocked`, `screening_unavailable`, decision `not_screened`, never sent to the simulator (FR-FRD-04) |
| `apps/risk/models.py` | `ScreeningEvent`: one per attempt; score, reasons, feature values, model / rules / policy versions, time taken. `RiskListEntry`: block and review lists |
| `apps/checkout/verification.py` | 6-digit codes (HMAC-hashed, 10 minutes), queued in the outbox and emailed by the worker: real addresses straight through Resend on the live server, demo addresses to Mailpit only (`apps/common/mail_routing.py`) |

Analysts read decisions in the Django admin (Risk -> Screening events) until the dashboard (D4, D6) lands in sprint 6. Demo data: `python manage.py seed_risk_lists` (the Compose stack runs it on start) lists card **4000 0000 0000 0101** and `blocked@example.com` for blocking and `review@example.com` for verification. Any order over S$500 asks for a code too. The burst rule counts every attempt, including blocked ones, so after an outage test or many declines on one test card, wait 10 minutes or use another card.

Confirmed by Fifa 13 Nov 2026: hard cut-off 500 ms with a p95 target of 200 ms; the card stays encrypted in the vault until the code is entered; resend after 30 s, at most 5 codes per payment.

Measuring: `python manage.py benchmark_screening` screens 1,000 payments over 5,000 earlier events inside a rolled-back transaction and reports p50/p95/p99 against NFR-PER-02. Outage test (DEBUG only): `RISK_SIMULATE_OUTAGE=error` or `slow` makes every screening unavailable.

Running locally: `python manage.py migrate && python manage.py migrate --database=vault`. If the
vault role shares your database and role, set `VAULT_DB_NAME` to a second database so the two
migration histories stay apart.
