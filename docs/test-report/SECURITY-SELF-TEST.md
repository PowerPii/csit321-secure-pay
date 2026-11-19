# Security self-test, 17 to 18 November 2026

A self-test of the SecurePay stack against the OWASP Top 10 (2021) and the parts of OWASP
ASVS 4.0 level 2 that apply to it: authentication and two-step sign-in, sessions, access
control, input handling, data protection, the card vault, webhooks, configuration and secrets.
It feeds the design specification and technical manual (course M3), the progress report (M4)
and the non-functional test report (M6).

**Result: no critical or high findings.** One medium finding (rate limits counted per server
process) and five low findings were fixed in the pull request that adds this report. Two low
findings are kept as known limitations, as Fifa decided on 18 Nov 2026 (section 4). Everything else in the
checklist passed (section 5).

## 1. Scope and method

| Part | How it was tested |
| --- | --- |
| Gateway: merchant API, hosted checkout, guest status, customer accounts, staff dashboard API | Local Docker stack (`deploy/compose.yaml`) with fresh secrets, two merchants and one staff account per role; manual requests and scripts; OWASP ZAP |
| Demo shop, simulator | Local stack; code review |
| Caddy configuration (headers, TLS, routing) | Local stack, plus passive checks of the live server |
| Live server `gateway/shop/mail.35-213-144-96.sslip.io` (the names before the 19 Nov 2026 move to `securepaysg.me`; same server) | About 20 plain GET requests for headers, cookies and routing. No scanning, no sign-in, no test data |
| Repository | gitleaks over the full git history (111 commits), bandit, pip-audit (all three services); npm audit already runs in CI |

Tools: OWASP ZAP 2.17 (`zaproxy/zap-stable`): baseline scan of the dashboard, checkout page,
account pages and shop; active API scan of the merchant API (authenticated with a test API
key) and of the guest status API, both from the OpenAPI contracts. gitleaks 8.30, bandit 1.9,
pip-audit 2.10, OpenSSL 3, Playwright (Chromium) for the browser checks.

Heavy or intrusive tests (active scans, rate-limit floods, lockout, concurrency) ran only on
the local stack. Severity uses OWASP risk rating terms: likelihood and impact for this
deployment (a student demo with test cards, but built as a payment system).

## 2. Summary of findings

| ID | Finding | Severity | OWASP | Status |
| --- | --- | --- | --- | --- |
| SEC-01 | Rate limits counted separately in each gunicorn worker, so the per-key limit was about 3 times too high | Medium | A04 Insecure design / A05 | Fixed |
| SEC-02 | `Referrer-Policy: no-referrer` on the checkout, account and dashboard pages was overwritten with `same-origin` | Low | A05 Security misconfiguration | Fixed |
| SEC-03 | No Content-Security-Policy on gateway API responses or on the demo shop | Low | A05 | Fixed |
| SEC-04 | DRF's browsable HTML API was served on the public server | Low | A05 | Fixed |
| SEC-05 | Public JSON endpoints that never read a body (submit, resend, sign-out) accepted HTML form posts | Low | A01 (CSRF, defence in depth) | Fixed |
| SEC-06 | Five made-up card tokens in contract examples flagged by a full-history gitleaks scan | Info | A07 | Fixed (ignore list) |
| SEC-07 | Staff and customer sign-in said "account locked" for a real, locked account | Low | A07 Identification and authentication failures | Fixed |
| SEC-07b | Customer sign-up says "email already registered" | Low | A07 | Accepted (known limitation) |
| SEC-08 | Anyone who knows a staff email can lock that account for 15 minutes (5 wrong passwords) | Low | A07 | Accepted (known limitation) |
| SEC-09 | Webhook address is resolved for the private-address check, then resolved again for the call (DNS rebinding window) | Low | A10 SSRF | Fixed in the second pass (section 7) |
| SEC-10 | Dashboard CSP allows inline styles (`style-src 'unsafe-inline'`) | Info | A05 | Accepted (MUI needs it; no inline script allowed) |
| SEC-11 | Mailpit's 401 page names the web server (`Server: Caddy`) | Info | A05 | Accepted |

## 3. Fixed findings

### SEC-01 Rate limits were counted per process (Medium)

**What:** Django had no `CACHES` setting, so it used its default in-memory cache, one per
process. The gateway runs 3 gunicorn workers, and every DRF throttle (100 requests a minute per
API key, 300 per IP, the sign-in and email limits) and the rate-limit alert counter (UC-43)
counted in each worker separately.

