# Evidence for the six mandatory NFRs, 19 November 2026

Collected for the six Must requirements that were still waiting for manual evidence after the
Codex re-audit of 19 Nov 2026 (`4ee019b`). Results are recorded in
[`../../manual-results.yaml`](../../manual-results.yaml); this folder holds the raw output.

| | |
| --- | --- |
| Revision | `main` at `4ee019b` (PR #72) |
| Environment | Disposable local copy of the stack in a cloud container (4 vCPU, 15 GB): `deploy/compose.yaml` with `DJANGO_DEBUG=0` and the Django admin off for gateway, worker, simulator and shop; Postgres 17, Caddy 2.11.9 with its local CA, Mailpit. Stub model (the trained artefact stays in the team folder). Torn down afterwards. |
| Data | Synthetic only: the Volt & Co. demo seed, the 11 integration scenarios, 1,080 load payments with fresh demo-range cards, `@example.com` / `@example.test` addresses |
| Not touched | The live server. No production data, mail or deploys |
| Collected by | Claude, for Fifa (branch `claude/project-thread-6gpxnq`) |
| Reviewed by | Name: ______________________  Date: ____________ (left for the team) |

## Results

| ID | Result | Figures | Files |
| --- | --- | --- | --- |
| NFR-CON-02 | Pass | 0 full card numbers in 17 locations (all 7 service logs, 3 databases outside the vault, 11 emails, merchant API, dashboard payments/refunds, fraud report + CSV export, audit log, webhook delivery log) | `m-con-02-card-number-scan.json` |
| NFR-CON-04 | Pass | 10 of 10 hashes Argon2id with 10 distinct salts; 11-character password refused on customer sign-up, merchant registration and `create_staff` | `m-con-04-password-hashes.json` |
| NFR-AVA-01 | Pass | 5 crashes, back in 5.8 to 6.4 s; 1,028 = 1,028 authorisations matched by operation ID, 0 missing, 0 twice, 0 unresolved | `m-ava-01-*.{txt,json}` |
| NFR-ENC-01 | Pass | Run by Fifa on the live server's shell (this container's proxy inspects TLS): all 5 names Let's Encrypt, TLS 1.0/1.1 refused, only ECDHE + AEAD on TLS 1.2, HTTP 308 to HTTPS everywhere, 8443 closed. The local Caddy run is kept as well | `../2026-11-19-tls-host.txt`, `m-enc-01-local-caddy-tls.txt` |
| NFR-ENC-02 | Pass | AES-256-GCM while held (tamper and wrong-token both refused), removed on submission and 1 s after expiry, restored backup has 0 vault rows | `m-enc-02-vault.json` |
| NFR-PER-02 | Pass | p95 13.3 ms (1,000) and 22.0 ms (20/s for 60 s), 0 over 500 ms; forced slow screening blocked 3 of 3 as `screening_unavailable` at 510 ms | `m-per-02-*.{txt,json}` |

## How each was done

* **CON-02:** after the integration run and the crash drill, `scripts/scan_pan.py` collected
  every place a card number could leak and counted Luhn-valid 13 to 19 digit numbers and exact
  matches of the 6 card numbers the tests pay with. It found its positive control (3 numbers,
  spaced, dashed and plain) before the run. Look-alikes set aside by rule: numbers right after
  a decimal point (feature values such as `1.4367816091954022`) and MIME boundaries or
  Message-IDs in raw email; each was checked by hand.
* **CON-04:** `scripts/con04.py` signs up through the real endpoints, then reads only counts,
  the scheme and the Argon2 parameters with SQL; no hash leaves the database.
* **AVA-01:** `scripts/ava01.sh` runs `tests/load/checkout_load.py` at 2 payments/s for 540 s
  (limits raised for the drill: 2,000/min per key, 4,000/min per IP, `THROTTLE_ANON=6000/min`)
  and kills the gateway's main process with `kill -9` every 90 s; Docker restarts it.
  `scripts/ava01_reconcile.py` then matches the gateway's authorise operations with the
  simulator's records by operation ID. The load tool itself prints FAIL because 53 of its calls
  landed while the gateway was down (51 creates that created nothing, 2 submits that lost their
  reply). One of those two had reached the simulator; the worker's status check settled it as
  authorised with the same operation ID 61 s later. The other never reached the gateway and
  stayed open for the customer.
* **ENC-02:** `scripts/enc02.py` holds a card, checks the stored form and decrypts it inside the
  gateway container (and fails with one byte changed or another token), submits it, lets a
  second checkout expire (its expiry moved back in this throwaway database), and takes a backup
  with `deploy/backup/backup.sh` while a third card is held, then restores it into a scratch
  database.
* **PER-02:** `manage.py benchmark_screening` and `loadtest_screening` as in MANUAL-TESTS.md,
  then `scripts/per02_timeout.py`: a lock on `risk_risklistentry` makes the rules' query wait,
  and the 500 ms statement timeout cuts it off.

## Findings worth a look

* The decision record for a timed-out screening says `InternalError`, not that the 500 ms budget
  ran out (the timeout cancels the query, and the next statement in the aborted savepoint is what
  raises). The payment is still blocked correctly; only the label is vague for an analyst.
* The scripts were written for this run (local paths under the container's scratch folder,
  Compose project `nfr`). They are kept as run, so anyone can see exactly what was checked.

## To repeat

Bring up the local stack as in the README quick start, add an override with `DJANGO_DEBUG: "0"`,
run `bash deploy/demo.sh seed` and the integration suite, then the scripts above. For NFR-ENC-01
run `bash tests/tls/check-tls.sh securepaysg.me` from a network that does not intercept TLS (the script says INVALID if it does) and record it under `M-ENC-01`.
