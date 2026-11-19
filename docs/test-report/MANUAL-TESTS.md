# Manual checks for the non-functional requirements

These are the parts of URS Section 4.4 that the CI tests cannot prove on their own: they need
the demonstration server, a real browser or people. Everything else is automated (see
`evidence.yaml`).

**Where:** the demonstration server (Section 4.6.1), now on the Student Pack domain
`securepaysg.me` (same Google Cloud VM, since 19 Nov 2026), so the figures are measured where the demo runs. On the server, from
`~/csit321-secure-pay`:

```bash
P="docker compose -f deploy/compose.prod.yaml"
D=<the domain>                # e.g. securepay.example; today securepaysg.me (35-213-144-96.sslip.io before 19 Nov 2026)
```

**Recording a result:** add an entry under the check's ID in `manual-results.yaml` (date, who,
environment, pass or fail, the figures and where the evidence is), commit it on a branch and
open a pull request. CI rebuilds the report with it. A fail is recorded too, with what was
fixed; then the check is run again.

**Who:** any team member, except where a check says otherwise. Use test cards and
`@example.com` emails only. Do not run the load test or the kill test less than 48 hours
before a demo (merge freeze window, `deploy/RUNBOOK.md` 10a), and run `bash deploy/demo.sh
reset` afterwards.

| ID | Requirement | What | Time |
| --- | --- | --- | --- |
| M-CON-02 | NFR-CON-02 | Scan the live logs and exports for card numbers | 10 min |
| M-CON-04 | NFR-CON-04 | Inspect the live user tables for Argon2id hashes | 5 min |
| M-CON-06 | NFR-CON-06 | Idle sign-out on the account pages and dashboard | 35 min (mostly waiting) |
| M-AVA-01 | NFR-AVA-01 | Kill the gateway 5 times under traffic | 30 min |
| M-AVA-05 | NFR-AVA-05 | Backup schedule on the server, then the restore check | 10 min |
| M-ENC-01 | NFR-ENC-01 | TLS scan of every public name | 15 min |
| M-ENC-02 | NFR-ENC-02 | Inspect the live vault after a test run | 5 min |
| M-ENC-03 | NFR-ENC-03 | Rotate the keys on the live server, read the key report | 10 min |
| M-PRI-01 | NFR-PRI-01 | Review the live logs for unmasked emails and phone numbers | 10 min |
| M-PRI-02 | NFR-PRI-02 | Card data checklist, by someone who did not build the vault | 20 min |
| M-PER-01 | NFR-PER-01 | Checkout load test, 20 payments per second for 5 minutes | 30 min |
| M-PER-02 | NFR-PER-02 | Screening benchmark, 1,000 payments | 10 min |
| M-PER-03 | NFR-PER-03 | 20 alerts timed on the dashboard | 15 min |
| M-USE-01 | NFR-USE-01 | Checkout at 360 px and the message checklist | 30 min |
| M-USE-02 | NFR-USE-02 | Accessibility scan and keyboard-only run | 30 min |
| M-USE-03 | NFR-USE-03 | Demo script in Chrome, Firefox and a phone browser | 45 min |
| M-USE-04 | NFR-USE-04 | Stakeholder walkthroughs, 5 participants (task 11.5) | 2 to 3 h |
| M-AUD-01 | NFR-AUD-01 | Trace 20 sampled payments in the dashboard | 30 min |
| M-MNT-01 | NFR-MNT-01 | Pipeline inspection and branch protection | 10 min |
| M-MNT-02 | NFR-MNT-02 | The gateway's database role cannot read the card table | 5 min |
| M-MNT-03 | NFR-MNT-03 | Pipeline inspection: dependency and code audits fail the run | 10 min |

---

## M-CON-02: no card numbers in live logs and exports

After a run of the demo script (or `bash deploy/demo.sh preflight`):

```bash
$P logs --no-color --since 24h > /tmp/all.log
grep -E '\b([0-9][ -]?){13,19}\b' /tmp/all.log | python3 -c "
import re,sys
def luhn(d):
    s=0
    for i,c in enumerate(reversed(d)):
        n=int(c)
        if i%2: n=n*2-9 if n>4 else n*2
        s+=n
    return s%10==0
hits=[l for l in sys.stdin for m in re.findall(r'(?:\d[ -]?){13,19}',l) if luhn(re.sub(r'\D','',m))]
print(len(hits),'lines with a Luhn-valid number'); print(''.join(hits[:20]))"
rm /tmp/all.log
```