**Evidence:** 330 requests with one API key within a minute on the local stack: 294 answered,
36 refused with 429. The limit is 100 (NFR-AVA-02, FR-ADM-12).

**Fix:** the cache is a table in the gateway database (`DatabaseCache`, created by migration
`security 0004`), shared by every worker and the background worker. No new service is needed
on the server. After the fix the same test answered 117 and refused 213; the small overshoot
comes from 10 requests arriving at the same instant, which a get-then-set throttle allows.
Follow-up (19 Nov 2026): the overshoot is gone. Each key's read-modify-write now runs under
a Postgres advisory lock on that key (`apps/common/throttling.py`, also the violation counter);
`apps/common/test_throttling.py` sends 24 requests at once against a limit of 5: DRF's own class
lets them all through, ours exactly 5.

### SEC-02 Referrer-Policy overwritten (Low)

**What:** the checkout, account and dashboard routes set `Referrer-Policy: no-referrer`
(password reset and verification links), but the site-wide header block, which Caddy runs last
because it also removes `Server`, replaced it with `same-origin`.

**Evidence:** live `GET /pay/...` and `/account/sign-in` answered `referrer-policy: same-origin`.

**Fix:** the site-wide value is now `?Referrer-Policy same-origin`, set only where a route did
not set its own. Checked on the local stack: those pages answer `no-referrer`, the rest
`same-origin`.

### SEC-03 Missing Content-Security-Policy (Low)

**What:** ZAP rule 10038 on every gateway response from Django (JSON, 404 pages) and on every
shop page.

**Fix:** gateway responses from Django get `default-src 'none'; frame-ancestors 'none';
base-uri 'none'; form-action 'none'` (they are JSON and PDF only). The shop gets `default-src
'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';
frame-ancestors 'none'; base-uri 'none'`: its pages have no script at all, so injected script
cannot run. Checked in Chromium: the shop pages render, and a full order (shop, checkout, back
to the order page) works with no CSP errors.

### SEC-04 Browsable API on the public server (Low)

**What:** with `Accept: text/html`, `https://gateway.<domain>/v1/payments` answered DRF's HTML
page (framework name, view names, allowed methods, a request form).

**Fix:** JSON is the only renderer unless `DJANGO_DEBUG=1`. Browsers still get JSON; receipt
PDFs and the fraud report CSV are unaffected.

### SEC-05 Form posts accepted by body-less endpoints (Low)

**What:** the customer APIs rely on "JSON only" instead of CSRF tokens (decided 13 Nov 2026),
but an endpoint that never reads its body never runs the JSON parser, so a cross-site
`application/x-www-form-urlencoded` post reached `/checkout/<id>/submit`, `/verify/resend`
and the sign-out endpoints. There was no real impact (the checkout session ID is a secret, and
the customer and guest cookies are `SameSite=Strict`), but the stated rule did not hold.

**Fix:** every unsafe request to these APIs must be `application/json`, or it gets 415 before
the view runs. New tests cover the five endpoints and three content types.

### SEC-06 Example tokens in the git history (Info)

Five `tok_...` values in `contracts/examples/` look like keys to gitleaks. They are made up;
their fingerprints are now in `.gitleaksignore`, so a full-history scan is clean.

### SEC-07 Account enumeration at sign-in (Low)

**What:** staff and customer sign-in answered `account_locked` (403) for a real, locked
account and `invalid_credentials` (401) for an unknown email, so after 5 wrong passwords an
attacker learned that the email had an account.

**Fix (agreed with Fifa, 18 Nov 2026):** the email and password step answers a locked account
exactly like a wrong password. That message already says that 5 failures lock sign-in for 15
minutes, and the staff holder is still emailed. The two-step code page, which is only reached
with the right password, still says "locked" with the minutes left.

## 4. Known limitations (kept, Fifa 18 Nov 2026)

### SEC-07b Customer sign-up says "email already registered" (Low)

Hiding it would need a "check your email to continue" sign-up flow. Customer accounts hold no
card data and sign-up is limited to 30 attempts a minute per IP, so it stays as a known
limitation.

### SEC-08 Lockout as denial of service (Low)

FR-ACC-15 locks a staff account for 15 minutes after 5 failures, and anyone who knows the email
can trigger it repeatedly. This is the usual trade-off of lockout (ASVS 2.2.1 allows it with
notification, which we do: the holder is emailed and administrators get an alert). Locking per
email and IP pair would let an attacker with many addresses keep guessing, so it stays as a
known limitation.

