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