Then download the fraud report CSV (dashboard, Reports, Export) and the audit log page, and
search them for any 13 to 19 digit number. **Pass:** 0 lines and 0 numbers (timestamps and
IDs are not Luhn-valid card numbers; check any hit by hand).

## M-CON-04: Argon2id hashes in the live user tables

```bash
$P exec -T db psql -U gateway -d gateway -At -c "
  SELECT 'staff', count(*), count(*) FILTER (WHERE password LIKE 'argon2\$argon2id\$%'),
         count(DISTINCT split_part(password, '\$', 5)) FROM auth_user
  UNION ALL
  SELECT 'customer', count(*), count(*) FILTER (WHERE password LIKE 'argon2\$argon2id\$%'),
         count(DISTINCT split_part(password, '\$', 5)) FROM customers_customeraccount;"
```

Then try to register at `https://gateway.$D/account/register` with an 11-character password.
**Pass:** on each row the three counts are equal (every hash is Argon2id and every salt is
different), and the registration is refused.

## M-CON-06: idle sign-out

1. Sign in at `https://gateway.$D/account/sign-in` as a demo customer; leave the tab alone.
   Note the time the warning appears and the time the page signs out.
2. Copy the `sp_customer` cookie value first (browser developer tools), and after the sign-out
   send it again: `curl -s -o /dev/null -w '%{http_code}' -H "Cookie: sp_customer=<value>"
   https://gateway.$D/customer/me`.
3. Repeat steps 1 and 2 on the dashboard (`/dashboard/`, cookie `sessionid`, URL
   `/internal/me`).

**Pass:** warning at 13 minutes (plus or minus 1), sign-out at 15, and both curls answer 401.

## M-AVA-01: kill the gateway 5 times under traffic

Needs the load script (M-PER-01) for steady traffic, at a gentle rate:

```bash
python3 tests/load/checkout_load.py --gateway https://gateway.$D --key-file deploy/secrets/securepay_api_key \
    --rate 2 --seconds 600 --out /tmp/kill-run.json &
for i in 1 2 3 4 5; do
  sleep 90
  date +%T
  # The gateway's main process dies as in a crash (a plain `docker kill` counts as a manual
  # stop, and Docker would not restart it).
  sudo kill -9 "$(docker inspect -f '{{.State.Pid}}' "$($P ps -q gateway)")"
  start=$(date +%s)
  until curl -fsS https://gateway.$D/readyz >/dev/null 2>&1; do sleep 1; done
  echo "back after $(( $(date +%s) - start )) s"
done
wait
```

Docker restarts the crashed container (`restart: unless-stopped`). After the run, open the
dashboard Payments list filtered to "Unresolved" and wait until it is empty (the worker
reconciles within about 40 minutes; an administrator can press Recheck). Then compare
gateway and simulator records:

```bash
$P exec -T db psql -U gateway -d gateway -At -c "SELECT count(*) FROM payments_operation WHERE type='authorise' AND status='succeeded'"
$P exec -T db psql -U simulator -d simulator -At -c "SELECT count(*) FROM operations_operation WHERE type='authorise' AND status='approved'"
```

