// Recovery drill for a merchant's first integration: a lost reply, a merchant restart, and
// recovery of the SAME payment and the SAME refund. Not part of the npm package.
//
//   # in an empty folder, with the published package:
//   npm init -y && npm install securepaysg@0.2.0
//   cp <repo>/sdk/node/scripts/{recovery-demo,checkout-driver}.mjs .
//   SECUREPAY_API_KEY=sp_test_... SECUREPAY_SIGNING_SECRET=whsec_... \
//   SECUREPAY_BASE_URL=https://gateway.securepaysg.me \
//   MAILPIT_URL=https://<user>:<password>@mail.securepaysg.me node recovery-demo.mjs
//
//   # or from sdk/node in the repository, after `npm run build` (the package resolves to dist/)
//
// Every step runs in a NEW Node.js process, so nothing survives in memory between them: the
// only thing the "merchant" keeps is its order file (DEMO_STORE, default
// ./securepay-demo-orders.json), standing in for the shop's database.
//
//   1. create-lost     Save order + idempotency key, call payments.create; the reply is lost
//                      and the process "crashes" before it learns the payment ID.
//   2. recover-create  Restart. Same order, same saved key: the gateway replays the original
//                      payment (Idempotent-Replayed: true). No second payment exists.
//   3. pay             The shopper pays at checkout_url. The order uses the step-up fixture
//                      email review@example.com, so a verification code is required; with
//                      MAILPIT_URL the code is read from the test inbox, otherwise open the
//                      printed link in a browser and enter the emailed code there.
//   4. capture         Capture, with its own saved key.
//   5. refund-lost     Save a refund record + its own key, call refunds.create for part of the
//                      amount; the reply is lost and the process "crashes".
//   6. recover-refund  Restart. Same saved key: the gateway replays the original refund, and
//                      refunds.list shows exactly one refund.
//   7. webhook-twice   A webhook handler (signature check, event-ID dedupe, sequence rule,
//                      order update) receives one signed event twice over HTTP; the second
//                      copy is skipped. See the note at that step about what is simulated.
//
// Use a test merchant only: the payment and refund appear on its dashboard.
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { SecurePay, SecurePayConnectionError, SecurePaySignatureError, VERSION, signPayload } from "securepaysg";
import { payWithTestCard, waitForStatus } from "./checkout-driver.mjs";

const env = process.env;
const STORE = env.DEMO_STORE ?? "securepay-demo-orders.json";
const baseUrl = env.SECUREPAY_BASE_URL ?? "https://gateway.securepaysg.me";
const PHASES = ["create-lost", "recover-create", "pay", "capture", "refund-lost", "recover-refund", "webhook-twice"];

// ---- the merchant's "database" ---------------------------------------------------------
const load = () => (existsSync(STORE) ? JSON.parse(readFileSync(STORE, "utf8")) : { orders: {}, refunds: {}, webhook_events: {} });
function save(db) {
  writeFileSync(`${STORE}.tmp`, JSON.stringify(db, null, 2));
  renameSync(`${STORE}.tmp`, STORE); // atomic: a crash never leaves half a file
}
const say = (msg) => console.log(`  ${msg}`);

// ---- a network that loses the gateway's reply ------------------------------------------
/** Sends the request for real, waits for the gateway's answer, then throws it away. */
function loseRepliesTo(pathSuffix) {
  return async (url, init) => {
    const response = await fetch(url, init);
    if (init?.method !== "POST" || !String(url).endsWith(pathSuffix)) return response;
    await response.text();
    throw new TypeError(`simulated: the gateway answered ${response.status}, but the reply was lost on the way back`);
  };
}

function client(extra = {}) {
  const { SECUREPAY_API_KEY: apiKey, SECUREPAY_SIGNING_SECRET: signingSecret } = env;
  if (!apiKey || !signingSecret) {
    console.error("Set SECUREPAY_API_KEY and SECUREPAY_SIGNING_SECRET (a test merchant's).");
    process.exit(2);
  }
  return new SecurePay({ apiKey, signingSecret, baseUrl, allowInsecureHttp: env.SECUREPAY_ALLOW_HTTP === "1", ...extra });
}

const current = (db) => {
  const order = db.orders[db.current];
  if (!order) throw new Error(`no current order in ${STORE}: run the whole drill (no step name)`);
  return order;
};

function paymentParams(order) {
  return {
    amount: order.amount,
    currency: "SGD",
    order_reference: order.id,
    return_url: "https://shop.example.com/orders/return",
    description: "SDK recovery drill",
    customer_email: "review@example.com", // step-up fixture: screening asks for a code
  };
}

