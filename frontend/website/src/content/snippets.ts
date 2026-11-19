import type { Snippet } from "../components/CodeBlock";
import { API_BASE, GATEWAY_URL, SDK_PACKAGE } from "./site";

export const CREATE_PAYMENT: Snippet[] = [
  {
    label: "curl",
    code: `curl ${API_BASE}/payments \\
  -H "Authorization: Bearer sp_test_..." \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "Content-Type: application/json" \\
  -d '{
    "amount": 4290,
    "currency": "SGD",
    "order_reference": "order_1042",
    "return_url": "https://shop.example/orders/1042",
    "line_items": [
      { "name": "Single-origin beans", "quantity": 2, "unit_amount": 1800 },
      { "name": "Pour-over filter", "quantity": 1, "unit_amount": 690 }
    ]
  }'`,
  },
  {
    label: "Node.js SDK",
    code: `import { SecurePay } from "${SDK_PACKAGE}";

const securepay = new SecurePay({
  apiKey: process.env.SECUREPAY_API_KEY,
  signingSecret: process.env.SECUREPAY_SIGNING_SECRET, // also checks every reply's signature
});

const payment = await securepay.payments.create({
  amount: 4290, // cents, SGD
  currency: "SGD",
  order_reference: "order_1042",
  return_url: "https://shop.example/orders/1042",
});
// The SDK adds the Idempotency-Key and retries safely with it.
// Send the customer to payment.checkout_url`,
  },
  {
    label: "Node.js",
    code: `import { randomUUID } from "node:crypto";

const res = await fetch("${API_BASE}/payments", {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.SECUREPAY_API_KEY}\`,
    "Idempotency-Key": randomUUID(), // reuse only when retrying this order
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    amount: 4290, // cents, SGD
    currency: "SGD",
    order_reference: "order_1042",
    return_url: "https://shop.example/orders/1042",
  }),
});

const payment = await res.json();
// Send the customer to payment.checkout_url`,
  },
  {
    label: "Python",
    code: `import os, uuid, requests

res = requests.post(
    "${API_BASE}/payments",
    headers={
        "Authorization": f"Bearer {os.environ['SECUREPAY_API_KEY']}",
        "Idempotency-Key": str(uuid.uuid4()),  # reuse only when retrying
    },
    json={
        "amount": 4290,  # cents, SGD
        "currency": "SGD",
        "order_reference": "order_1042",
        "return_url": "https://shop.example/orders/1042",
    },
    timeout=10,
)
payment = res.json()
# Redirect the customer to payment["checkout_url"]`,
  },
];

export const PAYMENT_RESPONSE: Snippet[] = [
  {
    label: "201 Created",
    code: `{
  "id": "pay_4fJ8kQ2mZx7RtL9vNc3bH1sD",
  "object": "payment",
  "reference": "SP-7KQ4-M2XD",
  "status": "created",
  "amount": 4290,
  "currency": "SGD",
  "order_reference": "order_1042",
  "checkout_url": "${GATEWAY_URL}/pay/cs_...",
  "checkout_expires_at": "2026-11-13T05:30:00Z",
  "sequence": 1
}`,
  },
];

