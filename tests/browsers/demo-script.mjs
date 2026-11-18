// Cross-browser run of the demo script (NFR-USE-03, check M-USE-03 in
// docs/test-report/MANUAL-TESTS.md). Plays the customer scenes of the demo cheat sheet in
// Chromium (Chrome), Firefox and WebKit (Safari's engine) on a desktop window, then scenes 2
// and 3 again on phone-sized windows (iPhone on WebKit, Pixel on Chromium):
//
//   1  marketing site loads
//   2  buy the USB-C cable, pay with a fresh approve card, shop order turns paid by webhook
//   3  buy the Volt Book 14 (over S$ 500): the verification code step appears; with Mailpit
//      access (MAILPIT_USER, MAILPIT_PASS) the code is read from the email and the payment
//      completes
//   4  card testing: the same fresh card on cable orders until screening blocks it
//   5  lost bank response: the page waits, then reconciliation finds the payment approved
//
// Scenes 6 and 7 (dashboard capture, refund, audit log, integrity check) need staff sign-in
// with an authenticator code and stay a manual click-through; scene 8 is a slide.
//
//   npm i --no-save playwright && npx playwright install chromium firefox webkit
//   SHOP=https://shop.<domain> GATEWAY=https://gateway.<domain> node tests/browsers/demo-script.mjs
//
// Optional: SITE (marketing site), MAILPIT (default https://mail.<domain>), BROWSERS
// (default "chromium,firefox,webkit"; add "chrome" for the installed Google Chrome), PHONES=0 to skip the phone runs, SCENES (e.g. "2,3").
// Test mode only: every card is a fresh simulator demo number, no real money. One full run
// makes about 30 test payments on the server. Writes demo-browsers.json; exit code 1 if any
// step fails.
import { createRequire } from "node:module";
import { randomInt } from "node:crypto";
import { writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const pw = require("playwright");
const SHOP = process.env.SHOP ?? "https://shop.localhost";
const GATEWAY = process.env.GATEWAY ?? "https://gateway.localhost";
const SITE = process.env.SITE ?? "https://csit321-secure-pay.vercel.app/";
const MAILPIT = process.env.MAILPIT ?? GATEWAY.replace("//gateway.", "//mail.");
const MAIL_AUTH = process.env.MAILPIT_USER
  ? "Basic " + Buffer.from(`${process.env.MAILPIT_USER}:${process.env.MAILPIT_PASS ?? ""}`).toString("base64") : null;
const BROWSERS = (process.env.BROWSERS ?? "chromium,firefox,webkit").split(",");
const SCENES = (process.env.SCENES ?? "1,2,3,4,5").split(",").map(Number);
const STAMP = new Date().toISOString().slice(5, 16).replace(/\D/g, "");
const runs = [];

/** A fresh Luhn-valid number in a simulator demo range (approve, lost response). */
function demoCard(prefix) {
  const body = prefix + Array.from({ length: 15 - prefix.length }, () => randomInt(10)).join("");
  for (let check = 0; check < 10; check++) {
    const digits = (body + check).split("").reverse().map(Number);
    const sum = digits.reduce((s, d, i) => s + (i % 2 ? (d * 2 > 9 ? d * 2 - 9 : d * 2) : d), 0);
    if (sum % 10 === 0) return body + check;
  }
}

async function order(page, sku, email) {
  await page.goto(`${SHOP}/products/${sku}`);
  await page.getByRole("button", { name: "Add to cart" }).click();
  await page.waitForLoadState();
  await page.goto(`${SHOP}/checkout`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Full name").fill("Mei Tan");
  await page.getByLabel("Delivery address").fill("1 Demo Road, Singapore 123456");
  await page.locator("form button[type=submit]").last().click();
  await page.waitForURL(/\/pay\/cs_/, { timeout: 20000 });
  await page.waitForSelector("#number");
}

async function pay(page, card, email) {
  const field = page.locator("#email");
  if (await field.count() && !(await field.inputValue())) await field.fill(email);
  await page.locator("#number").fill(card);
  await page.locator("#expiry").fill("12/30");
  await page.locator("#cvc").fill("123");
  await page.locator("#name").fill("Mei Tan");
  const consent = page.locator("#privacy-consent");
  if (await consent.count() && !(await consent.isChecked())) await consent.check();
  await page.getByRole("button", { name: /^Pay S\$/ }).click();
}

const heading = (page, re, timeout = 25000) =>
  page.getByRole("heading", { level: 1, name: re }).waitFor({ timeout }).then(() => true, () => false);

/** Waits for the result page and returns its heading ("Payment successful", "We couldn't ..."). */
async function resultHeading(page, timeout = 30000) {
  const h1 = page.getByRole("heading", { level: 1 }).filter({ hasNotText: /^(Pay S\$|Checking your payment)/ });
  return h1.first().waitFor({ timeout }).then(async () => (await h1.first().textContent()).trim(), () => "no result page");
}

async function latestCode(email, after) {
  for (let i = 0; i < 20; i++) {
    const r = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent("to:" + email)}`, { headers: { Authorization: MAIL_AUTH } });
    if (!r.ok) throw new Error(`Mailpit answered ${r.status}`);
    const msg = (await r.json()).messages?.find((m) => new Date(m.Created) >= after && /code/i.test(m.Subject + m.Snippet));
    if (msg) {
      const full = await (await fetch(`${MAILPIT}/api/v1/message/${msg.ID}`, { headers: { Authorization: MAIL_AUTH } })).json();
      const code = (full.Text ?? "").match(/\b(\d{6})\b/);
      if (code) return code[1];
    }
    await new Promise((res) => setTimeout(res, 1500));
  }
  throw new Error("no code email within 30 s");
}

const SCENE_FNS = {
  1: async (page) => {
    const r = await page.goto(SITE);
    if (!r?.ok()) throw new Error(`site answered ${r?.status()}`);
    await page.getByRole("heading", { level: 1 }).first().waitFor();
    return "marketing site home page shown";
  },
  2: async (page) => {
    const email = `mei.${STAMP}@example.com`;
    await order(page, "CABLE-01", email);
    await pay(page, demoCard("42424200"), email);
    if (!(await heading(page, /Payment successful/))) throw new Error("no 'Payment successful'");
    await page.getByRole("link", { name: /Return to/ }).click();
    await page.waitForURL(new RegExp(SHOP.replace(/[.]/g, "\\.") + "/orders/\\d+"), { timeout: 20000 });
    await page.locator(".badge.ok").waitFor({ timeout: 30000 });
    return `paid; shop order says "${(await page.locator(".badge.ok").first().textContent()).trim()}"`;
  },
  3: async (page) => {
    const email = `mei.${STAMP}@example.com`;
    await order(page, "LAPTOP-14", email);
    const after = new Date(Date.now() - 5000);
    await pay(page, demoCard("42424200"), email);
    if (!(await heading(page, /Check your email/))) throw new Error("no code page for S$ 2,399");
    if (!MAIL_AUTH) return "code page shown (code not entered: no Mailpit access in this run)";
    await page.locator("#code").fill(await latestCode(email, after));
    await page.getByRole("button", { name: /Confirm|Verify|Pay/ }).first().click();
    if (!(await heading(page, /Payment successful/))) throw new Error("no 'Payment successful' after the code");
    return "code from the email accepted; paid";
  },
  4: async (page) => {
    const card = demoCard("55555500");
    for (let attempt = 1; attempt <= 8; attempt++) {
      await order(page, "CABLE-01", `fraud.${STAMP}@example.com`);
      await pay(page, card, `fraud.${STAMP}@example.com`);
      const result = await resultHeading(page);
      if (/couldn't complete/.test(result)) return `card blocked on attempt ${attempt}`;
      if (!/Payment successful|Check your email/.test(result)) throw new Error(`attempt ${attempt}: result "${result}"`);
    }
    throw new Error("not blocked after 8 attempts");
  },
  5: async (page) => {
    await order(page, "STAND-PH", `mei.${STAMP}@example.com`);
    const started = Date.now();
    await pay(page, demoCard("40000119"), `mei.${STAMP}@example.com`);
    if (!(await heading(page, /confirming your payment|Checking your payment/, 30000))) throw new Error("no waiting page");
    if (!(await heading(page, /Payment successful/, 120000))) throw new Error("still waiting after 2 min");
    return `waited, then approved by reconciliation after ${Math.round((Date.now() - started) / 1000)} s`;
  },
};

async function run(type, label, contextOptions, scenes) {
  // "chrome" and "msedge" drive the installed Google Chrome / Edge instead of Playwright's Chromium.
  const browser = ["chrome", "msedge"].includes(type)
    ? await pw.chromium.launch({ channel: type }) : await pw[type].launch();
  const version = browser.version();
  for (const n of scenes) {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true, ...contextOptions });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    let ok = true, note;
    try { note = await SCENE_FNS[n](page); } catch (e) { ok = false; note = e.message.split("\n")[0]; }
    if (errors.length) note += ` (page errors: ${errors.slice(0, 2).join("; ")})`;
    runs.push({ browser: type, version, window: label, scene: n, ok, note });
    console.log(`${ok ? "ok  " : "FAIL"} ${type} ${version} ${label} scene ${n}: ${note}`);
    await ctx.close();
  }
  await browser.close();
}

for (const type of BROWSERS) await run(type, "desktop 1280x800", { viewport: { width: 1280, height: 800 } }, SCENES);
if (process.env.PHONES !== "0") {
  const phoneScenes = SCENES.filter((n) => n === 2 || n === 3);
  if (BROWSERS.includes("webkit")) await run("webkit", "iPhone 15 (emulated)", pw.devices["iPhone 15"], phoneScenes);
  if (BROWSERS.includes("chromium")) await run("chromium", "Pixel 7 (emulated)", pw.devices["Pixel 7"], phoneScenes);
}

writeFileSync("demo-browsers.json", JSON.stringify({ at: new Date().toISOString(), SHOP, GATEWAY, runs }, null, 1));
const failed = runs.filter((r) => !r.ok).length;
console.log(`${runs.length} scene runs, ${failed} failed. Details in demo-browsers.json`);
process.exit(failed ? 1 : 0);
