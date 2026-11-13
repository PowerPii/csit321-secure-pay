# Gateway

Modular Django + DRF gateway (merchant API, hosted checkout, dashboards' API, vault, risk) plus the outbox worker.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
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
| `POST /checkout/{cs}/submit` | Screening (stub Allow until sprint 4), operation row committed, then `/sim/authorise`; answers `authorised`, `declined` or `unresolved` |
| `GET /checkout/{cs}/result` | Same object as the session |

| Where | What |
| --- | --- |
| `apps/vault/service.py` | `tokenise` / `take` (decrypt and delete on submit) / `discard`; Fernet with `VAULT_ENCRYPTION_KEY`, own DB alias |
| `apps/checkout/service.py` | The checkout flow and the customer-facing result (no fraud reasons) |
| `apps/payments/processor.py` | Simulator client: bearer key, 2 s / 10 s timeouts (proposal S1), only signed replies count |
| `apps/payments/processing.py` | Applies an answer (approved, declined, no_record, none) to the operation and payment, with outbox event and audit. Reconciliation reuses it in sprint 5 |
| `apps/risk/screening.py` | Sprint 2 stub: always Allow |

Running locally: `python manage.py migrate && python manage.py migrate --database=vault`. If the
vault role shares your database and role, set `VAULT_DB_NAME` to a second database so the two
migration histories stay apart.
