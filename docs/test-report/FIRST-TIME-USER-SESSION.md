# First-time user session: script for the team (completion audit, 19 November 2026)

The audit's "done when" for section 3 needs people, not code: **a first-time user can find
the quickstart, finish verification using a keyboard, read the confirmation, and locate the
same payment from its receipt on a phone, while a second person observes where they hesitate.**
This is the script. About 30 minutes per participant. Run it with two or three people who have
not worked on SecurePay (a classmate, a friend); include a screen-reader user if one is willing.
Guidance: [W3C, Involving users in evaluating web accessibility](https://www.w3.org/WAI/test-evaluate/involving-users/).

## Roles

- **Facilitator** (one teammate): reads the tasks aloud, word for word, and does not help.
  If the participant is stuck for two minutes, say "What would you try next?" once; after
  another minute, note "assisted" and show them the next step.
- **Observer** (a second teammate): writes down, with the time, every pause longer than about
  five seconds, every wrong click, every "hmm" or question, and the words the participant uses.
  The observer never speaks.

## Before the session (facilitator, 10 minutes)

1. Restock the shop (`manage.py restock`, see `docs/DEMO-DAY.md`) and check https://www.securepaysg.me/status says
   "All systems operational" (not "Checking status", "Some parts have no recent check" or
   "Status may be out of date"; if so, fix the server first).
2. Use an email address the participant can open on their own phone (their own, or a team
   inbox they are signed in to). Do not use `@example.com`: those stay in the demo inbox.
3. Have a laptop with a fresh browser profile (no saved logins) and the participant's phone.
4. Ask for consent: "We're testing the website, not you. We'll write notes but record no
   video and no personal details beyond a first name. You can stop at any time."
   Never record card numbers, codes, reset links or the participant's email in the notes.

## Tasks (read aloud exactly)

**Task 1. Developer quickstart (laptop, mouse allowed).**
"You're a developer who wants to try SecurePay. Starting from www.securepaysg.me, find the
code you'd use to create your first payment."
- Success: they reach the Quickstart on /developers.
- Note: which link they took, how long it took, anything they read twice.

**Task 2. Pay with the keyboard only (laptop; put the mouse and trackpad out of reach).**
"Now be a shopper. In the Volt & Co. demo shop, buy something that costs more than S$500,
using test card 4242 4242 4242 4242, any future expiry and any 3 digits. Use only the
keyboard. Use the email address we agreed."
- An order over S$500 asks for a 6-digit code by email: this is the verification step.
- Success: they type the code from their email and reach "Payment successful" without the mouse.
- Note: where focus was lost or unclear, whether they found the code email, whether they
  understood why they were asked for a code.

**Task 3. Read the confirmation.**
"Tell me in your own words what just happened, and what you would keep in case something goes
wrong."
- Success: they say the payment went through and name the **payment reference** (`SP-...`).
- Note: whether they mention the order number instead, or the receipt email.

**Task 4. Find the same payment from the receipt, on the phone.**
"Later, on your phone, you want to check this payment. Use the receipt email."
- Success: from the receipt's link they reach the guest status page, enter the code and see the
  same `SP-...` reference marked "Paid".
- Note: zooming, sideways scrolling, mistyped references, anything that read as an error.

**Task 5 (team member as merchant, participant watches).**
The facilitator signs in to the dashboard as the Volt & Co. operator, types the reference the
participant reads out (however they say it, for example lower case without dashes) into the
Payments search, captures the payment and refunds S$1. Ask: "Is this the payment you made?"
- Success: one search finds it; the participant recognises the amount and reference.
- After the refund, the participant opens the refund receipt: it shows an `RF-...` refund
  reference and the same `SP-...` payment reference.

## After each session (observer, 10 minutes)

Fill one row per participant in the results table and keep the raw notes with the team, not
in the repository. Record the scope honestly: devices, browsers, assistive technology used,
which tasks were assisted, and what was not tested.

| Participant (first name or P1) | Device / browser / assistive tech | Task 1 | Task 2 | Task 3 | Task 4 | Task 5 | Longest hesitation (where, how long) | Words they used that we don't |
|---|---|---|---|---|---|---|---|---|
| P1 | | pass / assisted / fail, mm:ss | | | | | | |

Then, together:
1. List each hesitation seen by more than one participant. Each becomes an issue with the
   page, what the participant expected, and a proposed wording or layout change.
2. Fix the top three, then repeat only the affected task with a new participant.
3. Add a short summary (participants, scope, findings, fixes) to the M5 progress evidence
   and to `docs/test-report/ACCESSIBILITY.md` under "What this does not cover" if a
   screen-reader user could not take part.

## What the repeatable checks already cover

So the session can concentrate on people: every CI run walks home, developers quickstart,
API reference, status, privacy, terms, contact and a wrong link with an axe WCAG 2.2 scan
(`frontend/website/src/journey.test.tsx`); the checkout's suite covers keyboard focus, the
code page and every result (`frontend/checkout/src/A11y.test.tsx`); and the words on each
surface are listed in `docs/PAYMENT-LANGUAGE.md`.