// ---- the steps ---------------------------------------------------------------------------
const steps = {
  async "create-lost"() {
    const db = load();
    const id = `ORD-${randomUUID().slice(0, 8).toUpperCase()}`;
    // 1. Write the order AND its idempotency key before calling the gateway.
    db.orders[id] = { id, amount: 4590, status: "awaiting_payment", payment_create_key: randomUUID(), payment_id: null, last_sequence: 0 };
    db.current = id;
    save(db);
    say(`order ${id} saved with payment_create_key ${db.orders[id].payment_create_key}`);
    const sp = client({ fetch: loseRepliesTo("/v1/payments"), maxRetries: 1 });
    try {
      await sp.payments.create(paymentParams(db.orders[id]), { idempotencyKey: db.orders[id].payment_create_key });
      throw new Error("expected the reply to be lost");
    } catch (err) {
      if (!(err instanceof SecurePayConnectionError)) throw err;
      say(`SecurePayConnectionError after ${err.attempts} attempts: outcomeUnknown=${err.outcomeUnknown}`);
      say(`err.idempotencyKey ${err.idempotencyKey === db.orders[id].payment_create_key ? "equals" : "DIFFERS FROM"} the saved key`);
      if (err.idempotencyKey !== db.orders[id].payment_create_key || !err.outcomeUnknown) process.exit(1);
    }
    say("merchant process stops here, before it learned the payment ID");
    process.exit(0);
  },

  async "recover-create"() {
    const db = load();
    const order = current(db);
    if (order.payment_id) throw new Error("order already has a payment");
    say(`restarted: order ${order.id} has a saved key and no payment ID, so retry with that key`);
    const payment = await client().payments.create(paymentParams(order), { idempotencyKey: order.payment_create_key });
    const replayed = payment.lastResponse.idempotentReplayed;
    say(`payment ${payment.id} (${payment.reference}), Idempotent-Replayed: ${replayed}, signature verified: ${payment.lastResponse.signatureVerified}`);
    if (!replayed) throw new Error("the gateway did not replay: a second payment may exist");
    Object.assign(order, { payment_id: payment.id, payment_reference: payment.reference, checkout_url: payment.checkout_url });
    save(db);
    say("the same payment the lost reply described: no second payment was created");
  },

  async pay() {
    const db = load();
    const order = current(db);
    const sp = client();
    const payment = await sp.payments.retrieve(order.payment_id);
    if (env.MAILPIT_URL) {
      const view = await payWithTestCard(baseUrl, payment, { log: say });
      if (!view.steppedUp) throw new Error("expected a verification step-up for review@example.com");
    } else {
      say(`no MAILPIT_URL: open ${payment.checkout_url} , pay with 4242 4242 4242 4242 and enter the emailed code`);
    }
    const authorised = await waitForStatus(sp, order.payment_id, ["authorised"], { timeoutMs: env.MAILPIT_URL ? 60_000 : 600_000 });
    order.status = "paid"; // the merchant order update, from a signed GET reply
    order.last_sequence = Math.max(order.last_sequence, authorised.sequence);
    save(db);
    say(`verification-required checkout completed: ${authorised.status}; order ${order.id} marked paid`);
  },

  async capture() {
    const db = load();
    const order = current(db);
    order.capture_key ??= randomUUID();
    save(db);
    const captured = await client().payments.capture(order.payment_id, {}, { idempotencyKey: order.capture_key });
    order.status = "fulfilled";
    save(db);
    say(`captured ${captured.captured_amount} cents (HTTP ${captured.lastResponse.status})`);
  },

  async "refund-lost"() {
    const db = load();
    const order = current(db);
    const refundId = `${order.id}-R1`;
    // A refund is its own operation: its own record and its own key, saved first.
    db.refunds[refundId] = { id: refundId, order_id: order.id, amount: 1500, key: randomUUID(), gateway_refund_id: null };
    db.current_refund = refundId;
    save(db);
    say(`refund ${refundId} (1500 cents) saved with its own key ${db.refunds[refundId].key}`);
    const sp = client({ fetch: loseRepliesTo("/refunds"), maxRetries: 1 });
    try {
      await sp.refunds.create(order.payment_id, { amount: 1500, reason: "One item returned" }, { idempotencyKey: db.refunds[refundId].key });
      throw new Error("expected the reply to be lost");
    } catch (err) {
      if (!(err instanceof SecurePayConnectionError)) throw err;
      say(`SecurePayConnectionError: outcomeUnknown=${err.outcomeUnknown}, key ${err.idempotencyKey === db.refunds[refundId].key ? "preserved" : "LOST"}`);
      if (err.idempotencyKey !== db.refunds[refundId].key) process.exit(1);
    }
    say("merchant process stops here, before it learned the refund ID");
    process.exit(0);
  },

  async "recover-refund"() {
    const db = load();
    const order = current(db);
    const record = db.refunds[db.current_refund];
    const sp = client();
    say(`restarted: refund ${record.id} has a saved key and no gateway refund ID, so retry with that key`);
    const refund = await sp.refunds.create(order.payment_id, { amount: record.amount, reason: "One item returned" }, { idempotencyKey: record.key });
    say(`refund ${refund.id} (${refund.reference}) ${refund.status}, Idempotent-Replayed: ${refund.lastResponse.idempotentReplayed}`);
    if (!refund.lastResponse.idempotentReplayed) throw new Error("the gateway did not replay: a second refund may exist");
    const list = await sp.refunds.list(order.payment_id);
    say(`refunds.list: ${list.data.length} refund(s), ${list.refundable_amount} cents still refundable`);
    if (list.data.length !== 1) throw new Error("expected exactly one refund");
    Object.assign(record, { gateway_refund_id: refund.id, reference: refund.reference, status: refund.status });
    save(db);
  },

  async "webhook-twice"() {
    const db = load();
    const order = current(db);
    const sp = client();
    const secret = env.SECUREPAY_SIGNING_SECRET;
    // The merchant's webhook handler: verify, skip a seen event ID, apply the sequence rule,
    // then update the order. This is the code a shop would run behind its webhook URL.
    const outcomes = [];
    const server = createServer((req, res) => {
      const chunks = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => {
        let event;
        try {
          event = sp.webhooks.constructEvent(Buffer.concat(chunks), req.headers["securepay-signature"]);
        } catch (err) {
          res.writeHead(err instanceof SecurePaySignatureError ? 400 : 500).end();
          return;
        }
        const state = load();
        const o = state.orders[order.id];
        let outcome;
        if (state.webhook_events[event.id]) outcome = "duplicate: skipped";
        else if (event.sequence <= o.last_sequence) outcome = "older sequence: skipped";
        else {
          const object = event.data.object;
          o.last_sequence = event.sequence;
          if (object.object === "refund") {
            const r = Object.values(state.refunds).find((x) => x.gateway_refund_id === object.id);
            if (r) r.status = object.status;
            o.status = object.status === "completed" ? "partly_refunded" : o.status;
          }
          outcome = `applied ${event.type}: order now ${o.status}`;
        }
        state.webhook_events[event.id] ??= { type: event.type, received: 0 };
        state.webhook_events[event.id].received += 1;
        save(state);
        outcomes.push(outcome);
        res.writeHead(200).end(); // reply 2xx quickly; slow work goes after this
      });
    });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${server.address().port}/webhooks/securepay`;

    // What is simulated: the gateway only delivers to an approved public HTTPS address, so
    // this drill builds the refund.completed event from the refund's signed current state
    // and signs it with your signing secret, exactly as the gateway signs. To see a real
    // second delivery, use "Resend" on the dashboard's webhook log for the demo shop.
    const payment = await sp.payments.retrieve(order.payment_id);
    const refund = db.refunds[db.current_refund];
    const refundObject = await sp.refunds.retrieve(refund.gateway_refund_id);
    const body = JSON.stringify({
      id: `evt_DRILL${randomUUID().replace(/-/g, "").slice(0, 19)}`,
      object: "event",
      type: "refund.completed",
      created_at: new Date().toISOString(),
      payment_id: payment.id,
      sequence: payment.sequence,
      data: { object: refundObject },
    });
    const header = signPayload(body, secret);
    for (let i = 1; i <= 2; i++) {
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "SecurePay-Signature": header }, body });
      say(`delivery ${i}: HTTP ${r.status}, ${outcomes.at(-1)}`);
    }
    server.close();
    if (!outcomes[0]?.startsWith("applied") || !outcomes[1]?.startsWith("duplicate")) throw new Error("webhook dedupe did not behave");
    const final = load();
    const o = final.orders[order.id];
    const evidence = {
      when: new Date().toISOString(),
      sdk: `securepaysg@${VERSION}`,
      gateway: baseUrl,
      order: o.id,
      payment: { id: o.payment_id, reference: o.payment_reference },
      refund: { id: refund.gateway_refund_id, reference: refund.reference, amount: refund.amount, status: refund.status },
      order_status: o.status,
    };
    writeFileSync("recovery-evidence.json", JSON.stringify(evidence, null, 2));
    console.log("\nRecovery drill passed:");
    console.log(JSON.stringify(evidence, null, 2));
  },
};

// ---- run ---------------------------------------------------------------------------------
const phase = process.argv[2];
if (phase) {
  if (!steps[phase]) {
    console.error(`unknown step ${phase}; steps: ${PHASES.join(", ")}`);
    process.exit(2);
  }
  await steps[phase]();
} else {
  console.log(`securepaysg@${VERSION} recovery drill against ${baseUrl} (orders in ${STORE})`);
  const self = fileURLToPath(import.meta.url);
  for (const [i, name] of PHASES.entries()) {
    console.log(`\n${i + 1}. ${name} (new process)`);
    const r = spawnSync(process.execPath, [self, name], { stdio: "inherit", env });
    if (r.status !== 0) {
      console.error(`\nstep ${name} failed (exit ${r.status})`);
      process.exit(1);
    }
  }
}
