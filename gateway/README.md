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
