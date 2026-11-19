# Demo walkthrough

A guided tour of the running stack, story by story. It assumes you have followed the [quick start](../README.md#quick-start) and seeded the demo with `bash deploy/demo.sh seed`. Every address below is the local one; on the public server swap `localhost` for the server's domain (see [`deploy/RUNBOOK.md`](../deploy/RUNBOOK.md)).

## Staff dashboard

Open https://gateway.localhost/dashboard/. Sign-in is a password and a 6-digit authenticator code; five failures (wrong password or wrong code) lock the account for 15 minutes and email the account holder (Mailpit). Sessions end after 15 idle minutes. Merchant operators see their own merchant's payments and capture, cancel and refund them; fraud analysts work the review queue across all merchants; administrators see every merchant read-only, approve merchants (the API key and signing secret are shown once), read the audit log and re-check escalated operations.

## Paying in the demo shop

Shop at https://shop.localhost and pay with a test card from `contracts/SIMULATOR-CONTRACT.md` section 5 (4242 4242 4242 4242 approves, 4000 0000 0000 0002 declines, 4000 0000 0000 0119 loses the answer).

## Fraud screening (stories S2 and S3)

An order over S$500, or the email `review@example.com`, asks for a 6-digit code, which arrives in Mailpit at https://mail.localhost; three wrong codes block the payment. Card 4000 0000 0000 0101 or the email `blocked@example.com` is blocked, and so is a sixth attempt on one card within 10 minutes. Screening decisions, with score, reasons, features and versions, are on each payment's page in the dashboard; blocked and verified attempts are in the fraud review queue, where analysts record a finding (confirmed fraud, false positive or inconclusive) without changing the payment.

## Running the trained fraud model

Out of the box the gateway runs the stub model (score 0, the rules decide). To run the trained HistGradientBoosting model, copy its folder `hgb-fs02-2026-11-13` (team folder `02-research/gateway-model/`, or rebuild it with `research/training/train_gateway_model.py`) into `gateway/apps/risk/model_artifacts/`, then `echo RISK_MODEL_VERSION=hgb-fs02-2026-11-13 > deploy/.env` and `docker compose -f deploy/compose.yaml up -d gateway`. A score of 0.11 or more asks for a verification code and 0.22 or more blocks (`model_score_medium` / `model_score_high` in the decision). `docker compose -f deploy/compose.yaml exec gateway python manage.py loadtest_screening` checks the 200 ms p95 target at 20 screenings a second. Details and limits: `gateway/apps/risk/model_artifacts/README.md`, `research/evaluation/hgb-fs02-2026-11-13.md`.

## Webhooks, capture and cancel (story S1)

The gateway worker sends the shop a signed webhook for each status change; the shop confirms it with a signed `GET` before marking the order paid. To ship (capture) or cancel an order, as the merchant in demo story S1, sign in to the dashboard as the merchant operator and use Capture or Cancel authorisation on the payment's page, or:

```bash
docker compose -f deploy/compose.yaml exec merchant python manage.py settle_order capture ORD-1001
docker compose -f deploy/compose.yaml exec merchant python manage.py settle_order cancel ORD-1002
```

(or select the payment in the shop's Django admin and use the Capture / Cancel actions).

## Refunds (story S6)

Each refund reserves its amount under a lock on the payment, so refunds that together exceed the captured amount cannot both go through, even at the same moment. In the dashboard, use Refund on a captured payment (try the same refund in two tabs at once); or:

```bash
docker compose -f deploy/compose.yaml exec merchant python manage.py settle_order refund ORD-1001 --amount 500 --reason "One item returned"
```

## Lost answers and reconciliation (story S4)

Pay with 4000 0000 0000 0119 (the bank approves but the answer is lost) or 4000 0000 0000 0127 (the answer comes too late). After 10 seconds the checkout page says "We're confirming your payment" and the payment is Unresolved. The gateway worker then asks the simulator about the same operation ID, 30 seconds later and then at 1, 2, 5, 10 and 20 minutes; the first check finds the approval, the payment becomes Authorised without a second charge, and the page updates itself. Card 4000 0000 0000 0135 loses the request instead: the check finds no record, retires the ID, and the payment ends Declined (`not_processed`). An operation still without an answer after the sixth check is escalated; administrators find it with the "Escalated operations" tile on the dashboard's payments page and use "Re-check with the simulator" on the payment. Nobody can set an outcome by hand.

## Receipts and guest status

Every authorised payment gets an emailed receipt (Mailpit) with its reference and a link to https://gateway.localhost/guest/status?ref=SP-.... The link only fills in the reference: the guest also enters the email they paid with, receives a 6-digit code, and then sees that one payment, read-only, for 15 minutes. The reply is the same whether or not the details match, and three wrong codes lock the check for 15 minutes.

## Password reset and merchant sign-up

"Forgot your password?" on the dashboard sign-in page emails a reset link (Mailpit) that works once, for 30 minutes; staff confirm the new password with their authenticator code, and every session of the account ends. New merchants register at https://gateway.localhost/dashboard/register (business name, UEN, website, contact, password), verify their email from the link, and wait for an administrator, who is emailed and approves them on the Merchants page. The operator then signs in, generates the API key and webhook signing secret on the API keys page (shown once), and submits a webhook address for the administrator to approve.

## Simulator fault controls

See `contracts/SIMULATOR-CONTRACT.md` section 8. With `SIM_TEST_CONTROLS=1` (the Compose default; set it to 0 in a demo where nobody should inject faults) the simulator accepts fault rules at `https://simulator.localhost/sim/faults` with the test-control key in `deploy/secrets/simulator_test_control_key`, which the gateway never holds. For example, lose the reply to the next capture and also send two signed notifications 12 seconds later:

```bash
KEY=$(cat deploy/secrets/simulator_test_control_key)
curl -s https://simulator.localhost/sim/faults -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"match": {"operation_type": "capture"}, "action": "drop_response", "remaining": 1}'
curl -s https://simulator.localhost/sim/faults -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"match": {"operation_type": "capture"}, "action": "notify", "delay_ms": 12000, "copies": 2, "remaining": 1}'
curl -s -X DELETE https://simulator.localhost/sim/faults -H "Authorization: Bearer $KEY"   # clear all rules
```

## More

- Automated cross-service tests for S1-S6, receipts, guest status and fault controls: [`tests/integration/README.md`](../tests/integration/README.md).
- The full list of test cards: `contracts/SIMULATOR-CONTRACT.md` section 5.
- Before a live demo: [`docs/DEMO-DAY.md`](DEMO-DAY.md).