Run it on a disposable copy of the stack, never on the live server. The 19 Nov 2026 run used
the local stack with production settings; its scripts are in
`evidence/2026-11-19-local/scripts/` (`ava01.sh` for the kills, `ava01_reconcile.py`, which
matches every authorise on the gateway with the simulator's record by operation ID).

**Pass:** each of the 5 restarts answers `/readyz` within 30 s, no payment stays unresolved
or is escalated without a final answer, and the two counts match for the run's merchant
(no payment missing on either side and none processed twice). Record the 5 restart times.

## M-AVA-05: nightly backups and the weekly restore check

On the server:

```bash
crontab -l | grep -E 'backup/(backup|verify)\.sh'   # nightly backup.sh, weekly verify.sh
ls -1 ~/fyp-backups | tail -n 16                       # dated folders, none older than 14 days
bash deploy/backup/verify.sh                           # the restore check, on the newest backup
```

`verify.sh` checks the newest complete backup against its MANIFEST checksums, restores each
of the three dumps into a scratch database (`restorecheck_*`), counts tables and rows, checks
that the vault table is present and empty (no card data in backups) and drops the scratch
databases. The live databases are not touched. Backups made before 19 Nov 2026 have no
MANIFEST and fail by design: run `backup.sh` once first. The full drill (restore over the
local databases with a checkout in flight) is the opt-in integration test
`RECOVERY_DRILL=1 pytest tests/integration/test_recovery_drill.py`, on a laptop stack only.

**Pass:** both cron lines are there, the backup folders cover at most the last 14 days, and
`verify.sh` ends with `Backup ... restores.` (exit 0).

## M-ENC-01: TLS scan

From a laptop on an ordinary network (not the server, and not behind a proxy that inspects TLS,
or you measure the proxy):

```bash
bash tests/tls/check-tls.sh securepaysg.me | tee docs/test-report/evidence/$(date +%F)-tls.txt
```

It covers every external entry point: `gateway.`, `shop.` and `mail.` on the Google Cloud VM
(TLS 1.0 and 1.1 must be refused, TLS 1.2 and 1.3 offered, each TLS 1.2 cipher suite tried one
by one and only ECDHE with AES-GCM or ChaCha20-Poly1305 allowed, plain HTTP must answer 301 or
308 to HTTPS, HSTS shown), the website on Vercel (`securepaysg.me` and `www.`), and port 8443
(the private simulator hop, which must not answer from outside). It needs only bash, openssl
and curl, and runs testssl.sh as well if it is installed:

```bash
for host in gateway shop mail; do ./testssl.sh --quiet --protocols --ciphers --severity HIGH "https://$host.$D"; done
```

If the network in between intercepts TLS (an ISP or company filter, an antivirus web shield), the
certificates come from that filter instead of Let's Encrypt and plain HTTP may be redirected to
its block page. The script then ends with `INVALID` (exit 2): record nothing and run it again
from another network, or from the server's own shell (as on 19 Nov 2026).

**Pass:** the script ends with `PASS` (only TLS 1.2 and 1.3, no weak suite, every plain-HTTP
request redirected). Save the output. The same script against the local stack
(`bash tests/tls/check-tls.sh localhost`) checks the Caddy build before a deploy; the result of
19 Nov 2026 is in `evidence/2026-11-19-local/m-enc-01-local-caddy-tls.txt`.

## M-ENC-02: the live vault after a test run

After `bash deploy/demo.sh preflight` (or a demo run):

```bash
$P exec -T db psql -U vault -d gateway -At -c "
  SELECT count(*), count(*) FILTER (WHERE expires_at < now()) FROM vault.vault_storedcard;"
$P exec -T db psql -U gateway -d gateway -At -c "
  SELECT count(*) FROM payments_payment WHERE submitted_at IS NOT NULL AND card_token <> ''
  AND card_token IN (SELECT token FROM vault.vault_storedcard);" 2>&1 | tail -1
```

**Pass:** the first query shows 0 expired rows (any row left belongs to a checkout still open
in a browser) and none of them is for a submitted payment; the second query is refused (the
gateway role cannot read the vault, M-MNT-02) or returns 0. The dashboard Integrity page
self-check "No card data after submission" shows passed.

## M-ENC-03: key rotation on the live server

As an administrator on the dashboard Integrity page: rotate the field key and the vault key
(needs the authenticator code). Then open a payment made before the rotation, a merchant's
settings and the guest status of an older payment.

**Pass:** the rotation reports 0 failed re-encryptions, everything opens normally, and the
key report on the same page shows no active key older than 90 days.

## M-PRI-01: log review for personal data

```bash
$P logs --no-color --since 24h | grep -Eio '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}|\+?65[ -]?[0-9]{4}[ -]?[0-9]{4}' | sort | uniq -c | head -50
```

**Pass:** every email address shows masked (`a•••@example.com` style) and no phone number
appears. The 12-month clean-up itself is covered by the CI test; check the dashboard Integrity
page shows the daily clean-up ran in the last 24 hours.

## M-PRI-02: card data checklist (independent reviewer)

**Who:** a team member who did not build the vault (not the vault's author per `git log --
gateway/apps/vault`). Check each item on the running system and note how:

1. HTTPS enforced on every public name (M-ENC-01 result, or `curl -sI http://gateway.$D`).
2. No card number or security code after submission (M-ENC-02).
3. Card numbers masked to brand and last 4 on the checkout result, dashboard, emails and
   receipt PDF (look at one of each).
4. No active key older than 90 days (Integrity page key report).
5. Every staff account uses MFA (sign in as each role; Integrity self-check "Staff MFA").

**Pass:** all 5 items pass and agree with the self-check results on the Integrity page (UC-46).

## M-PER-01: checkout load test

The API key limit (100 per minute) and the per-browser limit (60 per minute) would refuse
most of the load, so raise both for the test only, then put them back:

1. Dashboard, Limits (administrator): API rate limit per key 2000, per IP 4000.
2. In `deploy/.env` add `THROTTLE_ANON=6000/min`, then `$P up -d gateway`. The gateway
   container must be **Recreated**, not just "Running" (`compose.prod.yaml` passes
   `THROTTLE_ANON` through since 20 Nov 2026; before that the line had no effect and the
   first live run on 20 Nov got 5,921 HTTP 429 replies).
3. From a laptop on a good connection (or from the server itself, which leaves out the
   internet link; say which in the result):

   ```bash
   pip install httpx
   python3 tests/load/checkout_load.py --gateway https://gateway.$D \
       --key-file deploy/secrets/securepay_api_key --rate 20 --seconds 300 --out /tmp/per-01.json
   ```

4. Undo steps 1 and 2 (`THROTTLE_ANON` line removed, `$P up -d gateway`), then
   `bash deploy/demo.sh reset`.

The script pays with fresh demo-range cards (approved at once by the simulator, so its delay
is close to 0) and times the card entry and submit calls the checkout page makes.
**Pass:** the script prints `PASS` (exit status 0): the 95th percentile of checkout responses
is at most 2 s, the rate was held, no request was refused with 429, and under 1% of payments
ended other than authorised. Attach `/tmp/per-01.json`.

Through Caddy every payment comes from the one machine running the script, so fraud screening
counts them all as one customer's attempts from one address (thousands an hour), which real
traffic never does and which slows screening as the run goes on. Say so in the result. A local
run straight to gunicorn with `TRUSTED_PROXY_HOPS=1` can add `--spread-ips` to give each payment
its own address. Reference run, 18 Nov 2026 (cloud container, 4 vCPU, gateway with 3 workers,
trained model, no Caddy): 6,000 payments at 20/s, p95 110 ms from one address and 89 ms with
`--spread-ips`, all authorised (before the checkout lock fix: p95 above 2 s, rate not held).

## M-PER-02: screening benchmark

```bash
$P exec -T gateway python manage.py benchmark_screening --payments 1000
$P exec -T gateway python manage.py loadtest_screening --rate 20 --seconds 60
```

**Pass:** p95 screening time at most 200 ms (including history features) in both, and the
benchmark reports every request over 500 ms as blocked "screening unavailable" (normally
none). Record the p50, p95 and max.

A fast run has no request over 500 ms, so it cannot show the timeout branch. Show it on a
disposable stack: hold a lock on the risk-list table that the rules read, then pay. The 500 ms
statement timeout cuts the screening query off and the payment must end Blocked with
`screening_unavailable`; a payment after the lock ends is authorised as normal.

```bash
$P exec -T db psql -U postgres -d gateway -c \
  "BEGIN; LOCK TABLE risk_risklistentry IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(12); COMMIT;" &
# within those 12 s: pay in the shop (or evidence/2026-11-19-local/scripts/per02_timeout.py)
```

## M-PER-03: alerts reach the dashboard within 10 seconds

Sign in as an analyst on one screen, Alerts page open. On another device pay 20 times in the
shop with the email `blocked@example.com` (each is blocked and raises an alert). Note the
time of each payment's result and of its alert appearing (screen recording is easiest).

**Pass:** all 20 alerts appear within 10 s of the payment's result. Also lock a staff account
(5 wrong passwords) and check the administrator's Security alerts page within 10 s.

## M-USE-01: phone width and plain messages

1. Browser developer tools, device toolbar at 360 px wide. Complete a payment in the shop and
   on the checkout page; check for horizontal scrolling on every step (card form, code,
   result, guest status, account pages).
2. Trigger each customer-facing message: approved, declined (`4000 0000 0000 0002`),
   blocked, verification code (order over S$500), wrong code, expired session, being checked
   (`4000 0000 0000 0119`), guest status code, locked status check. For each, check: states
   the outcome; states the next step; shows no card number; shows no technical detail.

**Pass:** no horizontal scroll at 360 px, and no message fails a checklist item. Record the
messages checked in a table (message, 4 ticks).

Step 1 can be scripted: `tests/a11y/scan.mjs` measures sideways scrolling on every customer
page at 320 px and 1280 px. The message table from 18 Nov 2026 is in `ACCESSIBILITY.md`.

## M-USE-02: accessibility

With the axe DevTools browser extension (free), scan: checkout card form, verification code,
result, guest status (find, code, view). Then complete each page with the keyboard only (Tab,
Shift+Tab, Enter, Space).

**Pass:** 0 critical issues on every page, every page completed by keyboard alone, and every
form field has a label. Save the axe results (export) as evidence.

Or run `tests/a11y/scan.mjs` against the server (same axe engine, every customer page at 320
and 1280 px, one keyboard-only payment, the dashboard with a staff sign-in); keep its
`a11y-results.json`. Findings, fixes and limits of the 18 Nov 2026 pass: `ACCESSIBILITY.md`.

## M-USE-03: cross-browser demo script

Run the demo script (the 8 scenes on the demo-day cheat sheet, `docs/DEMO-DAY.md`) in current Chrome and Firefox on a
desktop, and the customer scenes (2 and 3) plus the dashboard overview in one mobile browser
(Safari on iPhone or Chrome on Android). The integration suite run (stack) adds the API side.

**Pass:** every step works in all three; note the browser versions.

`tests/browsers/demo-script.mjs` plays the customer scenes (1 to 5) in Playwright's Chromium,
Firefox and WebKit (Safari's engine) and in the installed Chrome (`BROWSERS=chrome,...`), then
scenes 2 and 3 at iPhone and Pixel sizes; instructions at the top of the file. It makes fresh
demo cards, so screening history does not build up. What stays by hand: the dashboard scenes
(6 and 7), the scene 3 code unless `MAILPIT_USER`/`MAILPIT_PASS` are set, a browser
Playwright cannot start (its Firefox build does not start on macOS 27: use the real Firefox),
and the real phone.

## M-USE-04: stakeholder walkthroughs (task 11.5)

Five participants who are not on the team. Show them each result page in turn (authorised,
declined, blocked, being checked) without explaining. Ask: "Have you been charged?" and
"What would you do next?". Record answers per participant and result.

**Pass:** for each of the four results, at least 4 of 5 participants answer both questions
correctly. Keep the answer sheet (no names needed; P1 to P5).

## M-AUD-01: trace 20 payments

Pick 20 payments covering every outcome (authorised, captured, partly refunded, refunded,
declined, blocked, verified by code, reconciled after a lost reply, cancelled, expired).
For each, open its page in the dashboard as an administrator.

**Pass:** each timeline shows, under one correlation ID, the screening decision, every
processing operation, every refund, every webhook attempt and the related audit entries,
with nothing missing (compare with the audit log filtered by the payment ID).

## M-MNT-01: pipeline inspection

1. Open the latest pull request: the `ci` workflow ran the tests for the parts the change
   touches (the run's summary lists them) and the `ci-ok` job built the test report.
2. Repository settings, Branches: `main` requires a pull request and the status check
   `ci-ok` (green only when every CI job that had to run passed). This needs GitHub Pro (Student Pack)
   on a private repository.

**Pass:** both true. Until branch protection is on, record it as **fail** with the reason
(the team rule is still "merge only with green CI", but the URS asks that main refuses it).

## M-MNT-02: the gateway's database role cannot read cards

```bash
$P exec -T db psql -U gateway -d gateway -c "SELECT count(*) FROM vault.vault_storedcard;"
```

**Pass:** `permission denied for schema vault`. The import half of the requirement is the CI
test `test_nfr_mnt_02_only_the_vault_touches_card_data`.

## M-MNT-03: dependency and code audits fail the run

1. In `.github/ci-python.sh` (run by the `python` job for each Python service on every pull
   request that touches it): `pip-audit -r requirements.lock` and `bandit -r apps` run under
   `set -euo pipefail`, so a finding fails the job.
2. In `.github/ci-frontend.sh` (job `frontend`, for checkout, dashboard, website and the SDK):
   `npm audit --audit-level=high --omit=dev` (the SDK, which has no runtime dependencies,
   audits its build tools) under `set -euo pipefail`.
3. `ci-ok` is red when either job fails.

**Pass:** all three true on `main`, and the latest run of both scripts (in Actions, or locally
while Actions minutes are used up) shows the audits running and passing.
