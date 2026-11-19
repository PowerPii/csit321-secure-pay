// Lost replies, merchant restarts and option checks (Codex completion audit, 19 Nov 2026).
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { test } from "node:test";
import {
  SecurePay,
  SecurePayAPIError,
  SecurePayConnectionError,
  SecurePaySignatureError,
  constructEvent,
  signPayload,
  verifySignature,
  type CreatePaymentParams,
} from "../src/index.js";
import { example, fakeFetch, SECRET } from "./helpers.js";

// A merchant-chosen key, built at runtime so secret scanners do not read it as a credential.
const ORDER_KEY = ["order", "ORD-10042", "pay"].join("-");

const PARAMS: CreatePaymentParams = {
  amount: 4590,
  currency: "SGD",
  order_reference: "ORD-10042",
  return_url: "https://shop.example.com/orders/ORD-10042/return",
};

/**
 * A tiny gateway with the contract's idempotency rules (section 5): one operation per
 * merchant key, the first reply replayed with Idempotent-Replayed. `loseReplies` makes the
 * network drop the answer AFTER the gateway committed, like a cut connection.
 */
function fakeGateway() {
  const stored = new Map<string, { body: string; status: number; fingerprint: string }>();
  const created = { payments: 0, refunds: 0 };
  let loseReplies = 0;
  const impl = (async (input: string | URL | Request, init: RequestInit = {}) => {
    const url = new URL(String(input));
    const headers = init.headers as Record<string, string>;
    const key = headers["Idempotency-Key"]!;
    const fingerprint = `${init.method} ${url.pathname} ${String(init.body)}`;
    let reply = stored.get(key);
    let replayed = true;
    if (!reply) {
      replayed = false;
      const refund = url.pathname.endsWith("/refunds");
      const n = refund ? ++created.refunds : ++created.payments;
      const body = JSON.stringify(
        refund
          ? { id: `rfd_${String(n).padStart(24, "0")}`, object: "refund", status: "completed", amount: JSON.parse(String(init.body)).amount }
          : { id: `pay_${String(n).padStart(24, "0")}`, object: "payment", status: "created" },
      );
      reply = { body, status: 201, fingerprint };
      stored.set(key, reply);
    } else if (reply.fingerprint !== fingerprint) {
      const body = JSON.stringify({ error: { type: "conflict", code: "idempotency_key_reused", message: "Different request.", param: "Idempotency-Key" } });
      return new Response(body, { status: 409, headers: { "SecurePay-Signature": signPayload(body, SECRET) } });
    }
    if (loseReplies > 0) {
      loseReplies--;
      throw new TypeError("fetch failed: socket hang up");
    }
    const h = new Headers({ "SecurePay-Signature": signPayload(reply.body, SECRET) });
    if (replayed) h.set("Idempotent-Replayed", "true");
    return new Response(reply.body, { status: reply.status, headers: h });
  }) as typeof fetch;
  return {
    impl,
    created,
    loseNext(n: number) {
      loseReplies = n;
    },
  };
}

/** A fresh client, as after a merchant process restart: nothing carried over in memory. */
const freshClient = (fetchImpl: typeof fetch) =>
  new SecurePay({ apiKey: "sp_test_abc", signingSecret: SECRET, baseUrl: "https://gw.test", fetch: fetchImpl, maxRetries: 1 });

test("a lost reply keeps the generated key on the error, and every attempt used it", async () => {
  const gw = fakeGateway();
  gw.loseNext(2);
  const err = await freshClient(gw.impl).payments.create(PARAMS).then(
    () => assert.fail("expected an error"),
    (e: unknown) => e,
  );
  assert.ok(err instanceof SecurePayConnectionError);
  assert.equal(err.outcomeUnknown, true);
  assert.equal(err.attempts, 2);
  assert.match(err.idempotencyKey!, /^[0-9a-f-]{36}$/);
  assert.match(err.message, new RegExp(`retry with Idempotency-Key ${err.idempotencyKey}`));
  assert.equal(gw.created.payments, 1, "the gateway committed exactly once");
  // Retrying with the key from the error recovers the same payment.
  const again = await freshClient(gw.impl).payments.create(PARAMS, { idempotencyKey: err.idempotencyKey! });
  assert.equal(again.id, "pay_000000000000000000000001");
  assert.equal(again.lastResponse.idempotentReplayed, true);
  assert.equal(gw.created.payments, 1);
});