export const VERIFY_WEBHOOK: Snippet[] = [
  {
    label: "Node.js SDK",
    code: `import express from "express";
import { SecurePay } from "${SDK_PACKAGE}";

const securepay = new SecurePay({ apiKey: process.env.SECUREPAY_API_KEY, signingSecret: process.env.SECUREPAY_SIGNING_SECRET });
const app = express();

// The raw body: the signature covers the exact bytes sent.
app.post("/webhooks/securepay", express.raw({ type: "application/json" }), (req, res) => {
  let event;
  try {
    event = securepay.webhooks.constructEvent(req.body, req.get("SecurePay-Signature"));
  } catch {
    return res.sendStatus(400); // bad or stale signature
  }
  res.sendStatus(200); // reply within 10 s, then do the work
  if (event.type === "payment.authorised") {
    // event.data.object is the Payment. Skip event IDs you have seen.
  }
});`,
  },
  {
    label: "Node.js",
    code: `import { createHmac, timingSafeEqual } from "node:crypto";

// header: SecurePay-Signature: t=1763011800,v1=5f2b...
export function verify(rawBody, header, secret) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=")));
  const age = Math.abs(Date.now() / 1000 - Number(parts.t));
  if (age > 300) return false; // replay window: 300 seconds

  const expected = createHmac("sha256", secret)
    .update(\`\${parts.t}.\${rawBody}\`)
    .digest("hex");
  const given = Buffer.from(parts.v1 ?? "");
  return given.length === expected.length && timingSafeEqual(Buffer.from(expected), given);
}`,
  },
  {
    label: "Python",
    code: `import hmac, hashlib, time

# header: SecurePay-Signature: t=1763011800,v1=5f2b...
def verify(raw_body: bytes, header: str, secret: str) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    if abs(time.time() - int(parts["t"])) > 300:  # replay window
        return False
    signed = parts["t"].encode() + b"." + raw_body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])`,
  },
];

export const EVENT_EXAMPLE: Snippet[] = [
  {
    label: "payment.authorised",
    code: `{
  "id": "evt_9Qm2Lk7TzW4cXr1Bn8Vh3Jd6",
  "object": "event",
  "type": "payment.authorised",
  "created_at": "2026-11-13T04:31:12Z",
  "payment_id": "pay_4fJ8kQ2mZx7RtL9vNc3bH1sD",
  "sequence": 2,
  "data": {
    "object": {
      "id": "pay_4fJ8kQ2mZx7RtL9vNc3bH1sD",
      "status": "authorised",
      "amount": 4290,
      "card": { "token": "tok_...", "brand": "visa", "last4": "4242" },
      "screening": { "decision": "allow" }
    }
  }
}`,
  },
];

export const CAPTURE: Snippet[] = [
  {
    label: "Capture",
    code: `# capture the full amount
curl -X POST ${API_BASE}/payments/pay_4fJ8.../capture \\
  -H "Authorization: Bearer sp_test_..." \\
  -H "Idempotency-Key: $(uuidgen)" -d '{}'

# then refund part of it
curl -X POST ${API_BASE}/payments/pay_4fJ8.../refunds \\
  -H "Authorization: Bearer sp_test_..." \\
  -H "Idempotency-Key: $(uuidgen)" -d '{ "amount": 690, "reason": "item returned" }'`,
  },
];

export const SDK_INSTALL: Snippet[] = [
  { label: "npm", code: `npm install ${SDK_PACKAGE}` },
  { label: "pnpm", code: `pnpm add ${SDK_PACKAGE}` },
  { label: "yarn", code: `yarn add ${SDK_PACKAGE}` },
];

export const SDK_USAGE: Snippet[] = [
  {
    label: "Payments",
    code: `import { SecurePay, SecurePayAPIError } from "${SDK_PACKAGE}";

const securepay = new SecurePay({
  apiKey: process.env.SECUREPAY_API_KEY,             // sp_test_...
  signingSecret: process.env.SECUREPAY_SIGNING_SECRET, // whsec_...
});

// Before you ship: a signed status check, never the browser redirect.
const payment = await securepay.payments.retrieve("pay_4fJ8kQ2mZx7RtL9vNc3bH1sD");

if (payment.status === "authorised") {
  await securepay.payments.capture(payment.id);                  // all of it
  // or: await securepay.payments.capture(payment.id, { amount: 3000 });
}

try {
  await securepay.refunds.create(payment.id, { amount: 1500, reason: "One item returned" });
} catch (err) {
  if (err instanceof SecurePayAPIError && err.code === "refund_exceeds_refundable") {
    // more than is left to refund
  } else throw err;
}`,
  },
  {
    label: "Types",
    code: `import type { Payment, Refund, SecurePayEvent, PaymentStatus } from "${SDK_PACKAGE}";

// Generated from the OpenAPI file, so field names and statuses
// always match the API.
function shouldShip(p: Payment): boolean {
  return p.status === "captured";
}`,
  },
];
