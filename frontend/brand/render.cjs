// Renders the PNG copies of the wordmark and mark for slides, the report and emails, the app
// icons (apple-touch-icon, manifest icons) and the website's link preview image. Run from
// the repo root after changing an SVG:  node frontend/brand/render.cjs
// (Playwright with Chromium must be installed, and `npm ci` run in frontend/website for the
// fonts; the PNGs are committed.) The SVGs are outlined
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
  await page.close();

  // App icons for the website, checkout and dashboard: the "s." mark on a full navy square
  // (iOS and Android round the corners themselves), for apple-touch-icon and the web manifest.
  const markSvg = fs.readFileSync(path.join(dir, "securepay-mark.svg"), "utf8").replace(' rx="15"', "");
  const icons = [
    ["website", "apple-touch-icon.png", 180], ["website", "icon-192.png", 192], ["website", "icon-512.png", 512],
    ["checkout", "apple-touch-icon.png", 180], ["dashboard", "apple-touch-icon.png", 180],
  ];
  for (const [app, name, size] of icons) {
    const p = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    const svg = markSvg.replace(/ width="[^"]+" height="[^"]+"/, ` width="${size}" height="${size}"`);
    await p.setContent(`<html><body style="margin:0">${svg}</body></html>`);
    await p.screenshot({ path: path.join(dir, `../${app}/public/${name}`) });
    await p.close();
  }

  // The website's link preview (og:image, 1200 x 630): slate page, wordmark, the hero line.
  const fonts = path.join(dir, "../website/node_modules/@fontsource");
  const font = (pkg, file) => "data:font/woff2;base64," + fs.readFileSync(path.join(fonts, pkg, "files", file)).toString("base64");
  const word = fs.readFileSync(path.join(dir, "securepay-wordmark.svg"), "utf8")
    .replace(/ width="[^"]+" height="[^"]+"/, ' width="420" height="80"');
  const og = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await og.setContent(`<html><head><style>
    @font-face { font-family: S; font-weight: 600; src: url(${font("schibsted-grotesk", "schibsted-grotesk-latin-600-normal.woff2")}); }
    @font-face { font-family: H; font-weight: 500; src: url(${font("hanken-grotesk", "hanken-grotesk-latin-500-normal.woff2")}); }
    body { margin: 0; width: 1200px; height: 630px; background: #DCE2EA; font-family: H; color: #0E1B30; }
    .card { position: absolute; inset: 56px; background: #fff; border-radius: 16px; padding: 64px 72px;
            box-shadow: 0 1px 2px rgba(19,36,63,.06), 0 12px 32px rgba(19,36,63,.08); box-sizing: border-box; }
    h1 { font-family: S; font-weight: 600; font-size: 60px; line-height: 1.08; letter-spacing: -0.03em;
         color: #13243F; margin: 56px 0 0; max-width: 15ch; }
    p { position: absolute; left: 72px; bottom: 56px; margin: 0; font-size: 22px; color: #4A5568; }
    p b { color: #B08A3E; font-weight: 500; }
  </style></head><body><div class="card">${word}
    <h1>Every payment gets a reason before it gets a yes.</h1>
    <p>Card payment gateway with fraud screening <b>&middot;</b> CSIT321 student project, simulated payments only</p>
  </div></body></html>`);
  await og.evaluate(() => document.fonts.ready);
  await og.screenshot({ path: path.join(dir, "../website/public/og-image.png") });
  await browser.close();
})();
