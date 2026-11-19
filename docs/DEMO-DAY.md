# Demo day: running the live demo safely

Demo sprint 16. How the team gets from "the stack is live" to a 12-minute demo that survives
a bad day: the timeline, the one-command checks, what to do when a step breaks, the two
fallbacks, and the rehearsals. The scene-by-scene script, presenters and card table are on the
team's demo cheat sheet; server commands are in [`deploy/RUNBOOK.md`](../deploy/RUNBOOK.md)
(sections 9 to 11a).

For the **M4 prototype demonstration** (course milestone, by 19 Dec 2026) the team uses a shorter,
8-minute version: the *Demonstration Rehearsal Script* (Word + PDF in the project's
`11-m4-submission` folder) has the timed running order for all five presenters, speaker notes,
exact clicks and demo cards per scene, a fallback per scene, a demo-day checklist and likely
questions per work package. This file stays the source for the commands and the failure playbook.

Dates: M5 (feature complete) 12 Feb 2027 with rehearsal 1 before it; M6 test report 5 Mar;
rehearsal 2 in the last week of March; **M8 live demo 2 Apr 2027**.

`$P` below is `docker compose -f deploy/compose.prod.yaml` on the server.

## 1. Timeline

| When | Who | Do |
| --- | --- | --- |
| Once, now | Fifa | Watchdog cron + alert channel, uptime monitor, weekly restore test (RUNBOOK 9, 9a). Check the alert arrives: `bash deploy/watchdog.sh --test-alert` |
| 1 week before | Fifa | Copy backups to a laptop (`rsync`, RUNBOOK 9). Fallback laptop drill (section 4) on the laptop that goes to the room. Backup video recorded or re-recorded if anything visible changed (section 5) |
| 48 h before | Fifa | **Freeze**: GitHub variable `MERGE_FREEZE_UNTIL` and `bash deploy/freeze.sh on` (RUNBOOK 10a). Tell the team in the chat |
| Day before | Fifa | `deploy/backup/backup.sh`, then a server snapshot (RUNBOOK 9). `bash deploy/demo.sh reset` once to see it all PASS |
| Morning | Fifa | Before the reset: `nohup bash deploy/demo.sh traffic --minutes 90 &` (about 55 real payments for the dashboard's Fraud insights charts, spread over 90 minutes; it runs from the server, not the hotspot). Then `bash deploy/demo.sh reset`: copy today's cards and emails onto the cheat sheet |
| 1 h before | Fifa | `bash deploy/demo.sh reset` again, then `bash deploy/demo.sh preflight` → **READY**. No more test payments from the presenter's laptop or the hotspot after this (screening counts attempts per IP for an hour) |
| 30 min before | Everyone | Tabs open (marketing site, shop, dashboard signed in as operator and as administrator with the authenticator ready, Mailpit). Fallback laptop running and seeded, on charge. Phone hotspot on. Video on the desktop |
| After | Fifa | `bash deploy/freeze.sh off` and delete `MERGE_FREEZE_UNTIL`. Delete the snapshot once all is well |

## 2. The one-command checks

- `bash deploy/demo.sh reset` (RUNBOOK 11a): restock, empty the inbox, print fresh demo cards
  and customer emails, run `demo_check`. Deletes nothing.
- `bash deploy/demo.sh preflight`: the demo-day checklist in one go.
  1. Deploy freeze on? (a warning, not a failure)
  2. `watchdog.sh --check`: containers, `/readyz` (both databases and the worker heartbeat),
     the shop's `/healthz`, disk, memory, certificate, backup age
  3. `smoke-check.sh` from the server's public name
  4. One real payment through the shop with a fresh demo card (integration test S1: cart,
     checkout, approve, webhook marks the order paid, capture). The order is real and shows
     on the dashboard as a captured wireless mouse
  5. `demo_check`

  It ends with **READY** or **NOT READY: <what> failed**. NOT READY an hour before: fix it with
  section 3, run preflight again, and if it is still red 20 minutes before, switch to the
  fallback laptop.

## 3. If something breaks

On stage, keep talking and move on; fix things after. Before the demo, use the right column.

| What you see | During the demo | Before the demo (server) |
| --- | --- | --- |
| A payment is blocked or asks for a code when it should not | "Screening remembers cards across every shop": use the spare approve card and a new email | `demo.sh reset` prints fresh cards; did someone rehearse with today's cards? |
| No email in Mailpit after 30 s | Show the payment's page in the dashboard instead | `curl https://gateway.<domain>/readyz`: `"worker"` means `$P restart gateway-worker` |
| The order stays "waiting for payment" | Refresh once; the shop also asks the gateway directly on return | `$P logs --tail 50 gateway-worker merchant` |
| S4 still waiting after 1 minute | Open the payment in the dashboard: the reconciliation checks are listed; come back to it | `$P logs --tail 50 gateway-worker` |
| Dashboard sign-in fails | Use the second signed-in browser profile | Five failures lock the account for 15 minutes: wait, or sign in as another staff account |
| A page errors or times out | Switch to the fallback laptop (section 4) | `bash deploy/watchdog.sh --check`, then RUNBOOK 12 |
| Venue Wi-Fi down | Presenter laptop on the phone hotspot; the server is unaffected | |
| Server down, hotspot works | Fallback laptop (it needs no internet at all) | Uptime monitor and watchdog alerts say why; restore from the snapshot after the demo |
| Laptop stack also fails | Play the backup video and narrate over it | |

## 4. Fallback 1: the whole stack on a laptop

The laptop runs the same Compose stack at `https://gateway.localhost`, `https://shop.localhost`
and `https://mail.localhost` (no inbox password), with no internet needed. Data is separate
from the server: seed it fresh. Do this drill a week before and again the day before.

Needs Docker Desktop (8 GB memory for Docker is comfortable), Node.js 22 for the two bundles,
and the repository at the commit the server runs (`main` during the freeze).

```bash
# once: secrets and bundles (README quick start steps 1 and 2)
docker compose -f deploy/compose.yaml up -d --build
bash deploy/demo.sh seed          # Volt & Co., staff logins (temporary passwords), shop keys
bash deploy/demo.sh reset         # cards, emails, demo_check
python3 -m venv .venv-it && .venv-it/bin/pip install --require-hashes -r tests/integration/requirements.lock   # once, for preflight
bash deploy/demo.sh preflight     # READY
```

- **Fraud model:** copy `hgb-fs02-2026-11-13` into `gateway/apps/risk/model_artifacts/` and
  put `RISK_MODEL_VERSION=hgb-fs02-2026-11-13` in `deploy/.env`, as on the server, so the
  laptop screens the same way. Without it, preflight warns "stub" and the rules decide.
- **Staff logins:** sign in once as each of the three staff accounts after `seed` and add
  them to the authenticator app as "SecurePay laptop", so they do not mix with the server's.
- **No certificate warnings on stage:** trust Caddy's local certificate authority once.
  `docker compose -f deploy/compose.yaml cp caddy:/ca/root.crt securepay-local-ca.crt`, then
  macOS: `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain securepay-local-ca.crt`;
  Windows: double-click the file > Install Certificate > Local Machine > Trusted Root
  Certification Authorities. Restart the browser. Remove it after the demo.
- `*.localhost` names resolve to the laptop on macOS and recent Windows; if not, add
  `127.0.0.1 gateway.localhost shop.localhost mail.localhost simulator.localhost` to the hosts file.
- The marketing site (scene 1) is on Vercel; offline, show the slide with its screenshot.
- Leave the stack running from 30 minutes before; starting it takes about a minute.

## 5. Fallback 2: the backup video

A screen recording of the whole script, with the team's voices, ready to play if both stacks
fail. Record it after rehearsal 1 (when the script is settled) and again after anything
visible changes.

- Record on the fallback laptop stack or the server, 1920 × 1080, with OBS Studio or the
  built-in recorder (macOS: Shift-Cmd-5; Windows: Xbox Game Bar, Win-Alt-R). Browser zoom
  125 % so text reads on a projector; hide bookmarks and other tabs.
- One take per scene is fine; join them with any editor. Keep it to 12 minutes; add a
  caption per scene ("S3: card testing blocked") so it stands on its own.
- Never show the dashboard's authenticator QR code, API keys, or the inbox password.
- Keep copies on the presenter laptop's desktop, a USB stick and the team Drive. Check it
  plays offline in the venue's player.

## 6. Rehearsals

**M4 rehearsals (weeks 10 to 11).** Package walk-throughs, then two timed runs of the M4 script;
see the rehearsal script, Chapter 6, for the plan and its 8-minute log.

**Rehearsal 1 (before M5, 12 Feb 2027).** Full run on the server, in order, with a timer and
one person (not presenting) taking notes. Do it under demo conditions: `reset` the morning,
`preflight` an hour before, and the S3 step from the hotspot. Then switch to the fallback
laptop mid-run once, on purpose, to time the switch.

**Rehearsal 2 (last week of March).** Same, in the room if possible, with the projector, and
the video played once to check sound and size.

Leave at least an hour after a rehearsal before the next real run (IP velocity), and run
`demo.sh reset` before it.

Rehearsal log (copy for each run):

| Step | Presenter | Planned | Actual | What went wrong / to change | Owner |
| --- | --- | --- | --- | --- | --- |
| 1. The problem | Liu Ying | 1:00 | | | |
| 2. Mei buys a cable (S1) | Jun Han | 2:00 | | | |
| 3. Mei buys a laptop (S2) | Jun Han | 1:30 | | | |
| 4. Card testing blocked (S3) | Noppawut | 2:00 | | | |
| 5. The bank goes quiet (S4) | Adeeb | 1:30 | | | |
| 6. Back office (S5) | Janyaporn | 1:30 | | | |
| 7. Keeping it safe (S6) | Noppawut | 1:30 | | | |
| 8. Results | Liu Ying | 1:00 | | | |
| Switch to fallback laptop | | under 1:00 | | | |
| **Total** | | **12:00** | | | |

Preflight result: READY / NOT READY (what): ______. Watchdog alerts during the run: ______.
