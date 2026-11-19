# What each surface calls a payment (completion audit, 19 November 2026)

One journey, one reference, one set of words: **developer quickstart, hosted checkout,
verification, receipt, merchant dashboard, refund**. This page is the map. When a surface's
wording changes, change it here first.

## The rule

- The API's `status` values never change. They are the contract with merchants
  (`contracts/openapi/merchant-api.v1.yaml`) and the SDK's types. Only the words shown to
  people change, and each audience has one small mapping:
  - customers: `gateway/apps/payments/labels.py` (guest status page and customer account,
    served as `status_label`); the hosted checkout and the demo shop use the same words;
  - merchants and staff: `STATUS_LABELS` in `frontend/dashboard/src/format.ts`.
- **One public reference.** The `SP-XXXX-XXXX` payment reference is on the checkout result,
  the receipt email and PDF, the guest status page, the customer account, the demo shop's order
  page and the dashboard. Typing it into the dashboard's Payments search finds the payment,
  in any case and with or without the dashes or spaces (`sp 7kq4 m2xd` works). Order numbers
  (`ORD-...`, the merchant's) and refund references (`RF-XXXX-XXXX`, on the refund receipt)
  stay separate; a refund reference typed into the same search finds its payment.
- **A lost bank reply is never a failure.** While a payment is `unresolved`, no surface says
  "try again" or offers a new payment. Every surface says not to pay again and points to where
  the result will appear.

## Payment states

| API `status` | Customer (checkout result, guest status, account) | Demo shop order page | Dashboard (merchant, staff) |
|---|---|---|---|
| `created` | In progress (checkout still open) | Awaiting payment, "Continue to payment" | Created |
| `screening`, `processing` | "Checking your payment…" while the page waits; In progress | Waiting for payment confirmation | Screening / Processing |
| `verification_required` | Enter the code (C5); In progress | Waiting for payment confirmation, "Continue to payment" | Awaiting code |
| `authorised` | Payment successful, badge **Paid** | Payment confirmed | Authorised |
| `captured` | Paid | Paid | Captured (Refunded / Partially refunded once refunds complete) |
| `unresolved` | **"We're checking your payment"**, "Please don't pay again", status link to `/guest/status?ref=SP-...`; label *Being checked - do not pay again* | Waiting for payment confirmation, "Please don't pay again" | Unresolved, with each processor operation's check count, **last** and next check time |
| `declined` | Payment declined, "Try another card"; Not charged | Payment not completed, "Try another card" | Declined |
| `blocked` | We couldn't complete this payment (or "We couldn't confirm it was you" after a failed code); Not charged. No screening detail. | Payment not completed | Blocked (fraud detail for analysts only) |
| `cancelled` | This payment was cancelled; Not charged | Order cancelled | Cancelled |
| `expired` | This checkout has ended; Not charged | Payment not completed | Expired |

Refunds: the customer account shows Refunded or Partly refunded; the refund receipt email
carries the `RF-` reference and the payment's `SP-` reference; the dashboard lists refunds
by `RF-` reference on the payment.

## Where a timeout could invite a second payment, and what each now says

| Moment | What the person sees | Why it is safe |
|---|---|---|
| The pay request's reply is lost in the browser | "We lost the connection while sending your payment, so it may still go through. Reload this page to see the result... Paying again on this page won't charge you twice." | Submitting a checkout is idempotent: a second submit returns the same payment (`gateway/apps/checkout/service.py`, `submit`). |
| The simulator does not answer (`unresolved`) | "We're checking your payment... Please don't pay again", with the status link | Reconciliation settles it with the same operation ID. |
| The shop cannot reach SecurePay to create the payment | "Nothing was charged. Use 'Continue to payment' below...; it picks up the same payment, so you won't pay twice." | The shop reuses the attempt's Idempotency-Key (`merchant/apps/shop/payments.py`). |
| Screening is unavailable (`blocked`, `screening_unavailable`) | "We couldn't check this payment right now. No money was taken. Please try again in a few minutes" | The first payment is final (blocked before any financial effect), so a new one is not a duplicate. |

## Checked by

- `gateway/apps/payments/test_labels.py`: every status has a customer label; the enum is unchanged.
- `gateway/apps/internal/tests.py::test_the_receipt_reference_finds_the_payment_however_it_is_typed`
- `frontend/checkout/src/App.test.tsx`: the pending view's wording and status link, and the lost pay reply.
- `merchant/apps/shop/tests.py::test_gateway_down_then_retry_reuses_the_idempotency_key`
