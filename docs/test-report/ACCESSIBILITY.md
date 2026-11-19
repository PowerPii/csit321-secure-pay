# Accessibility and mobile pass (18 November 2026)

Checked against WCAG 2.2 level A and AA: the hosted checkout (card form, verification code,
all results), the guest status check, the customer account pages, the staff dashboard (sign-in,
code page, all 16 menu pages and payment detail, as merchant operator, fraud analyst and
administrator) and the Volt & Co. demo shop.
It is the evidence for **NFR-USE-01** (phone width, plain messages) and **NFR-USE-02**
(accessibility scan, keyboard only, labelled fields), checks M-USE-01 and M-USE-02 in
`MANUAL-TESTS.md`.

## How it was checked

| Check | Tool | Where |
| --- | --- | --- |
| Automated scan, WCAG 2.2 A/AA + best practice | axe-core 4.10 (the engine of the axe DevTools extension) in Chromium | Live server (before) and a local copy of the stack running this branch (after) |
| Phone width | Chromium at 320 px, 360 px and 1280 px; page width compared with the window | Same |
| Keyboard only | Scripted Tab, Shift+Tab, Enter, Space, arrow keys; focus checked after each step | Same |
| Screen readers | Roles, names, live regions and focus moves read from the accessibility tree; no screen-reader session with a person | Same |
| Contrast | axe colour-contrast rule plus the theme colours worked out by hand | Same |
| Every push | axe-core inside the vitest suites of the checkout and the dashboard (CI) | `frontend/checkout/src/A11y.test.tsx`; `expectAccessible()` in 15 dashboard page tests |

Re-run against any server with `tests/a11y/scan.mjs` (instructions at the top of the file).
It scans the shop, every customer page at 320 and 1280 px, pays once by keyboard at each
width and, with a staff sign-in, every dashboard page.

## What was found and fixed

Before: the live server and a local copy of the stack on 18 Nov 2026. After: this branch on
the local copy, every page listed above.

| # | Problem | WCAG | Where | Fix |
| --- | --- | --- | --- | --- |
| 1 | Most rows in the dashboard tables (overview, fraud review, fraud alerts, security alerts) opened only with a mouse click | 2.1.1 (A) | Dashboard | The reference in each row is now a button: Tab to it, Enter opens the payment, case or alert. Looks like plain text until hovered or focused |
| 2 | Wide tables that scroll sideways on phones could not be scrolled by keyboard | 2.1.1 (A) | Dashboard, 7 pages | Scrolling tables take focus (arrow keys scroll them) |
| 3 | The paid page sent the customer back to the shop after 5 s with no way to stop it | 2.2.1 (A) | Checkout | "Stay on this page" link next to the countdown |
| 4 | The whole step panel was a live region, so screen readers re-read the session countdown every second | 4.1.3 (AA) | Checkout, guest status | Live region removed; when the step changes (checking, code, result) focus moves to the new heading so it is read once |
| 5 | Field errors were not tied to their fields (no `aria-invalid`, not in `aria-describedby`); after a failed submit focus stayed on the button | 3.3.1 (A), 4.1.2 (A) | Checkout, guest status, account | Every error is linked to its field and marked invalid; focus moves to the first field with an error. The shop already did this (Django 5.2) |
| 6 | Card form, phone sign-in page had no page heading | 1.3.1 (A), 2.4.6 | Checkout, account | Screen-reader heading on the card form ("Pay S$ … to … by card"); the sign-in intro and its heading stay for screen readers on phones |
| 7 | Sign-in / Register tabs on phones were not linked to their panels and ignored arrow keys | 4.1.2 (A) | Account | `aria-controls`, `tabpanel`, arrow keys, one tab stop |
| 8 | Keyboard focus ring was saffron on white (2.0:1) on checkout inputs and teal (2.5:1) in the shop | 1.4.11 (AA), 2.4.7 (AA) | Checkout, shop | Navy ring (15:1) with the saffron halo kept; shop ring in its darker teal (5.5:1); visible ring on every button and link |
| 9 | Red text buttons ("Deactivate") were 4.3:1 on white | 1.4.3 (AA) | Dashboard | Theme red #D9434B to #C2333B (5.5:1); same for the alert count badge |
| 10 | Headings skipped levels (page title h1, then card titles as h6); the "SecurePay" word mark and number tiles were headings | 1.3.1 (A) | Dashboard, 48 page views | Card titles are h2; word mark and tile numbers are plain text |
| 11 | Action columns had empty table headers | 1.3.1 (A) | Dashboard, 7 tables | Header "Actions" for screen readers |
| 12 | `role="status"` on the new-alert links was invalid and announced nothing reliable | 4.1.2 (A) | Dashboard | A hidden live region always on the page announces the unread fraud and open security alert counts; the sidebar links say the count too |
| 13 | No way to skip the navigation; after moving to another page focus stayed on the old link | 2.4.1 (A), 2.4.3 (A) | Dashboard, shop | "Skip to content" link (shows on Tab); focus moves to the new page's content after navigation |
| 14 | Content outside landmarks (sidebar, top bar, shop demo banner, dashboard sign-in) | 1.3.1 (best practice) | Dashboard, shop | `aside`, `header` and `main` landmarks |
| 15 | The overview chart's daily numbers were only in hover tooltips | 1.1.1 (A) | Dashboard | The numbers are also in a table for screen readers |
| 16 | Pages wider than the phone: payment detail timeline (214 px too wide at 360), integrity (26 px), cart (5 px at 320) | 1.4.10 (AA) | Dashboard, shop | Long request IDs wrap, tables scroll inside their box, grid columns may shrink |
| 17 | Top bar wrapped the "Test mode" pill onto two lines at 320 px | 1.4.10 (AA) | Checkout | Pill stays on one line; status text right-aligned |
| 18 | Sticky shop header could cover the focused element when tabbing back up | 2.4.11 (AA) | Shop | Scroll padding under the header |