### SEC-09 DNS rebinding window on webhooks (Low, fixed 18 Nov 2026)

`check_endpoint` resolved the merchant's host and refused private addresses, then httpx
resolved it again for the call. A merchant controlling DNS could switch to a private address in
between. First accepted as mitigated (approved HTTPS address only, certificate must match the
host name, no redirects, reply body never read). The webhook delivery log added on 18 Nov 2026
stores and shows the start of the reply, so that last point no longer held, and the second
pass fixed it: see section 7.

## 5. Checklist results

| Area (ASVS chapter) | Check | Result |
| --- | --- | --- |
| Access control (V4) | Merchant API: another merchant's payment, refunds, capture, refund by ID | Pass: 404, same as a missing record |
| | Dashboard: operator opening, refunding or listing another merchant's payment | Pass: 404, not in list |
| | Role checks: analyst capture/refund (403), operator on admin pages (403), analyst changing rules (403), admin refund (403, operators only) | Pass |
| | Refund race: 5 parallel refunds of S$10 on a S$15 payment | Pass: 1 completed, 4 refused, no over-refund |
| | Refund amount validation (negative, 0, decimal, string, above refundable) | Pass |
| Authentication (V2) | Password only, no TOTP: dashboard API | Pass: 401 |
| | TOTP code reused in a second sign-in | Pass: refused and counted as a failure |
| | Lockout after 5 failures, right password while locked | Pass: locked, right password refused with the same reply as an unknown email (after SEC-07) |
| | Password hashing, length | Pass: Argon2, at least 12 characters, common-password check |
| Sessions (V3) | Staff session cookie | Pass: HttpOnly, Secure (live: not DEBUG), SameSite=Strict, 15 minutes idle, new key at sign-in |
| | Customer and guest cookies | Pass: HttpOnly, Secure, SameSite=Strict |
| CSRF (V4.2) | Dashboard POST without token, with a foreign Referer, sign-in without token | Pass: 403 |
| | Customer APIs with form or text bodies | Pass after SEC-05: 415 |
| Input (V5) | ZAP active scan of merchant API and guest status API (SQL injection, XSS, path traversal, command injection and others) | Pass: 0 failures, 113 and 114 rules passed |
| | Templates: no `|safe` on user data, no `dangerouslySetInnerHTML` | Pass |
| Data protection (V6, V8) | Gateway database role reading the vault table | Pass: permission denied |
| | Card left in the vault after payment; card number in database rows or container logs | Pass: none found |
| | Vault encryption | Pass: AES-256-GCM, key only read by `apps.vault` |
| Communications (V9) | TLS versions and ciphers (Caddy 2.11, same image as live) | Pass: TLS 1.2 and 1.3 only, AEAD ciphers only; TLS 1.0, 1.1 and CBC suites refused |
| | HTTP to HTTPS, HSTS | Pass: 308 redirect, `max-age=31536000` |
| Webhooks and simulator (V13) | Webhook signature | Pass: HMAC-SHA256 over timestamp and body, 5-minute tolerance, constant-time compare; the shop re-reads the payment from the API |
| | SSRF guard | Pass: HTTPS only, public addresses only, admin approval, no redirects, connection pinned to the checked address (SEC-09, section 7) |
| | Simulator key and test controls | Pass: constant-time compare, not published on the public server |
| Configuration (V14) | Django admin, OpenAPI schema on live | Pass: 404 |
| | `manage.py check --deploy` with DEBUG off | Pass: only HSTS and SSL-redirect warnings, which Caddy handles |
| | Security headers on live | Pass after SEC-02 and SEC-03: HSTS, nosniff, X-Frame-Options DENY or `frame-ancestors 'none'`, CSP on HTML |
| Secrets and dependencies | gitleaks, full history | Pass: no real secrets (SEC-06) |
| | pip-audit (gateway, simulator, shop), bandit | Pass: no known vulnerabilities; bandit's 2 hits are rate strings, not passwords |

## 6. For the documents

- **Design specification / technical manual (M3):** security controls in section 5 as
  implemented; the shared rate-limit cache (SEC-01); SEC-07b and SEC-08 as known limitations.
- **Progress report (M4):** "A security self-test against OWASP Top 10 and ASVS found no
  critical or high issues; one medium and five low issues were fixed."
- **Test report (M6):** section 5 as test cases with results; NFR-AVA-02 (per-key rate limit)
  re-tested after SEC-01.

