import assert from "node:assert/strict";
import { test } from "node:test";
import { constructEvent, SecurePay, SecurePaySignatureError, signPayload, verifySignature } from "../src/index.js";
import { example, SECRET } from "./helpers.js";

// Made by the gateway's own Python code (gateway/apps/events/signing.py):
//   sign(b'{"id":"evt_test","object":"event"}', "whsec_test_vector_secret", 1763520000)
const VECTOR_BODY = '{"id":"evt_test","object":"event"}';
const VECTOR_HEADER = "t=1763520000,v1=5d453afe8b04c92980be8d4605c30ac7372ad374c87d61cdbddfe604a8521530";
const VECTOR_NOW = 1763520000;

test("matches the gateway's own signatures (cross-language vector)", () => {
  assert.equal(signPayload(VECTOR_BODY, SECRET, VECTOR_NOW), VECTOR_HEADER);
  assert.equal(verifySignature(VECTOR_BODY, VECTOR_HEADER, SECRET, { now: VECTOR_NOW }), true);
  assert.equal(verifySignature(Buffer.from(VECTOR_BODY), VECTOR_HEADER, SECRET, { now: VECTOR_NOW + 299 }), true);
  assert.equal(verifySignature(new TextEncoder().encode(VECTOR_BODY), VECTOR_HEADER, SECRET, { now: VECTOR_NOW }), true);
});

test("rejects a changed body, a wrong secret, a stale timestamp and bad headers", () => {
  const ok = { now: VECTOR_NOW };
  assert.equal(verifySignature(VECTOR_BODY + " ", VECTOR_HEADER, SECRET, ok), false);
  assert.equal(verifySignature(VECTOR_BODY, VECTOR_HEADER, "whsec_other", ok), false);
  assert.equal(verifySignature(VECTOR_BODY, VECTOR_HEADER, SECRET, { now: VECTOR_NOW + 301 }), false);
  assert.equal(verifySignature(VECTOR_BODY, VECTOR_HEADER, SECRET, { now: VECTOR_NOW - 301 }), false);
  for (const header of [undefined, null, "", "t=abc,v1=00", "v1=" + "a".repeat(64), "t=1763520000", "nonsense"]) {
    assert.equal(verifySignature(VECTOR_BODY, header, SECRET, ok), false, String(header));
  }
});

test("accepts any matching v1 when several are sent", () => {
  const header = `t=${VECTOR_NOW},v1=${"0".repeat(64)},${VECTOR_HEADER.split(",")[1]}`;
  assert.equal(verifySignature(VECTOR_BODY, header, SECRET, { now: VECTOR_NOW }), true);
});

test("constructEvent returns the contract's example event, typed", () => {
  const body = example("events/payment.authorised.json");
  const event = constructEvent(body, signPayload(body, SECRET), SECRET);
  assert.equal(event.type, "payment.authorised");
  if (event.type.startsWith("payment.") && event.data.object.object === "payment") {
    assert.equal(event.data.object.status, "authorised");
  } else {
    assert.fail("expected a payment event");
  }
  const refund = example("events/refund.unresolved.json");
  const refundEvent = constructEvent(refund, signPayload(refund, SECRET), SECRET);
  assert.equal(refundEvent.data.object.object, "refund");
});

test("constructEvent throws SecurePaySignatureError with a useful reason", () => {
  const body = example("events/payment.blocked.json");
  assert.throws(() => constructEvent(body, undefined, SECRET), (e: unknown) => e instanceof SecurePaySignatureError && /No SecurePay-Signature/.test(e.message));
  assert.throws(() => constructEvent(body, signPayload(body, "whsec_wrong"), SECRET), /does not match/);
  assert.throws(() => constructEvent(body, signPayload(body, SECRET, 1000), SECRET), /clock difference/);
  assert.throws(() => constructEvent("[]", signPayload("[]", SECRET), SECRET), /not a SecurePay event/);
});

test("refuses parsed JSON instead of the raw body", () => {
  assert.throws(() => constructEvent({ id: "evt" } as unknown as string, "t=1,v1=" + "0".repeat(64), SECRET), TypeError);
});

test("client.webhooks uses the client's signing secret", () => {
  const sp = new SecurePay({ apiKey: "sp_test_x", signingSecret: SECRET, fetch: (() => {}) as unknown as typeof fetch });
  const body = example("events/payment.authorised.json");
  assert.equal(sp.webhooks.constructEvent(body, signPayload(body, SECRET)).object, "event");
  const noSecret = new SecurePay({ apiKey: "sp_test_x", fetch: (() => {}) as unknown as typeof fetch });
  assert.throws(() => noSecret.webhooks.constructEvent(body, signPayload(body, SECRET)), /No signing secret/);
  assert.equal(noSecret.webhooks.constructEvent(body, signPayload(body, SECRET), { secret: SECRET }).object, "event");
});
