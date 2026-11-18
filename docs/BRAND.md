# Brand brief: building SecurePay screens

How SecurePay should look and feel, for anyone (person or AI assistant) adding a screen. The
files, colours and type are in [`frontend/brand/README.md`](../frontend/brand/README.md); this
page is the why and the rules.

## The direction: Slate, plus a wordmark

Chosen 19 Nov 2026 after four rounds of mockups. The brief was **modern and minimal, friendly,
with a tinge of quiet luxury**. Stripe was the reference for craft, not for copying.

- A cool slate page, white cards with soft layered shadows, navy ink.
- One warm note: a muted brass, used only for small marks. The wordmark's full stop is the
  whole brand accent. It says "done, checked".
- Schibsted Grotesk 600 for headings and amounts, Hanken Grotesk for text.
- Corners of 8 to 16 px, never pills for buttons.
- The moments that matter are **the checkout and the website hero**. Spend polish there first.

What we learnt choosing it: each extra ingredient (engraving, metal, leather trim, serif
headlines) made it worse. Luxury here comes from restraint. **Add one thing at a time, and take
things away before adding new ones.**

## Do not use (reads as template or AI-generated)

- Dark hero with a grid, glow or gradient blobs
- A pill "eyebrow" with a coloured dot above the headline
- One word of the headline in the accent colour
- Rows of identical icon cards (three or six of them)
- UPPERCASE tracked labels above every section
- "Trusted by" or "Built with" logo strips
- Fake browser chrome or macOS window dots around screenshots and code
- Space Grotesk + Inter, pill buttons, monospace used as decoration
- Invented numbers. Every figure on the site is measured (`frontend/website/src/content/site.ts`)

## Rules for product screens

- **Checkout:** the merchant and amount lead. One primary action (Pay). Cancel is a text link,
  not a second button. While paying, the button shows the three-segment brass Pay meter and
  "Processing…". Motion respects `prefers-reduced-motion`.
- **Dashboard:** a work tool. Mist canvas, white tables, navy headings. The menu is grouped into
  Payments, Fraud and Admin. No decorative colour; colour means a status.
- **Emails and receipts:** navy header with the wordmark, a thin brass rule, the Test mode
  badge, white body.
- **Status colours** (allow, verify, block) are for screening outcomes and statuses only.
- **Accessibility:** every text pair passes WCAG AA; brass is never text on white. Keep the
  axe scan at 0 issues (`tests/a11y/`).
- **Copy:** plain, specific, and true. Say what the system does and what was measured. Keep the
  student-project disclaimer on the website and the Test mode badge everywhere.

## Prompt for an AI assistant

When asking an assistant for a new screen, give it this page and say:

> Build this in the SecurePay Slate style from docs/BRAND.md. Use only the tokens in
> frontend/brand/tokens.json. Start from the closest existing screen and change as little as
> possible. Avoid everything in the "Do not use" list. Before you finish, list anything you
> added that is not already used elsewhere in the app, and remove it unless it is needed.

## The demo store, Volt & Co.

Volt & Co. is a fictional merchant, so it does not use the SecurePay look: warm paper
(`#FBFAF7`), graphite ink, one orange (`#E8692A`) for the ampersand in its name and small
details in the product drawings, 6 px corners, system fonts. The same "do not use" list
applies. Its styles live in `merchant/apps/shop/templates/shop/base.html` and the drawings'
colours in `merchant/apps/shop/templatetags/shop.py`.
