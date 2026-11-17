// Renders the PNG copies of the logo for slides, the report and emails. Run from the repo
// root after changing an SVG:  node frontend/brand/render.cjs
// (Playwright with Chromium must be installed; the PNGs are committed.)
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const jobs = [
  // [svg, png, css width, css height, scale, background]
  ["securepay-mark.svg", "securepay-mark-256.png", 64, 64, 4, "transparent"],
  ["securepay-logo.svg", "securepay-logo-1064.png", 266, 64, 4, "transparent"],
  ["securepay-logo-on-navy.svg", "securepay-logo-on-navy-1064.png", 266, 64, 4, "#0F2240"],
];

(async () => {
  const browser = await chromium.launch();
  for (const [svg, png, w, h, scale, bg] of jobs) {
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: scale });
    const markup = fs.readFileSync(path.join(dir, svg), "utf8");
    await page.setContent(`<html><body style="margin:0;background:${bg}">${markup}</body></html>`);
    await page.screenshot({ path: path.join(dir, png), omitBackground: bg === "transparent" });
    await page.close();
  }
  // The 56 px mark the gateway embeds in every email (28 px shown, 2x for sharp screens).
  const page = await browser.newPage({ viewport: { width: 28, height: 28 }, deviceScaleFactor: 2 });
  const mark = fs.readFileSync(path.join(dir, "securepay-mark.svg"), "utf8")
    .replace("<svg ", '<svg width="28" height="28" ');
  await page.setContent(`<html><body style="margin:0">${mark}</body></html>`);
  await page.screenshot({ path: path.join(dir, "../../gateway/apps/common/brand/securepay-mark-56.png"), omitBackground: true });
  await browser.close();
})();
