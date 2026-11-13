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

# 2. checkout page and staff dashboard bundles (Caddy serves them at
#    https://gateway.localhost/pay/... and https://gateway.localhost/dashboard/)
(cd frontend/checkout && npm install && npm run build)
(cd frontend/dashboard && npm install && npm run build)

# 3. whole stack
docker compose -f deploy/compose.yaml up --build
# https://gateway.localhost   https://shop.localhost   https://mail.localhost

# 4. register the demo shop as a merchant and give it its API key and signing secret
docker compose -f deploy/compose.yaml exec gateway python manage.py create_merchant "Demo Shop" \
  --webhook-url https://shop.localhost/webhooks/securepay \
  | tee /dev/stderr | awk '/API key:/{print $3 > "deploy/secrets/securepay_api_key"}
                           /Signing secret:/{print $3 > "deploy/secrets/securepay_signing_secret"}'
docker compose -f deploy/compose.yaml restart merchant

# 5. staff accounts for the dashboard (password prompt, 12+ characters; the authenticator
#    app is set up at the first sign-in from the QR code on the two-step page)
docker compose -f deploy/compose.yaml exec gateway python manage.py create_staff ops@demoshop.sg \
  --role merchant_operator --merchant mer_... --name "Aisha Rahman"   # the ID create_merchant printed
docker compose -f deploy/compose.yaml exec gateway python manage.py create_staff analyst@securepay.sg \
  --role fraud_analyst --name "Daniel Lim"
docker compose -f deploy/compose.yaml exec gateway python manage.py create_staff admin@securepay.sg \
  --role administrator --name "Mei Tan"
```

Staff dashboard: https://gateway.localhost/dashboard/. Sign-in is a password and a 6-digit authenticator code; five failures (wrong password or wrong code) lock the account for 15 minutes and email the account holder (Mailpit). Sessions end after 15 idle minutes. Merchant operators see their own merchant's payments and capture, cancel and refund them; fraud analysts work the review queue across all merchants; administrators see every merchant read-only, approve merchants (the API key and signing secret are shown once), read the audit log and re-check escalated operations.

Then shop at https://shop.localhost and pay with a test card from `contracts/SIMULATOR-CONTRACT.md` section 5 (4242 4242 4242 4242 approves, 4000 0000 0000 0002 declines, 4000 0000 0000 0119 loses the answer).

Fraud screening (demo stories S2 and S3): an order over S$500, or the email `review@example.com`, asks for a 6-digit code, which arrives in Mailpit at https://mail.localhost; three wrong codes block the payment. Card 4000 0000 0000 0101 or the email `blocked@example.com` is blocked, and so is a sixth attempt on one card within 10 minutes. Screening decisions, with score, reasons, features and versions, are on each payment's page in the dashboard; blocked and verified attempts are in the fraud review queue, where analysts record a finding (confirmed fraud, false positive or inconclusive) without changing the payment.

Fraud model (sprint 7): out of the box the gateway runs the stub model (score 0, the rules decide). To run the trained HistGradientBoosting model, copy its folder `hgb-fs02-2026-11-13` (team folder `02-research/gateway-model/`, or rebuild it with `research/training/train_gateway_model.py`) into `gateway/apps/risk/model_artifacts/`, then `echo RISK_MODEL_VERSION=hgb-fs02-2026-11-13 > deploy/.env` and `docker compose -f deploy/compose.yaml up -d gateway`. A score of 0.11 or more asks for a verification code and 0.22 or more blocks (`model_score_medium` / `model_score_high` in the decision). `docker compose -f deploy/compose.yaml exec gateway python manage.py loadtest_screening` checks the 200 ms p95 target at 20 screenings a second. Details and limits: `gateway/apps/risk/model_artifacts/README.md`, `research/evaluation/hgb-fs02-2026-11-13.md`.

The gateway worker sends the shop a signed webhook for each status change; the shop confirms it with a signed `GET` before marking the order paid. To ship (capture) or cancel an order, as the merchant in demo story S1, sign in to the dashboard as the merchant operator and use Capture or Cancel authorisation on the payment's page, or:

```bash
docker compose -f deploy/compose.yaml exec merchant python manage.py settle_order capture ORD-1001
docker compose -f deploy/compose.yaml exec merchant python manage.py settle_order cancel ORD-1002
```

(or select the payment in the shop's Django admin and use the Capture / Cancel actions).

Refunds (demo story S6): each refund reserves its amount under a lock on the payment, so refunds that together exceed the captured amount cannot both go through, even at the same moment. In the dashboard, use Refund on a captured payment (try the same refund in two tabs at once); or:

```bash
docker compose -f deploy/compose.yaml exec merchant python manage.py settle_order refund ORD-1001 --amount 500 --reason "One item returned"
```

Lost answers (demo story S4): pay with 4000 0000 0000 0119 (the bank approves but the answer is lost) or 4000 0000 0000 0127 (the answer comes too late). After 10 seconds the checkout page says "We're confirming your payment" and the payment is Unresolved. The gateway worker then asks the simulator about the same operation ID, 30 seconds later and then at 1, 2, 5, 10 and 20 minutes; the first check finds the approval, the payment becomes Authorised without a second charge, and the page updates itself. Card 4000 0000 0000 0135 loses the request instead: the check finds no record, retires the ID, and the payment ends Declined (`not_processed`). An operation still without an answer after the sixth check is escalated; administrators find it with the "Escalated operations" tile on the dashboard's payments page and use "Re-check with the simulator" on the payment. Nobody can set an outcome by hand.

Receipts and guest status (sprint 8): every authorised payment gets an emailed receipt (Mailpit) with its reference and a link to https://gateway.localhost/guest/status?ref=SP-.... The link only fills in the reference: the guest also enters the email they paid with, receives a 6-digit code, and then sees that one payment, read-only, for 15 minutes. The reply is the same whether or not the details match, and three wrong codes lock the check for 15 minutes.

Fault controls (sprint 8, SIMULATOR-CONTRACT.md section 8): with `SIM_TEST_CONTROLS=1` (the Compose default; set it to 0 in a demo where nobody should inject faults) the simulator accepts fault rules at `https://simulator.localhost/sim/faults` with the test-control key in `deploy/secrets/simulator_test_control_key`, which the gateway never holds. For example, lose the reply to the next capture and also send two signed notifications 12 seconds later:

```bash
KEY=$(cat deploy/secrets/simulator_test_control_key)
curl -s https://simulator.localhost/sim/faults -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"match": {"operation_type": "capture"}, "action": "drop_response", "remaining": 1}'
curl -s https://simulator.localhost/sim/faults -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"match": {"operation_type": "capture"}, "action": "notify", "delay_ms": 12000, "copies": 2, "remaining": 1}'
curl -s -X DELETE https://simulator.localhost/sim/faults -H "Authorization: Bearer $KEY"   # clear all rules
```

Automated cross-service tests for S1-S6, receipts, guest status and fault controls: `tests/integration/README.md`.

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
