# Demo merchant

Test-harness storefront in plain Django templates: products, orders, and a receiver for HMAC-signed gateway events.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py runserver 8002
```

Needs PostgreSQL; the easiest way is `docker compose -f ../deploy/compose.yaml up db`.

## The shop (sprint 2)

C1 products and cart, C2 contact and delivery, C8 order page. The shop is an ordinary SecurePay
merchant: set `SECUREPAY_API_KEY` and `SECUREPAY_SIGNING_SECRET` (env or Compose secrets) to
what the gateway's `create_merchant "Demo Shop"` printed, and `SECUREPAY_API_URL`.

- Placing an order saves a payment attempt with its own Idempotency-Key, then calls
  `POST /v1/payments` and sends the customer to the `checkout_url`. A retry after a lost reply
  reuses the key; "Try another card" after a decline makes a new payment.
- The return from checkout is navigation only. The order is marked paid only from a signed
  `GET /v1/payments/{id}` that matches the order's reference and amount. Until webhooks arrive
  (sprint 3) the order page asks the gateway itself and refreshes while the payment is pending.
- Orders are visible only to the browser session that placed them.
