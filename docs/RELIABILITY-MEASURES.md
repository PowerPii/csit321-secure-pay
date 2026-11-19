# Reliability measures: what shoppers and merchants experienced

Uptime says whether each part answered. These three measures say whether **payments**
worked, which is what a user notices (Google SRE Workbook, "Implementing SLOs"; Codex
completion audit, 19 Nov 2026, section 4). They reuse what the gateway already records;
nothing extra is measured.

Where to read them:

- `GET /status.json` on the gateway, field `measures` (the public status page's data; counts
  only, no IDs, amounts or emails), recomputed at most once a minute;
- the public status page (`www.<domain>/status`, section "What payments experienced"), which
  shows each number with what it is out of, its window and its environment
  (`frontend/website/src/components/StatusMeasures.tsx`). Fewer than 20 timed payments: it
  shows the median, not the p95;
- `python manage.py reliability_report [--hours 168] [--json]` on the server, for slides
  and the M6 report. It prints each number with its population, window and environment.

Code: `gateway/apps/status/measures.py`. Tests: `gateway/apps/status/test_measures.py`.

## Common to all three

| | |
| --- | --- |
| **Environment** | The gateway named in `STATUS_GATEWAY_URL` (the public server: `gateway.securepaysg.me`), or "local stack". Quote it with every number; laptop and server runs are never mixed. |
| **Population** | Every payment on that gateway whose card was submitted in the window. All of it is simulated: demo runs, rehearsals, `demo.sh traffic`, integration tests. Say so on a slide. |
| **Window** | The last 24 hours by default (`--hours` to change), ending when the report runs. |

## 1. Checkout time

| | |
| --- | --- |
| **Measures** | Server-side time from card submission (`Payment.submitted_at`) to the bank's approval (`authorised_at`). |
| **Denominator** | Payments submitted in the window, approved, and **screened `allow`** (no verification step). |
| **Left out, and why** | Payments that needed a code: their time is mostly the customer reading an email. Declines and blocks: they have no approval time. |
| **Reported as** | p50 and p95 in ms (nearest rank) and the count. Fewer than 20 payments: quote the count, not the p95. |
| **Not included** | Browser and network time before the request reaches the gateway. The load test (`tests/load`) measured the HTTP round trip separately: p95 195.6 ms over 12,000 responses at 20 payments/s (19 Nov 2026 audit, laptop). |

## 2. Definite answers

| | |
| --- | --- |
| **Measures** | Share of eligible payments that reached an **expected final state**. |
| **Numerator** | Approved (authorised, captured, or later cancelled), declined by the bank (`card_declined`), or **blocked on purpose**: fraud rules, the fraud model, a failed or expired verification code, the amount limit. |
| **Denominator (eligible)** | Payments submitted in the window, minus those **still waiting for the customer's code**, minus those submitted in the **last 10 minutes** (still settling). Both left-out counts are reported. |
| **Counted against** | Blocked because **screening was unavailable** (see 3), declined `not_processed` (the network never got the request), and anything still screening, processing or unresolved after 10 minutes. |
| **Annotation** | The report lists expected blocks separately: a run with many risk-test cards has many blocks, and they are answers, not failures. |

## 3. Screening unavailable (shown on its own)

A payment blocked because screening gave no decision (model unavailable, or over the 500 ms
timeout; FR-FRD-04, NFR-PER-02)
gets a fast, well-formed HTTP 200 and a clear message, so latency and error-rate graphs look
healthy. It is still no decision. It counts against measure 2 and is printed as its own line,
so a fast failure cannot hide inside a good p95.

## 4. Oldest outstanding work

| | |
| --- | --- |
| **Measures** | Age of the oldest card-network call (`Operation`) still `pending` or `unresolved`, and of the oldest merchant webhook still waiting to be delivered, with how many of each. |
| **Window** | None: it is the state now. |
| **Bound** | Reconciliation settles or escalates a call within about 38.5 minutes; NFR-AVA-03 allows 60. `manage.py recovery_check` warns from 40 and fails from 60. |

## Quoting a number

Write it the way the report prints it, for example:

> 412 of 418 eligible payments (98.6 %) got a definite answer, gateway.securepaysg.me,
> 24 hours to 20 Feb 2027 18:00 SGT, simulated demo traffic; 6 blocked because screening
> was unavailable; 3 waiting for a code and 2 too recent were left out.

(Illustrative wording only: run the report for the real figures.)