No colour, layout or wording visible to a mouse user changed apart from the "Stay on this
page" link, the darker red (#9) and the navy focus ring (#8).

## Results after the fixes

| Check | Result |
| --- | --- |
| axe, customer pages: card form, card form with errors, verification code (and with error), approved, declined, being checked, invalid link, guest status (and with errors), account sign-in, at 320 and 1280 px | 0 violations on all 22 scans |
| axe, dashboard: sign-in, code page, 16 menu pages and payment detail; administrator at 360 and 1280 px, merchant operator and fraud analyst at 1280 px | 0 violations on all 76 scans |
| Sideways scrolling | None on any page at 320 px (customer) or 360 px (dashboard) |
| Keyboard-only payment | Tab reaches Pay; an empty submit puts focus on the first error; the payment completes by keyboard; focus lands on "Payment successful"; "Stay on this page" stops the return. Same at 320 px |
| Keyboard-only dashboard | Sign-in, 6-digit code and Enter; "Skip to content"; open a payment, a fraud case and an alert from their tables. Same at 360 px |
| Form labels | Every field on every page has a label (axe `label` rule, plus the checks above) |

### Customer messages (NFR-USE-01 checklist)

Each message states the outcome, states the next step, shows no card number and shows no
technical detail; all pass.

| Message | Outcome | Next step | No card no. | No tech. detail |
| --- | --- | --- | --- | --- |
| Payment successful: "S$ … paid to …", receipt on its way | ✓ | ✓ return to shop | ✓ (brand and last 4 only) | ✓ |
| Payment declined: "Your bank declined this payment. No money was taken." | ✓ | ✓ try a different card | ✓ | ✓ |
| Blocked / couldn't complete: "No money was taken. If you need help, please contact …" | ✓ | ✓ | ✓ | ✓ |
| Verification failed: "…we stopped the payment to protect your card. No money was taken." | ✓ | ✓ return and try again | ✓ | ✓ |
| Being checked: "We didn't hear back from the bank in time. Please don't pay again." | ✓ | ✓ page updates, shop confirms | ✓ | ✓ |
| Screening unavailable: "No money was taken. Please try again in a few minutes" | ✓ | ✓ | ✓ | ✓ |
| Checkout ended: "This checkout has ended. No money was taken." | ✓ | ✓ start again at the shop | ✓ | ✓ |
| Code sent: "enter the 6-digit code we sent to a•••@…" | ✓ | ✓ | ✓ | ✓ |
| Wrong code: "That code isn't right. 2 attempts left." | ✓ | ✓ | ✓ | ✓ |
| Code expired: "This code has expired. Ask for a new code." | ✓ | ✓ | ✓ | ✓ |
| Guest status code: "If the details match a payment, we have emailed a 6-digit code…" | ✓ | ✓ | ✓ | ✓ |
| Guest status locked: "…locked for 15 minutes. Try again after HH:MM, or contact the shop" | ✓ | ✓ | ✓ | ✓ |
| Form errors, e.g. "Enter the expiry date as MM / YY." | ✓ | ✓ | ✓ | ✓ |

## Public website (19 November 2026, completion audit)

The 19 November audit's Chrome sweep of 12 public pages and the fallback route at 1280 and
320 px found four routes with issues. Fixed and re-scanned with axe-core 4.10 in Chromium at
both widths against a local build of the website (`vite preview`, live gateway status data):

| Route | Finding | Fix | After |
| --- | --- | --- | --- |
| /developers/api/explorer | 22 (desktop) / 18 (phone) colour-contrast: Redoc's 2xx response text and tabs in `brand.allow` (3.2:1) | Redoc `success` colour set to the darker #146C44 used by the status chips | 0 |
| /status, /privacy, /terms | link-in-text-block: links told apart by colour alone | Site-wide link default is underlined; only link lists (header, footer, "on this page") underline on hover | 0 |
| /privacy (phone) | 4 scrollable tables not reachable by keyboard | Each table's scroll area is a named, focusable region | 0 |
| Fallback (404) | No H1 | The heading is the page's H1; a "Contact the team" button was added | H1 present |
| /status (found in the re-scan with live data) | 450 aria-prohibited-attr on the uptime bars' tooltips; heading order | Tooltips describe instead of label; component names are H2 | 0 |

The explorer still has Redoc's own heading-order best-practice findings (it renders its
operation headings as h5); they are outside WCAG A/AA. Every CI run now also walks the public
site in `frontend/website/src/journey.test.tsx` (axe WCAG 2.2 A/AA without colour contrast,
which jsdom cannot compute). People testing is scripted in `FIRST-TIME-USER-SESSION.md`.

## What this does not cover

- **No session with a screen-reader user.** Names, roles, live regions and focus were
  checked in the accessibility tree; a short run with NVDA or VoiceOver before the demo
  would confirm how it sounds.
- **Scans in Chromium.** The axe scans ran in Chromium; the demo script itself was then run in
  Chrome, Firefox, WebKit and on an iPhone for NFR-USE-03 (M-USE-03, 18 Nov 2026, all pass).
- **Small text in the overview chart on phones.** The 14-day chart scales down with the
  screen, so its axis labels are small at 360 px. The same numbers are in the legend, the
  tiles and the screen-reader table.
- **Session time limits.** The checkout session (60 min), the verification code (10 min)
  and the 15-minute idle sign-out are security limits, which WCAG 2.2.1 allows; the idle
  sign-out already warns at 13 minutes with "Stay signed in".
- **Not a conformance claim.** This is a pass over the pages the demo uses, not a formal
  WCAG audit.
