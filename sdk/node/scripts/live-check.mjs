// End-to-end check of the built SDK (dist/) against a real gateway. Not published to npm.
//
//   npm run build
//   SECUREPAY_API_KEY=sp_test_... SECUREPAY_SIGNING_SECRET=whsec_... \
//   SECUREPAY_BASE_URL=https://gateway.securepaysg.me \
//   MAILPIT_URL=https://<user>:<password>@mail.securepaysg.me node scripts/live-check.mjs
//
// It creates two simulated payments, pays them with a fresh test card from the simulator's
// demo range 4242 4200 xxxx xxxx (no screening history) through the hosted checkout's own
// API (what the payment page does), then captures, refunds and cancels.
// When screening asks for a verification code (the second payment on one card often does),
// it reads the code from the Mailpit test inbox at MAILPIT_URL and enters it. Without
// MAILPIT_URL it stops at once with a clear message instead of waiting for a timeout.
// Only use it with a test merchant: the payments show up on that merchant's dashboard.
import { randomUUID } from "node:crypto";
import { SecurePay, SecurePayAPIError } from "../dist/index.js";
import { payWithTestCard, waitForStatus } from "./checkout-driver.mjs";

const { SECUREPAY_API_KEY: apiKey, SECUREPAY_SIGNING_SECRET: signingSecret } = process.env;
const baseUrl = process.env.SECUREPAY_BASE_URL ?? "https://gateway.securepaysg.me";
if (!apiKey || !signingSecret) {
  console.error("Set SECUREPAY_API_KEY and SECUREPAY_SIGNING_SECRET (a test merchant's).");
  process.exit(2);
}
const sp = new SecurePay({ apiKey, signingSecret, baseUrl, allowInsecureHttp: process.env.SECUREPAY_ALLOW_HTTP === "1" });
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

const pay = (payment) => payWithTestCard(baseUrl, payment, { log: (m) => console.log(`# ${m}`) });
const waitFor = (id, statuses) => waitForStatus(sp, id, statuses, { timeoutMs: 30_000 });

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
await expectError(new SecurePay({ apiKey: "sp_test_" + "x".repeat(40), signingSecret, baseUrl, allowInsecureHttp: process.env.SECUREPAY_ALLOW_HTTP === "1" }).payments.retrieve(created.id), "api_key_invalid", "unknown API key");

await pay(created);
const authorised = await waitFor(created.id, ["authorised", "blocked", "declined"]);
expect(authorised.status === "authorised", `paid with the test card: ${authorised.status}`);
const captured = await sp.payments.capture(created.id, { amount: 4000 });
expect(captured.status === "captured" && captured.captured_amount === 4000, "partial capture of 4000 cents");
const refund = await sp.refunds.create(created.id, { amount: 1500, reason: "One item returned" }, { idempotencyKey: `${key}-refund-1` });
expect(["completed", "unresolved"].includes(refund.status), `refund ${refund.reference}: ${refund.status}`);
await expectError(sp.refunds.create(created.id, { amount: 3000 }), "refund_exceeds_refundable", "refund over what is left is refused");
const list = await sp.refunds.list(created.id);
expect(list.data.length === 1 && list.refundable_amount === 2500, `list refunds: ${list.data.length}, ${list.refundable_amount} cents left`);
const again = await sp.refunds.retrieve(refund.id);
expect(again.id === refund.id, "retrieve the refund");

// With an inbox, the second payment uses the step-up fixture email review@example.com, so
// every run also proves the verification path (code read from Mailpit, then entered).
const stepUp = Boolean(process.env.MAILPIT_URL);
const second = await sp.payments.create(
  { ...params, order_reference: `${order}-B`, ...(stepUp ? { customer_email: "review@example.com" } : {}) },
  { idempotencyKey: `${key}-B` },
);
const secondView = await pay(second);
if (stepUp) expect(secondView.steppedUp && secondView.status !== "verification_required", `verification code read from the inbox and accepted: ${secondView.status}`);
await waitFor(second.id, ["authorised"]);
const cancelled = await sp.payments.cancel(second.id);
expect(cancelled.status === "cancelled", "cancel an authorised payment");
console.log(`\nAll ${step} checks passed against ${baseUrl}.`);
