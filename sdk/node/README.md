# securepaysg

Server-side TypeScript client for the [SecurePay](https://www.securepaysg.me) merchant API: create payments, capture, cancel, refund, check status, and verify signed webhooks.

- No dependencies. Node.js 20.19 or later (uses the built-in `fetch` and `node:crypto`).
- Types generated from the API's OpenAPI 3.1 file, so field names and statuses match the API.
- Adds an `Idempotency-Key` to every `POST` and retries timeouts, `429` and `5xx` replies with that same key, so a retry never charges twice.
- Checks the `SecurePay-Signature` on every reply and every webhook when you give it your signing secret.

> SecurePay is a university final-year project (CSIT321, group FYP-26-S4-36). It is not a licensed payment service. The live gateway at `gateway.securepaysg.me` is a demo: every payment is simulated and no real money moves. Never send real card data.

## Install

```bash
npm install securepaysg
```

## Get your keys

Register a merchant account on the [dashboard](https://gateway.securepaysg.me/dashboard/register). Once an administrator approves it, open **API keys** to get:

- a secret API key, `sp_test_...`
- a webhook signing secret, `whsec_...`

Both are shown once. Keep them in your server's environment, never in browser code.

## Take a payment

```ts
import { SecurePay } from "securepaysg";

const securepay = new SecurePay({
  apiKey: process.env.SECUREPAY_API_KEY!,
  signingSecret: process.env.SECUREPAY_SIGNING_SECRET, // checks every reply's signature
});

const payment = await securepay.payments.create({
  amount: 4590, // cents, SGD (50 to 1,000,000)
  currency: "SGD",
  order_reference: "ORD-10042",
  return_url: "https://shop.example.com/orders/ORD-10042/return",
  customer_email: "alex@example.com", // optional
  line_items: [                       // optional; must add up to amount
    { name: "Wireless mouse", quantity: 1, unit_amount: 2990 },
    { name: "Cable tie (pack)", quantity: 2, unit_amount: 800 },
  ],
});

// Send the customer to the hosted checkout (valid for 1 hour).
res.redirect(payment.checkout_url!);
```

The customer's return to `return_url` is navigation only. Fulfil the order when a verified `payment.authorised` webhook arrives, or after checking the status yourself:

```ts
const current = await securepay.payments.retrieve(payment.id);
if (current.status === "authorised") {
  await securepay.payments.capture(current.id);                 // capture all of it
  // or: await securepay.payments.capture(current.id, { amount: 4000 }) to capture less
}
```

Test card `4242 4242 4242 4242` with any future expiry and any 3-digit code is approved. Other test cards are listed in the [guides](https://www.securepaysg.me/developers#test-cards).

## All methods

| Method | Endpoint |
| --- | --- |
| `payments.create(params, options?)` | `POST /v1/payments` |
| `payments.retrieve(paymentId)` | `GET /v1/payments/{id}` |
| `payments.capture(paymentId, { amount? }?, options?)` | `POST /v1/payments/{id}/capture` |
| `payments.cancel(paymentId, options?)` | `POST /v1/payments/{id}/cancel` |
| `refunds.create(paymentId, { amount, reason? }, options?)` | `POST /v1/payments/{id}/refunds` |
| `refunds.list(paymentId)` | `GET /v1/payments/{id}/refunds` |
| `refunds.retrieve(refundId)` | `GET /v1/refunds/{id}` |
| `webhooks.constructEvent(rawBody, signatureHeader)` | verifies a webhook |

Every method returns the object from the API, plus a non-enumerable `lastResponse` with `status`, `requestId`, `idempotentReplayed`, `signatureVerified` and the `idempotencyKey` sent.

A capture or cancel can answer `202` when the simulated bank does not reply in time: `lastResponse.status` is `202`, `pending_operation` is set, and the final `payment.captured` or `payment.cancelled` webhook follows. Do not retry it with a new idempotency key.

## Webhooks

The signature covers the exact bytes sent, so give `constructEvent` the raw body.

```ts
import express from "express";
import { SecurePay, SecurePaySignatureError } from "securepaysg";

const securepay = new SecurePay({ apiKey: process.env.SECUREPAY_API_KEY!, signingSecret: process.env.SECUREPAY_SIGNING_SECRET });
const app = express();

app.post("/webhooks/securepay", express.raw({ type: "application/json" }), (req, res) => {
  let event;
  try {
    event = securepay.webhooks.constructEvent(req.body, req.get("SecurePay-Signature"));
  } catch (err) {
    if (err instanceof SecurePaySignatureError) return res.sendStatus(400);
    throw err;
  }
  res.sendStatus(200); // reply within 10 seconds, then do the work

  switch (event.type) {
    case "payment.authorised":
      // event.data.object is a Payment
      break;
    case "refund.completed":
      // event.data.object is a Refund
      break;
  }
});
```

Then, as the [webhook guide](https://www.securepaysg.me/developers#webhooks) says: skip event IDs you have already handled, and ignore an event whose `sequence` is not higher than the one you stored for that payment, because events can arrive out of order.

Without a client, use the standalone functions:

```ts
import { constructEvent, verifySignature, signPayload } from "securepaysg";

constructEvent(rawBody, header, process.env.SECUREPAY_SIGNING_SECRET!); // throws on a bad signature
verifySignature(rawBody, header, secret);                               // true or false
signPayload(body, secret);                                              // a valid header, for your own tests
```

## Errors

```ts
import { SecurePayAPIError, SecurePayConnectionError, SecurePaySignatureError } from "securepaysg";

try {
  await securepay.refunds.create(paymentId, { amount: 1500 });
} catch (err) {
  if (err instanceof SecurePayAPIError) {
    err.status;    // 422
    err.code;      // "refund_exceeds_refundable": branch on this, never on message
    err.type;      // "business_rule"
    err.param;     // the field at fault, or null
    err.requestId; // quote it when asking for help
  } else if (err instanceof SecurePayConnectionError) {
    // no answer after the retries (network or timeout)
  } else if (err instanceof SecurePaySignatureError) {
    // a reply failed the signature check: do not trust it
  }
}
```

All error codes are in the [API reference](https://www.securepaysg.me/developers/api#error-codes).

## Options

```ts
new SecurePay({
  apiKey: "sp_test_...",             // required
  signingSecret: "whsec_...",        // recommended: verifies replies, default for webhooks
  baseUrl: "https://gateway.securepaysg.me", // default
  timeoutMs: 30_000,                 // per attempt
  maxRetries: 2,                     // extra attempts after a timeout, 429 or 5xx
  fetch: customFetch,                // default: global fetch
});
```

Per call: `{ idempotencyKey, timeoutMs, signal }`. Pass your own `idempotencyKey` (for example `order-${orderId}-capture`) to make a retry safe even after your own process restarts.

## Types

```ts
import type { Payment, PaymentStatus, Refund, SecurePayEvent, CreatePaymentParams } from "securepaysg";
```

## Links

- Guides: https://www.securepaysg.me/developers
- API reference: https://www.securepaysg.me/developers/api
- OpenAPI file: https://www.securepaysg.me/openapi/merchant-api.v1.yaml

## License

MIT
