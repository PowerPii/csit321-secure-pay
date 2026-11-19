# Cross-service integration tests

Demo stories S1-S6 (`docs/MVP-SCOPE.md` section 2), the emailed receipt and guest status check, and the simulator's fault controls, run against the real Compose stack over HTTPS. The tests drive the same APIs the browser pages use (the hosted checkout's `/checkout/*`, the shop's forms, `/guest/status/*`), read emails from Mailpit, and add fault rules through the simulator's test controls.

```bash
# the stack, set up as in the main README (quick start steps 1 to 4)
docker compose -f deploy/compose.yaml up -d --build
# a Python 3.12 environment with the two test dependencies
python3 -m venv .venv-it && .venv-it/bin/pip install --require-hashes -r tests/integration/requirements.lock
.venv-it/bin/pytest tests/integration -q        # about 2 minutes
```

What they need:

- The demo shop registered with its key in `deploy/secrets/securepay_api_key` (quick start step 4).
- `deploy/secrets/simulator_test_control_key`, and test controls on (`SIM_TEST_CONTROLS=1`, the Compose default). With controls off, `test_fault_controls.py` is skipped.
- `*.localhost` resolving to 127.0.0.1 (most systems do; otherwise add `gateway.localhost shop.localhost simulator.localhost mail.localhost` to `/etc/hosts`).
- Caddy's local root certificate: copied from the `caddy` container automatically, or set `CADDY_ROOT_CA` to its path.

| File | Covers |
| --- | --- |
| `test_demo_stories.py` | S1 through the shop's own pages and the signed webhook / signed GET, then capture; S2 code from Mailpit; S3 blocklisted card; S4 lost response settled by the worker's status check with the same operation ID (about 40 s); S5 idempotent retry and 409 on a changed body; S6 two refunds at once |
| `test_guest_status.py` | Receipt email with reference and status link; same reply for a wrong email; code from Mailpit; 15-minute cookie; sign-out; lock after 3 wrong codes |
| `test_fault_controls.py` | Test-control key; `drop_response` + `notify` settled by a signed notification before any status check; `drop_request` retired as `no_record` and declined `not_processed` |
| `test_recovery_drill.py` | Opt-in (`RECOVERY_DRILL=1`, it replaces the local databases): backup with a checkout in flight, a payment after it, `deploy/backup/restore.sh`; history back, later payment gone, zero vault rows, card asked again then paid once, old payment still captures, `recovery_check` passes |

Each run pays twice with each approving test card. Screening counts attempts per card (the burst rule and the trained model's card history), so a second run soon after the first sees those cards as risky and S1/S6 end Blocked. Start from a fresh database between repeated runs: `docker compose -f deploy/compose.yaml down -v`, then quick start steps 3 and 4 again.
