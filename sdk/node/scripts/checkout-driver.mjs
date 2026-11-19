// Pays a SecurePay payment the way the hosted payment page does, for scripts and demos.
// Not part of the npm package. Only for test merchants and simulated test cards.
//
// It calls the hosted checkout's own JSON API (/checkout/<session>/card, /submit, /verify).
// When screening asks for a verification code (an order over S$500, the email
// review@example.com, or a risky pattern such as a burst on one card), it reads the 6-digit
// code from the Mailpit test inbox and enters it, so a run never stalls on a step-up.
//
// Inbox: MAILPIT_URL, for example https://mail.localhost (local stack) or
// https://<user>:<password>@mail.securepaysg.me (the live demo inbox; HTTP Basic auth).

import { randomInt } from "node:crypto";

/**
 * A fresh approving test card from the simulator's demo range 4242 4200 xxxx xxxx (any
 * Luhn-valid number approves). Screening counts a card's attempts over 30 days across the
 * gateway, so reusing 4242 4242 4242 4242 run after run ends in a burst block; a fresh
 * number has no history. (contracts/SIMULATOR-CONTRACT.md section 5.)
 */
export function freshDemoCard(prefix = "42424200") {
  let digits = prefix;
  while (digits.length < 15) digits += String(randomInt(10));
  let sum = 0;
  for (let i = 0; i < 15; i++) {
    let d = Number(digits[14 - i]);
    if (i % 2 === 0) d = d * 2 > 9 ? d * 2 - 9 : d * 2;
    sum += d;
  }
  return digits + String((10 - (sum % 10)) % 10);
}

const TERMINAL = new Set(["authorised", "captured", "blocked", "declined", "expired", "cancelled", "unresolved"]);

/** A Mailpit inbox client. Returns null when MAILPIT_URL is not set. */
export function mailpitFromEnv(env = process.env) {
  if (!env.MAILPIT_URL) return null;
  const url = new URL(env.MAILPIT_URL);
  const headers = { Accept: "application/json" };
  if (url.username || url.password) {
    const user = decodeURIComponent(url.username);
    const pass = decodeURIComponent(url.password);
    headers.Authorization = `Basic ${Buffer.from(`${user}:${pass}`).toString("base64")}`;
    url.username = "";
    url.password = "";
  }
  const base = url.origin + url.pathname.replace(/\/+$/, "");
  const get = async (path) => {
    const r = await fetch(base + path, { headers });
    if (!r.ok) throw new Error(`Mailpit ${path}: HTTP ${r.status}`);
    return r.json();
  };
  return {
    base,
    /** Waits up to `timeoutMs` for the verification email that names `reference`; returns the code. */
    async verificationCode(reference, { timeoutMs = 30_000 } = {}) {
      const until = Date.now() + timeoutMs;
      while (Date.now() < until) {
        const found = await get(`/api/v1/search?query=${encodeURIComponent(`"${reference}"`)}&limit=10`);
        for (const m of found.messages ?? []) {
          const full = await get(`/api/v1/message/${encodeURIComponent(m.ID)}`);
          const text = `${full.Text ?? ""}\n${full.Subject ?? ""}`;
          if (!/verification code/i.test(text)) continue;
          const code = text.match(/verification code is (\d{6})/i)?.[1] ?? text.match(/\b(\d{6})\b/)?.[1];
          if (code) return code;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
      throw new Error(`no verification email for ${reference} in ${base} within ${timeoutMs / 1000} s`);
    },
  };
}

/**
 * Enters a test card on the payment's hosted checkout and submits it, completing a
 * verification step-up from the inbox when asked. Returns the checkout's final view
 * ({ status, reference, ... }) plus `steppedUp` (a code was asked for and entered), without
 * waiting for webhooks.
 */
export async function payWithTestCard(baseUrl, payment, { card = freshDemoCard(), inbox = mailpitFromEnv(), log = () => {} } = {}) {
  const session = payment.checkout_url?.match(/cs_[0-9A-Za-z]{24}/)?.[0];
  if (!session) throw new Error(`payment ${payment.id} has no checkout session in checkout_url`);
  const post = async (path, body) => {
    const r = await fetch(`${baseUrl}/checkout/${session}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const text = await r.text();
    if (r.status !== 200) throw new Error(`checkout ${path}: HTTP ${r.status} ${text}`);
    return JSON.parse(text);
  };
  await post("/card", { number: card, expiry_month: 12, expiry_year: 2030, cvc: "123", privacy_consent: true });
  let view = await post("/submit", {});
  if (view.status === "verification_required") {
    if (!inbox) {
      throw new Error(
        `payment ${payment.id} (${view.reference}) needs a verification code. Set MAILPIT_URL to the test inbox ` +
          "so the script can read it, or use a fresh card and customer email.",
      );
    }
    log(`verification required for ${view.reference}: reading the code from ${inbox.base}`);
    const code = await inbox.verificationCode(view.reference);
    view = await post("/verify", { code });
    log(`code entered: ${view.status}`);
    return { ...view, steppedUp: true };
  }
  return { ...view, steppedUp: false };
}

/**
 * Polls `retrieve` until the payment reaches one of `wanted`. Stops early, with the actual
 * status, when the payment settles somewhere else (it does not wait out the timeout).
 */
export async function waitForStatus(securepay, paymentId, wanted, { timeoutMs = 60_000 } = {}) {
  const until = Date.now() + timeoutMs;
  let last;
  while (Date.now() < until) {
    last = await securepay.payments.retrieve(paymentId);
    if (wanted.includes(last.status)) return last;
    if (TERMINAL.has(last.status) && last.status !== "unresolved") {
      throw new Error(`payment ${paymentId} ended ${last.status}${last.outcome?.reason ? ` (${last.outcome.reason})` : ""}, not ${wanted.join(" or ")}`);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`payment ${paymentId} is still ${last?.status} after ${timeoutMs / 1000} s, not ${wanted.join(" or ")}`);
}