test("order key saved before the call: lost reply + merchant restart recovers the same payment", async () => {
  const gw = fakeGateway();
  const db = new Map<string, { key: string; paymentId: string | null }>(); // the merchant's table
  db.set("ORD-10042", { key: randomUUID(), paymentId: null });

  gw.loseNext(2); // first process: every attempt's reply is lost, then the process dies
  await assert.rejects(() => freshClient(gw.impl).payments.create(PARAMS, { idempotencyKey: db.get("ORD-10042")!.key }), SecurePayConnectionError);

  // Second process: only the database survived.
  const order = db.get("ORD-10042")!;
  const payment = await freshClient(gw.impl).payments.create(PARAMS, { idempotencyKey: order.key });
  order.paymentId = payment.id;
  assert.equal(payment.lastResponse.idempotentReplayed, true);
  assert.equal(gw.created.payments, 1);
});

test("without a saved key, a restart creates a second payment (why the quickstart saves one)", async () => {
  const gw = fakeGateway();
  gw.loseNext(2);
  await assert.rejects(() => freshClient(gw.impl).payments.create(PARAMS), SecurePayConnectionError);
  await freshClient(gw.impl).payments.create(PARAMS);
  assert.equal(gw.created.payments, 2);
});

test("each partial refund has its own key; a lost refund reply is recovered, not repeated", async () => {
  const gw = fakeGateway();
  const id = "pay_EXAMPLE00000000000000001";
  const first = { key: randomUUID(), amount: 1500 };
  const second = { key: randomUUID(), amount: 1000 };
  gw.loseNext(2);
  const err = await freshClient(gw.impl).refunds.create(id, { amount: first.amount }, { idempotencyKey: first.key }).catch((e: unknown) => e);
  assert.ok(err instanceof SecurePayConnectionError && err.idempotencyKey === first.key);
  const recovered = await freshClient(gw.impl).refunds.create(id, { amount: first.amount }, { idempotencyKey: first.key });
  assert.equal(recovered.lastResponse.idempotentReplayed, true);
  const other = await freshClient(gw.impl).refunds.create(id, { amount: second.amount }, { idempotencyKey: second.key });
  assert.equal(other.lastResponse.idempotentReplayed, false);
  assert.equal(gw.created.refunds, 2, "two distinct refunds, each once");
  // Reusing one refund's key for a different amount is refused, not silently replayed.
  await assert.rejects(
    () => freshClient(gw.impl).refunds.create(id, { amount: 999 }, { idempotencyKey: first.key }),
    (e: unknown) => e instanceof SecurePayAPIError && e.code === "idempotency_key_reused" && e.idempotencyKey === first.key && !e.outcomeUnknown,
  );
});

test("a 5xx after the retries is outcomeUnknown and carries the key; a 4xx is not", async () => {
  const server = JSON.stringify({ error: { type: "server", code: "internal_error", message: "Oops.", param: null } });
  const f = fakeFetch([{ status: 503, body: "", sign: false }, { status: 500, body: server }]);
  const sp = new SecurePay({ apiKey: "sp_test_abc", signingSecret: SECRET, baseUrl: "https://gw.test", fetch: f.impl, maxRetries: 1 });
  const err = await sp.payments.create(PARAMS, { idempotencyKey: ORDER_KEY }).catch((e: unknown) => e);
  assert.ok(err instanceof SecurePayAPIError);
  assert.equal(err.status, 500);
  assert.equal(err.outcomeUnknown, true);
  assert.equal(err.idempotencyKey, ORDER_KEY);
  assert.deepEqual(f.calls.map((c) => c.headers["idempotency-key"]), [ORDER_KEY, ORDER_KEY]);

  const g = fakeFetch([{ status: 409, body: example("api/error-idempotency-key-reused.409.json") }]);
  const sp2 = new SecurePay({ apiKey: "sp_test_abc", signingSecret: SECRET, baseUrl: "https://gw.test", fetch: g.impl });
  const e2 = await sp2.payments.create(PARAMS).catch((e: unknown) => e);
  assert.ok(e2 instanceof SecurePayAPIError && e2.outcomeUnknown === false && e2.idempotencyKey === g.calls[0]!.headers["idempotency-key"]);
});

test("409 idempotency_request_in_progress after the last retry is outcomeUnknown", async () => {
  const busy = JSON.stringify({ error: { type: "conflict", code: "idempotency_request_in_progress", message: "Still running.", param: "Idempotency-Key" } });
  const f = fakeFetch([{ status: 409, body: busy, headers: { "Retry-After": "0" } }]);
  const sp = new SecurePay({ apiKey: "sp_test_abc", signingSecret: SECRET, baseUrl: "https://gw.test", fetch: f.impl, maxRetries: 0 });
  const err = await sp.payments.create(PARAMS, { idempotencyKey: ORDER_KEY }).catch((e: unknown) => e);
  assert.ok(err instanceof SecurePayAPIError && err.outcomeUnknown && err.idempotencyKey === ORDER_KEY);
});

