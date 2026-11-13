# SecurePay: secure online payment gateway with fraud detection

CSIT321 final year project (FYP-26-S4-36). A simulated card payment gateway with a hosted checkout, a merchant API with signed webhooks, a staff dashboard, and a rules-then-model fraud screening pipeline trained on IEEE-CIS.

**Start here:** [`docs/MVP-SCOPE.md`](docs/MVP-SCOPE.md) says what the MVP includes, the six demo stories it must pass, and the sprint order. The full design is in [`docs/architecture/ARCHITECTURE-RECOMMENDATION.md`](docs/architecture/ARCHITECTURE-RECOMMENDATION.md); wireframes are in [Figma](https://www.figma.com/design/RK2NOWzPLfnLbAIqcswi3E).

Status: skeleton. Every MVP route is wired and returns `501 Not Implemented` until built. Real code so far: the payment state machine, card fingerprinting, the screening pipeline with a stub model, webhook signing and verification, and the simulator's test cards, each with tests.

| Folder | Trust domain | What |
| --- | --- | --- |
| `gateway/` | Gateway | Modular Django 5.2 + DRF app. Modules in `gateway/apps/`: accounts, merchants, checkout, vault, payments, refunds, risk, events, reconciliation, audit, internal. Each module's `__init__.py` states what it owns and its key rule. |
| `gateway/apps/events/management/commands/run_worker.py` | Gateway | The outbox / reconciliation / expiry worker (`python manage.py run_worker`) |
| `simulator/` | Simulator | Processing simulator: `operations`, `ledger`, `faults` |
| `merchant/` | Merchant | Demo storefront in Django templates: `shop`, `webhooks` |
| `frontend/checkout/` | Gateway | Hosted checkout bundle (Vite + React + TS, strict CSP) |
| `frontend/dashboard/` | Gateway | Merchant / admin / analyst SPA (Vite + React + TS + MUI) |
| `research/` | Offline | Notebooks, shared feature definitions, training and evaluation; produces model artifacts |
| `contracts/` | Shared | OpenAPI files, event JSON Schemas, generated TS types |
| `tests/integration/` | All | Cross-service end-to-end, recovery, concurrency and security tests |
| `deploy/` | VM | Docker Compose, Caddyfile, Postgres init, secrets templates, backups |
| `docs/` | All | MVP scope, architecture, diagrams |
| `.github/workflows/ci.yml` | CI | Lint, checks, tests on real Postgres, dependency audits, gitleaks |

## Quick start

```bash
# 1. secrets (see deploy/secrets/README.md)
cd deploy/secrets && for f in *.example; do python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "${f%.example}"; done && cd ../..
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > deploy/secrets/vault_encryption_key

# 2. checkout page bundle (Caddy serves it at https://gateway.localhost/pay/...)
(cd frontend/checkout && npm install && npm run build)

# 3. whole stack
docker compose -f deploy/compose.yaml up --build
# https://gateway.localhost   https://shop.localhost   https://mail.localhost

# 4. register the demo shop as a merchant and give it its API key and signing secret
docker compose -f deploy/compose.yaml exec gateway python manage.py create_merchant "Demo Shop" \
  | tee /dev/stderr | awk '/API key:/{print $3 > "deploy/secrets/securepay_api_key"}
                           /Signing secret:/{print $3 > "deploy/secrets/securepay_signing_secret"}'
docker compose -f deploy/compose.yaml restart merchant
```

Then shop at https://shop.localhost and pay with a test card from `contracts/SIMULATOR-CONTRACT.md` section 5 (4242 4242 4242 4242 approves, 4000 0000 0000 0002 declines, 4000 0000 0000 0119 loses the answer).

For day-to-day work on one service, see that service's README (venv + `runserver`).

## Rules that shape the code

- Services talk only over authenticated HTTPS APIs; each has its own database and credentials.
- Only `contracts/` and `research/features/` are shared. The payment state machine is **not** shared between gateway and simulator.
- Card data lives only in `gateway/apps/vault`, on its own DB role. Logs, audit events, outbox payloads, idempotency fingerprints and screening features must never contain it (enforce with tests).
- No Redis, Celery, Kafka or Kubernetes.
- Python 3.12 everywhere; scikit-learn pinned to the same version in `gateway/` and `research/`.

## Business rules

The section 11 decisions (SGD only, S$0.50 to S$10,000, 24 h idempotency, 7-day authorisation expiry, 10-minute verification code, 500 ms screening timeout, and so on) live in one place: `GATEWAY_RULES` in `gateway/config/settings.py`. Open points still to confirm are listed at the end of `docs/MVP-SCOPE.md`.

## Running checks locally

```bash
cd gateway && python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
DJANGO_DEBUG=1 python manage.py check && ruff check . && pytest
cd ../frontend/dashboard && npm install && npx tsc --noEmit && npm test
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branches and pull requests.
