// End-to-end check of the built SDK (dist/) against a real gateway. Not published to npm.
//
//   npm run build
//   SECUREPAY_API_KEY=sp_test_... SECUREPAY_SIGNING_SECRET=whsec_... \
//   SECUREPAY_BASE_URL=https://gateway.securepaysg.me node scripts/live-check.mjs
//
// It creates two simulated payments, pays them with test card 4242 4242 4242 4242 through the
// hosted checkout's own API (what the payment page does), then captures, refunds and cancels.
// Only use it with a test merchant: the payments show up on that merchant's dashboard.
import { randomUUID } from "node:crypto";
import { SecurePay, SecurePayAPIError } from "../dist/index.js";

const { SECUREPAY_API_KEY: apiKey, SECUREPAY_SIGNING_SECRET: signingSecret } = process.env;
const baseUrl = process.env.SECUREPAY_BASE_URL ?? "https://gateway.securepaysg.me";
if (!apiKey || !signingSecret) {
  console.error("Set SECUREPAY_API_KEY and SECUREPAY_SIGNING_SECRET (a test merchant's).");
  process.exit(2);
}
const sp = new SecurePay({ apiKey, signingSecret, baseUrl });
let step = 0;
const ok = (what) => console.log(`ok ${++step} - ${what}`);
const expect = (cond, what) => {
  if (!cond) throw new Error(`failed: ${what}`);
  ok(what);
};
const expectError = async (promise, code, what) => {
  try {
    await promise;
  } catch (e) {
    if (e instanceof SecurePayAPIError && e.code === code) return ok(`${what} (${e.status} ${code})`);
    throw e;
  }
  throw new Error(`failed: ${what}: no error`);
};

async function payWithTestCard(payment) {
  const session = payment.checkout_url.match(/cs_[0-9A-Za-z]{24}/)[0];
  const post = (path, body) =>
    fetch(`${baseUrl}/checkout/${session}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const card = await post("/card", { number: "4242424242424242", expiry_month: 12, expiry_year: 2030, cvc: "123", privacy_consent: true });
  if (card.status !== 200) throw new Error(`card step: ${card.status} ${await card.text()}`);
  const submit = await post("/submit", {});
  if (submit.status !== 200) throw new Error(`submit step: ${submit.status} ${await submit.text()}`);
}

async function waitFor(id, statuses) {
  for (let i = 0; i < 30; i++) {
    const p = await sp.payments.retrieve(id);
    if (statuses.includes(p.status)) return p;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`payment ${id} did not reach ${statuses}`);
}

const order = `SDK-${randomUUID().slice(0, 8)}`;
const params = {
  amount: 4590,
  currency: "SGD",
  order_reference: order,
  return_url: "https://shop.example.com/orders/return",
  description: "SDK live check",
  // example.com never receives mail; the live server does not relay to it.
  customer_email: `sdk-check-${randomUUID().slice(0, 8)}@example.com`,
  line_items: [
    { name: "Wireless mouse", quantity: 1, unit_amount: 2990 },
    { name: "Cable tie (pack)", quantity: 2, unit_amount: 800 },
  ],
};
const key = `sdk-live-${randomUUID()}`;
const created = await sp.payments.create(params, { idempotencyKey: key });
expect(created.status === "created" && created.checkout_url, `create payment ${created.id} (${created.reference})`);
expect(created.lastResponse.signatureVerified, "reply signature verified");
const replay = await sp.payments.create(params, { idempotencyKey: key });
expect(replay.id === created.id && replay.lastResponse.idempotentReplayed, "same idempotency key replays the stored reply");
await expectError(sp.payments.create({ ...params, amount: 100 }, { idempotencyKey: key }), "idempotency_key_reused", "same key, different body is refused");
await expectError(sp.payments.capture(created.id), "payment_not_authorised", "capture before payment is refused");
await expectError(sp.payments.create({ ...params, amount: 10 }), "amount_too_small", "amount below S$0.50 is refused");
await expectError(new SecurePay({ apiKey: "sp_test_" + "x".repeat(40), signingSecret, baseUrl }).payments.retrieve(created.id), "api_key_invalid", "unknown API key");

await payWithTestCard(created);
const authorised = await waitFor(created.id, ["authorised", "blocked", "declined"]);
expect(authorised.status === "authorised", `paid with the test card: ${authorised.status}`);
const captured = await sp.payments.capture(created.id, { amount: 4000 });
expect(captured.status === "captured" && captured.captured_amount === 4000, "partial capture of 4000 cents");
const refund = await sp.refunds.create(created.id, { amount: 1500, reason: "One item returned" });
expect(["completed", "unresolved"].includes(refund.status), `refund ${refund.reference}: ${refund.status}`);
await expectError(sp.refunds.create(created.id, { amount: 3000 }), "refund_exceeds_refundable", "refund over what is left is refused");
const list = await sp.refunds.list(created.id);
expect(list.data.length === 1 && list.refundable_amount === 2500, `list refunds: ${list.data.length}, ${list.refundable_amount} cents left`);
const again = await sp.refunds.retrieve(refund.id);
expect(again.id === refund.id, "retrieve the refund");

const second = await sp.payments.create({ ...params, order_reference: `${order}-B` });
await payWithTestCard(second);
await waitFor(second.id, ["authorised"]);
const cancelled = await sp.payments.cancel(second.id);
expect(cancelled.status === "cancelled", "cancel an authorised payment");
console.log(`\nAll ${step} checks passed against ${baseUrl}.`);
