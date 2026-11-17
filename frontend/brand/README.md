# SecurePay branding kit

Sprint 12 of the demo-day plan: one logo, one colour set and one favicon on every SecurePay
surface (checkout, guest status, customer account pages, staff dashboard, emails, marketing
website), and in slides and the report. The demo store, Volt & Co., is a fictional merchant
with its own look on purpose; it says "Payments by SecurePay" in its footer.

## Files

| File | Use |
| --- | --- |
| `securepay-mark.svg` | The mark: a saffron shield with a white tick on a navy tile. Also every app's `public/favicon.svg` |
| `securepay-logo.svg` | Mark and wordmark, for light backgrounds |
| `securepay-logo-on-navy.svg` | Mark and wordmark, for navy backgrounds (title slides) |
| `securepay-mark-256.png`, `securepay-logo-1064.png`, `securepay-logo-on-navy-1064.png` | PNG copies for slides, the report and documents |
| `tokens.json` | The colours, the source of truth |
| `tokens.css` | The same colours as CSS custom properties |
| `render.cjs` | Makes the PNGs again after an SVG changes, including the 56 px mark the gateway puts inside every email (`gateway/apps/common/brand/`) |

## Colours

| Token | Hex | Use |
| --- | --- | --- |
| navy | `#0F2240` | Primary: top bars, buttons, the mark's tile |
| ink | `#0A1830` | Body text |
| saffron | `#F5A524` | Signal colour: the shield, the Test mode badge, focus rings. Never for body text on white (too little contrast) |
| paper | `#FAF8F4` | Warm page background |
| line | `#E6E1D8` | Dividers |
| muted | `#5B6475` | Secondary text |
| allow / verify / block | `#1F9D63` / `#D98A0B` / `#D9434B` | Screening outcomes only |

Type: Inter for text; Space Grotesk for large headings on the website and in slides.

## Test mode badge

Every SecurePay surface shows that payments are simulated: a small saffron pill reading
**Test mode** (checkout, guest status, account pages, dashboard sidebar), **TEST MODE** in the
email header, and the store's "Demo store" bar. Its tooltip and the email footer say
"no real money moves". Keep the wording; do not remove the badge for screenshots.

## Rules

- Use the files as they are: no stretching, recolouring or effects. Leave space around the
  mark of at least a quarter of its width.
- On navy, use `securepay-logo-on-navy`; on photos, put the logo on a navy or white panel.
- The mark is ours (drawn for this project); no real card scheme, bank or shop logos anywhere.

A gateway test (`test_brand_kit_is_the_same_everywhere` in `gateway/apps/common/tests.py`)
fails if a favicon, the checkout's `Brand.tsx`, the email colours or a theme drift from this
folder.