test("a POST reply that fails the signature check keeps the key and is outcomeUnknown", async () => {
  const body = example("api/create-payment.201.json");
  const f = fakeFetch([{ status: 201, body, sign: false, headers: { "SecurePay-Signature": `t=${Math.floor(Date.now() / 1000)},v1=${"0".repeat(64)}` } }]);
  const sp = new SecurePay({ apiKey: "sp_test_abc", signingSecret: SECRET, baseUrl: "https://gw.test", fetch: f.impl });
  const err = await sp.payments.create(PARAMS, { idempotencyKey: ORDER_KEY }).catch((e: unknown) => e);
  assert.ok(err instanceof SecurePaySignatureError && err.outcomeUnknown && err.idempotencyKey === ORDER_KEY);
});

test("a GET connection error has no key", async () => {
  const f = fakeFetch([new TypeError("fetch failed")]);
  const sp = new SecurePay({ apiKey: "sp_test_abc", baseUrl: "https://gw.test", fetch: f.impl, maxRetries: 0 });
  const err = await sp.payments.retrieve("pay_EXAMPLE00000000000000001").catch((e: unknown) => e);
  assert.ok(err instanceof SecurePayConnectionError && err.idempotencyKey === null && err.outcomeUnknown);
});

test("refuses an idempotency key the gateway would reject, before sending", async () => {
  const f = fakeFetch([]);
  const sp = new SecurePay({ apiKey: "sp_test_abc", baseUrl: "https://gw.test", fetch: f.impl });
  for (const bad of ["short", "has space in it", "x".repeat(256), "ünïcode-key", ""]) {
    await assert.rejects(() => sp.payments.create(PARAMS, { idempotencyKey: bad }), TypeError, bad);
  }
  assert.equal(f.calls.length, 0);
});

test("baseUrl must be HTTPS; plain HTTP only on this machine and only when allowed", () => {
  const f = fakeFetch([]).impl;
  const make = (baseUrl: string, allowInsecureHttp?: boolean) => new SecurePay({ apiKey: "sp_test_abc", baseUrl, fetch: f, allowInsecureHttp });
  assert.ok(make("https://gateway.securepaysg.me"));
  assert.ok(make("https://gateway.localhost/"));
  assert.throws(() => make("http://gateway.securepaysg.me"), /must use https/);
  assert.throws(() => make("http://gateway.securepaysg.me", true), /must use https/);
  assert.throws(() => make("http://localhost:8000"), /allowInsecureHttp/);
  assert.ok(make("http://localhost:8000", true));
  assert.ok(make("http://127.0.0.1:8000", true));
  assert.ok(make("http://gateway.localhost", true));
  assert.ok(make("http://[::1]:8000", true));
  assert.throws(() => make("http://localhost.evil.com", true), /must use https/);
  assert.throws(() => make("ftp://gateway.securepaysg.me"), /https/);
  assert.throws(() => make("https://user:pass@gateway.securepaysg.me"), /user name or password/);
  assert.throws(() => make("https://gateway.securepaysg.me/?x=1"), /query string/);
  assert.throws(() => make("not a url"), /not a valid URL/);
});

test("timeoutMs and maxRetries must be finite and within limits", async () => {
  const f = fakeFetch([]).impl;
  const make = (o: object) => new SecurePay({ apiKey: "sp_test_abc", fetch: f, ...o });
  for (const timeoutMs of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, 600_001]) assert.throws(() => make({ timeoutMs }), RangeError);
  for (const maxRetries of [-1, 1.5, Number.NaN, 11]) assert.throws(() => make({ maxRetries }), RangeError);
  assert.ok(make({ timeoutMs: 1, maxRetries: 0 }));
  assert.ok(make({ timeoutMs: 600_000, maxRetries: 10 }));
  await assert.rejects(() => make({}).payments.retrieve("pay_EXAMPLE00000000000000001", { timeoutMs: Number.NaN }), RangeError);
});

test("signature tolerance must be 1 to 3,600 seconds; 0 or NaN no longer disables the freshness check", () => {
  const body = example("events/payment.authorised.json");
  const old = signPayload(body, SECRET, 1_000_000);
  for (const toleranceSeconds of [0, -5, Number.NaN, Number.POSITIVE_INFINITY, 3601]) {
    assert.throws(() => verifySignature(body, old, SECRET, { toleranceSeconds }), RangeError);
    assert.throws(() => constructEvent(body, old, SECRET, { toleranceSeconds }), RangeError);
  }
  assert.equal(verifySignature(body, old, SECRET, { toleranceSeconds: 3600 }), false);
  assert.equal(verifySignature(body, old, SECRET, { toleranceSeconds: 60, now: 1_000_030 }), true);
  assert.throws(() => verifySignature(body, old, SECRET, { now: Number.NaN }), RangeError);
});
