// Renders the PNG copies of the wordmark and mark for slides, the report and emails. Run from
// the repo root after changing an SVG:  node frontend/brand/render.cjs
// (Playwright with Chromium must be installed; the PNGs are committed.) The SVGs are outlined
// paths made from Schibsted Grotesk SemiBold, so no font is needed to draw them.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const jobs = [
  // [svg, png, css width, css height, scale, background]
  ["securepay-mark.svg", "securepay-mark-256.png", 64, 64, 4, "transparent"],
  ["securepay-wordmark.svg", "securepay-wordmark-1316.png", 329, 63, 4, "transparent"],
  ["securepay-wordmark-on-navy.svg", "securepay-wordmark-on-navy-1316.png", 329, 63, 4, "#13243F"],
];

(async () => {
  const browser = await chromium.launch();
  for (const [svg, png, w, h, scale, bg] of jobs) {
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: scale });
    const markup = fs.readFileSync(path.join(dir, svg), "utf8")
      .replace(/ width="[^"]+" height="[^"]+"/, ` width="${w}" height="${h}"`);
    await page.setContent(`<html><body style="margin:0;background:${bg}">${markup}</body></html>`);
    await page.screenshot({ path: path.join(dir, png), omitBackground: bg === "transparent" });
    await page.close();
  }
  // The wordmark the gateway embeds in every email header, on navy (128 x 24 shown, 2x).
  const page = await browser.newPage({ viewport: { width: 128, height: 24 }, deviceScaleFactor: 2 });
  const mark = fs.readFileSync(path.join(dir, "securepay-wordmark-on-navy.svg"), "utf8")
    .replace(/ width="[^"]+" height="[^"]+"/, ' width="128" height="24"');
  await page.setContent(`<html><body style="margin:0;background:#13243F">${mark}</body></html>`);
  await page.screenshot({ path: path.join(dir, "../../gateway/apps/common/brand/securepay-wordmark-email.png") });
  await browser.close();
})();
