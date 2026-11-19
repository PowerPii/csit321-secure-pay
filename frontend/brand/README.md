# SecurePay branding kit

One logo, one colour set and one favicon on every SecurePay surface (checkout, guest status,
customer account pages, staff dashboard, emails, PDF receipts, marketing website), and in slides
and the report. The demo store, Volt & Co., is a fictional merchant with its own look on
purpose; it says "Payments by SecurePay" in its footer.

The look is **Slate**: a cool blue-grey page, navy ink, and one warm note, a muted brass,
used only for small marks. It was chosen by the team on 19 Nov 2026 after four rounds of
mockups. How we got there, and the rules for new screens, are in [`docs/BRAND.md`](../../docs/BRAND.md).

## Files

| File | Use |
| --- | --- |
| `securepay-wordmark.svg` | **The logo.** Lowercase "securepay" with a brass full stop, for light backgrounds |
| `securepay-wordmark-on-navy.svg` | The logo for navy backgrounds (title slides, email header) |
| `securepay-mark.svg` | The square mark: "s." on a navy tile. Favicon, app icon, avatar. Also every app's `public/favicon.svg` |
| `securepay-wordmark-1316.png`, `securepay-wordmark-on-navy-1316.png`, `securepay-mark-256.png` | PNG copies for slides, the report and documents |
| `frontend/*/public/apple-touch-icon.png`, website `icon-192.png`, `icon-512.png`, `site.webmanifest` | App icons: the "s." mark on a full navy square (phones round the corners) |
| `frontend/website/public/og-image.png` | The link preview (1200 x 630) shown when the website is shared in chat apps and social sites |
| `tokens.json` | The colours, the source of truth |
| `tokens.css` | The same colours as CSS custom properties |
| `render.cjs` | Makes the PNGs again after an SVG changes: the copies above, the app icons, the link preview and the email header wordmark (`gateway/apps/common/brand/securepay-wordmark-email.png`). Run `npm ci` in `frontend/website` first for the fonts |

The SVGs are outlined paths (Schibsted Grotesk SemiBold, tracking -0.045em), so they look the
same without the font installed.

## Colours

| Token | Hex | Use |
| --- | --- | --- |
| navy | `#13243F` | Brand colour: the wordmark, buttons, the mark's tile, headings |
| ink | `#0E1B30` | Body text |
| brass | `#B08A3E` | **The one accent, for marks only**: the wordmark's full stop, the Pay meter, focus halos, the Test mode outline, bullets. Never for text on white (3.2:1) |
| brassLight | `#D2AE63` | Brass on navy (the full stop on the navy wordmark, small marks in navy bands) |
| slate | `#DCE2EA` | Page background (website, checkout summary panel, active nav item) |
| mist | `#ECEFF4` | Soft panels, table headers, the dashboard canvas |
| line | `#E1E6ED` | Dividers and card borders |
| muted | `#4A5568` | Secondary text (7.4:1 on white) |
| allow / verify / block | `#1F9D63` / `#D98A0B` / `#C2333B` | Screening outcomes only |

## Type

- **Schibsted Grotesk 600** for headings, amounts and the wordmark.
- **Hanken Grotesk** (400 to 700) for everything else.
- JetBrains Mono for code samples on the website only.

All three are self-hosted with `@fontsource` packages. The gateway's Content-Security-Policy
(`font-src 'self'`) blocks Google Fonts, so do not add a font `<link>`.

## Test mode badge

Every SecurePay surface shows that payments are simulated: a small pill with a brass outline
reading **Test mode** (checkout, guest status, account pages, dashboard sidebar), **TEST MODE**
in the email header and PDF receipts, and the store's "Demo store" bar. Its tooltip and the
email footer say "no real money moves". Keep the wording; do not remove the badge for
screenshots.

## Rules

- The wordmark is always lowercase with its full stop; in sentences we still write
  "SecurePay".
- Use the files as they are: no stretching, recolouring or effects. Leave space around the
  wordmark of at least the height of its "s".
- On navy, use `securepay-wordmark-on-navy`; on photos, put it on a navy or white panel.
- Use the "s." mark only where the wordmark does not fit (favicon, app icon, avatar).
- The marks are ours (drawn for this project); no real card scheme, bank or shop logos anywhere.

A gateway test (`test_brand_kit_is_the_same_everywhere` in `gateway/apps/common/tests.py`)
fails if a favicon, a wordmark component, the email or receipt colours, or a theme drift from
this folder.