Not covered: a test by someone outside the team, denial-of-service resilience, the host
operating system and Google Cloud account settings, and TLS measured from outside on the live
server (the cloud test machine sits behind a TLS proxy; the same Caddy image was measured
locally). An SSL Labs test of the live gateway would close the last gap.

## 7. Second pass, 18 November 2026 (evening)

A second review aimed at the mistakes generated code often has, and at the code merged after
the first test: fraud insights charts, webhook delivery log and Resend, customer spending tab,
fraud explanations and the merchant view of fraud decisions.

**Result: no critical, high or medium findings.** One low finding from the first test
(SEC-09) and one new low finding (SEC-12) were fixed.

| ID | Finding | Severity | Status |
| --- | --- | --- | --- |
| SEC-09 | DNS rebinding window on webhooks; the new delivery log shows the start of the reply, so a rebinding would no longer be blind | Low | Fixed: the name is resolved once per attempt, every answer must be public, and the call connects to that address, with the Host header and the TLS name (SNI and certificate check) still the merchant's host name |
| SEC-12 | DRF's per-IP rate limits keyed on the whole `X-Forwarded-For` header, which the client writes; safe today only because Caddy replaces the header | Low | Fixed: `NUM_PROXIES` follows `TRUSTED_PROXY_HOPS`, so the limits and fraud screening read the same address |
| SEC-13 | `npm audit` reports `picomatch` (ReDoS) in the three front ends | Info | Accepted: build tools only, not in the files served to browsers (`npm audit --omit=dev`: 0) |
| SEC-14 | Python dependencies are version ranges and Docker images are tags, so a deploy installs the newest matching releases | Info | Fixed (19 Nov 2026): Python services install `requirements.lock` with hashes, front-end `package.json` files name exact versions (with `package-lock.json`), base images are pinned by tag and digest. Images built by CI and pushed to a registry are still planned (needs a registry and Actions minutes) |

What was checked, and passed:

| Area | Check | Result |
| --- | --- | --- |
| Access control | Every route of the gateway (merchant API, checkout, guest status, customer, staff API) read for authentication, role and merchant/customer scoping, including the five new features | Pass: every object lookup is scoped (merchant, customer, or role); another merchant's webhook event or payment answers 404; fraud analysts cannot open the webhook log; merchant operators get no scores, reason codes, features or thresholds |
| | Permission-matrix acceptance test (six principals against every endpoint) and the full gateway suite | Pass: 593 tests (before the fixes), all passing after |
| Injection | Raw SQL, `.extra`, shell, `eval`, unsafe deserialisation, template `safe` | Pass: three raw queries, all parameterised; the model file is loaded only after its SHA-256 matches the manifest |
| | CSV export | Pass: formula cells escaped |
| SSRF | Webhook URL submission, approval and delivery | Pass after SEC-09 (tested with a local TLS server: pinned call succeeds for the certificate's name, refused for another name) |
| Sessions and 2FA | Staff two-step sign-in, backup codes, step-up TOTP for key changes, staff and customer password reset, lockout | Pass: no step can be skipped; reset needs the TOTP code once 2FA is set up |
| Card data | Vault, logs, API replies | Pass: AES-256-GCM with the token as associated data, card deleted at submission, no card number in logs or replies |
| Secrets | gitleaks over all 139 commits on every branch; working tree | Pass: no leaks |
| Static analysis | bandit (3 services); semgrep rules for Django, Python security, React, browser JavaScript, secrets and Dockerfiles | Pass: no security issue (style rules and known-safe patterns only) |
| Dependencies | pip-audit (3 services), npm audit (3 front ends) | Pass: no known vulnerabilities in anything that runs (SEC-13 is build-only) |
| Live server | Headers, TLS versions, exposed paths (`/admin/`, `/api/schema/`, `/.env`, `/.git/`), HTTP to HTTPS, private simulator | Pass: TLS 1.2 and 1.3 only; HSTS, CSP, nosniff, frame protection; nothing sensitive exposed; Mailpit behind basic auth |

Residual risks, unchanged by this pass: the demo inbox (Mailpit) receives every reset link and
code, so its password protects every customer account (fixed 19 Nov 2026 after the Codex
re-audit: real recipients now go straight to the provider and only made-up demo addresses
reach Mailpit; codes are no longer in subjects, RUNBOOK.md 13b); SEC-07b and SEC-08 above; no test by
someone outside the team; no denial-of-service testing; the Google Cloud account, firewall and
server operating system were not reviewed.
