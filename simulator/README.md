# Processing simulator

Stands in for the card network/issuer: enforces unique operation ids, records ledger entries and injects faults (lost responses, delays, declines).

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py runserver 8001
```

Needs PostgreSQL; the easiest way is `docker compose -f ../deploy/compose.yaml up db`.
