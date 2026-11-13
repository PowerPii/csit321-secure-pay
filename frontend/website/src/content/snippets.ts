import type { Snippet } from "../components/CodeBlock";

export const CREATE_PAYMENT: Snippet[] = [
  {
    label: "curl",
    code: `curl https://api.securepay.example/v1/payments \\
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
    label: "Node.js",
    code: `import { randomUUID } from "node:crypto";

const res = await fetch("https://api.securepay.example/v1/payments", {
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
    "https://api.securepay.example/v1/payments",
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
  "checkout_url": "https://pay.securepay.example/pay/cs_...",
  "checkout_expires_at": "2026-11-13T05:30:00Z",
  "sequence": 1
}`,
  },
];

export const VERIFY_WEBHOOK: Snippet[] = [
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
  return timingSafeEqual(Buffer.from(expected), Buffer.from(parts.v1));
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
curl -X POST https://api.securepay.example/v1/payments/pay_4fJ8.../capture \\
  -H "Authorization: Bearer sp_test_..." \\
  -H "Idempotency-Key: $(uuidgen)" -d '{}'

# then refund part of it
curl -X POST https://api.securepay.example/v1/payments/pay_4fJ8.../refunds \\
  -H "Authorization: Bearer sp_test_..." \\
  -H "Idempotency-Key: $(uuidgen)" -d '{ "amount": 690, "reason": "item returned" }'`,
  },
];
