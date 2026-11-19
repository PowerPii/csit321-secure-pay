# Live server checks, 20 Nov 2026 (00:20 to 01:15 SGT)

Code on the server: `db8cacd`. Fifa ran the server shell and dashboard steps; Claude drove the
browser checks from a cloud container over HTTPS and recorded the results.

| File | Check |
| --- | --- |
| `server-checks.txt` | M-AVA-05 (cron, backup folders, `verify.sh`) and M-PRI-01 (log grep), plus the deployed revision and migrations |
| `integrity-page-2026-11-20.png` | Integrity and keys page after the key rotation (M-ENC-03) and the clean-up run (M-PRI-01) |
| `m-con-06-customer.txt` | Idle sign-out of a throwaway customer account (M-CON-06) |
| `m-per-03-payments.json`, `m-per-03-alert-timing.txt` | 20 blocked payments and when each fraud alert was written (M-PER-03) |

M-PER-01 (load test) was attempted and is **not recorded**: the first run was refused by the
per-IP limit because `compose.prod.yaml` did not pass `THROTTLE_ANON` to the gateway (fixed in
this change); the second, with the limit raised, was stopped after 20 minutes without a result.
The same test on today's code on a local stack passed (p95 85 ms, `../2026-11-20-local/per-01-local-ab.txt`),
so this is not a code regression; the live run needs repeating with the load generator off the
server (it shares the e2-medium's 2 shared vCPUs with the gateway).
