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
