// Accessibility and phone-width scan of a running SecurePay stack (NFR-USE-01, NFR-USE-02;
// docs/test-report/ACCESSIBILITY.md). Runs axe-core (WCAG 2.2 A and AA plus best practice) in
// Chromium on every customer page, at 320 px and 1280 px, measures sideways scrolling, and
// pays once by keyboard alone. With STAFF_EMAIL, STAFF_PASSWORD and a fresh STAFF_CODE it also
// signs in to the dashboard and scans every page that account can open.
//
//   npm i --no-save playwright axe-core@4.10.2 && npx playwright install chromium
//   SHOP=https://shop.<domain> GATEWAY=https://gateway.<domain> node tests/a11y/scan.mjs
//
// Each run makes two test payments in the demo shop (test mode, no real money); NO_PAY=1 stops
// at the card form.
// Exit code 1 if any page has an axe violation or scrolls sideways.
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const axeSource = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const SHOP = process.env.SHOP ?? "https://shop.localhost";
const GATEWAY = process.env.GATEWAY ?? "https://gateway.localhost";
const CARDS = ["4242424242424242", "5555555555554444"]; // simulator approve cards
const results = [];
const notes = [];

async function scan(page, name) {
  await page.addScriptTag({ content: axeSource });
  const r = await page.evaluate(() => window.axe.run(document, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
  }));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const width = page.viewportSize().width;
  results.push({ name, width, overflow, violations: r.violations.map((v) => ({
    id: v.id, impact: v.impact, help: v.help, targets: v.nodes.slice(0, 5).map((n) => n.target.join(" ")) })) });
}

async function tabUntil(page, test, max = 40) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (await page.evaluate(test)) return true;
  }
  return false;
}

async function customer(browser, width, card) {
  const ctx = await browser.newContext({ viewport: { width, height: 800 }, ignoreHTTPSErrors: true, bypassCSP: true });
  const page = await ctx.newPage();
  await page.goto(SHOP + "/"); await scan(page, "shop home");
  await page.locator(".product form button").first().click(); await page.waitForLoadState();
  await page.goto(SHOP + "/cart"); await scan(page, "shop cart");
  await page.goto(SHOP + "/checkout"); await page.click("button[type=submit]"); await page.waitForLoadState();
  await scan(page, "shop checkout with errors");
  await page.fill("input[name=email]", "a11y@example.com");
  await page.fill("input[name=full_name]", "Access Test");
  await page.fill("[name=delivery_address]", "1 Test Road, Singapore 123456");
  await page.click("button[type=submit]"); await page.waitForURL(/\/pay\/cs_/, { timeout: 20000 });
  await page.waitForSelector("#number"); await scan(page, "checkout card form");

  // Keyboard only from here: Tab to Pay, submit empty, then fill from the first error.
  await page.focus("body");
  const reachedPay = await tabUntil(page, () => document.activeElement?.getAttribute("type") === "submit");
  await page.keyboard.press("Enter"); await page.waitForTimeout(400);
  const firstError = await page.evaluate(() => document.activeElement?.id);
  await scan(page, "checkout card form with errors");
  if (process.env.NO_PAY) { notes.push(`${width}px keyboard: Pay reached by Tab=${reachedPay}, empty submit focused #${firstError} (NO_PAY: not paid)`); }
  else {
  if (firstError === "email") { await page.keyboard.type("a11y@example.com"); await page.keyboard.press("Tab"); }
  await page.keyboard.type(card); await page.keyboard.press("Tab"); await page.keyboard.type("1230");
  await page.keyboard.press("Tab"); await page.keyboard.type("123"); await page.keyboard.press("Tab");
  await page.keyboard.type("Access Test"); await page.keyboard.press("Tab"); await page.keyboard.press("Space");
  await tabUntil(page, () => document.activeElement?.getAttribute("type") === "submit");
  await page.keyboard.press("Enter");
  const paid = await page.waitForSelector("text=Payment successful", { timeout: 20000 }).then(() => true, () => false);
  const focus = await page.evaluate(() => `${document.activeElement?.tagName} "${document.activeElement?.textContent}"`);
  if (paid) {
    const stay = page.getByRole("button", { name: "Stay on this page" });
    if (await stay.count()) await stay.click();
    await scan(page, "checkout approved");
  }
  notes.push(`${width}px keyboard payment: Pay reached by Tab=${reachedPay}, empty submit focused #${firstError}, ` +
    `paid=${paid}, focus after paying on ${focus}`);
  }
  for (const [name, path] of [["guest status", "/guest/status"], ["account sign-in", "/account/sign-in"],
    ["invalid checkout link", "/pay/cs_000000000000000000000000"]]) {
    await page.goto(GATEWAY + path); await page.waitForTimeout(1200); await scan(page, name);
  }
  await ctx.close();
}

async function dashboard(browser, width) {
  const { STAFF_EMAIL: email, STAFF_PASSWORD: password, STAFF_CODE: code } = process.env;
  const ctx = await browser.newContext({ viewport: { width, height: 800 }, ignoreHTTPSErrors: true, bypassCSP: true });
  const page = await ctx.newPage();
  await page.goto(GATEWAY + "/dashboard/login"); await scan(page, "dashboard sign-in");
  if (!email || !password || !code) { await ctx.close(); return; }
  await page.getByLabel("Email").fill(email); await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click(); await page.waitForURL(/totp/);
  await page.keyboard.type(code); await page.keyboard.press("Enter");
  await page.waitForURL(/overview|backup|two-step/, { timeout: 15000 });
  const links = await page.$$eval('nav[aria-label="Main"] a', (as) => as.map((a) => a.getAttribute("href")));
  for (const href of links) { await page.goto(new URL(href, GATEWAY).href); await page.waitForTimeout(1500); await scan(page, `dashboard ${href}`); }
  await page.goto(GATEWAY + "/dashboard/payments"); await page.waitForTimeout(1500);
  const first = page.locator('a[href*="/payments/pay_"]').first();
  if (await first.count()) { await first.click(); await page.waitForTimeout(1500); await scan(page, "dashboard payment detail"); }
  await ctx.close();
}

const browser = await chromium.launch();
await customer(browser, 1280, CARDS[0]);
await customer(browser, 320, CARDS[1]);
await dashboard(browser, 1280); // one fresh code signs in once; the menu is the same at 360 px
await browser.close();

writeFileSync("a11y-results.json", JSON.stringify({ at: new Date().toISOString(), SHOP, GATEWAY, notes, results }, null, 1));
let failed = 0;
for (const r of results) {
  const bad = r.violations.length || r.overflow > 0;
  failed += bad ? 1 : 0;
  console.log(`${bad ? "FAIL" : "ok  "} ${String(r.width).padStart(4)}px ${r.name}${r.overflow > 0 ? ` (scrolls ${r.overflow}px sideways)` : ""}`);
  for (const v of r.violations) console.log(`       [${v.impact}] ${v.id}: ${v.help} -> ${v.targets.join(", ")}`);
}
console.log(notes.join("\n"));
console.log(`${results.length} page scans, ${failed} with problems. Details in a11y-results.json`);
process.exit(failed ? 1 : 0);
