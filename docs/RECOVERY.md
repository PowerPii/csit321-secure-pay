# Recovery rehearsal: start, restore and roll back

A checklist for a teammate who **did not** build the deployment. It proves that someone else
can bring SecurePay up from nothing, restore a backup taken in the middle of a payment, and
roll back a bad deploy, using only the published instructions (Codex completion audit,
19 Nov 2026, section 4).

Run it on your own laptop. Nothing here touches the public server; part E is the optional
server version, for Fifa only.

**While you work, record** in the table at the end: the time you start each part, how long
it took, and **the first instruction you had to ask someone about**. Asking is the point:
each question shows us an instruction to fix. Do not let the person who wrote the scripts
sit next to you; message them only when stuck, and write down when you did.

## What you need

- Docker Desktop (macOS or Windows) or Docker Engine (Linux), Node.js 20+, Python 3.12, git
- A clone of the repository on `main`: `git clone https://github.com/PowerPii/csit321-secure-pay.git`
- About 60 minutes. A fresh laptop needs extra time for the first image build.

## A. Start from an empty machine (about 20 minutes)

1. Follow `README.md` **Quick start** steps 1 to 4 exactly as written (secrets, the two
   front-end bundles, `docker compose -f deploy/compose.yaml up --build`, register the shop).
2. Check the database started cleanly. This must print nothing:
   `docker compose -f deploy/compose.yaml logs db | grep -i "permission denied"`
   (Before 19 Nov 2026 this failed on Docker Desktop; the initialiser is now inside the image.)
3. Open https://shop.localhost, buy something with card `4242 4242 4242 4242`, and check the
   order says paid. Write down the payment reference shown on the receipt (`SP-XXXX-XXXX`).

**Done when:** the order is paid and `docker compose -f deploy/compose.yaml ps` shows every
service up.

## B. Back up in the middle of a payment, then restore (about 15 minutes)

1. In the shop, start a second order and enter card `5555 5555 5555 4444` on the payment
   page, but **do not press Pay**. Leave the tab open. The card now sits, encrypted, in the vault.
2. Take a backup:
   `COMPOSE_FILE=deploy/compose.yaml bash deploy/backup/backup.sh`
   It prints the folder (in `~/fyp-backups`). Look inside: three `.dump` files and `MANIFEST`.
3. Buy a third order and pay it. It happened **after** the backup, so the restore must remove it.
4. Restore:
   `COMPOSE_FILE=deploy/compose.yaml bash deploy/backup/restore.sh`
   It checks the backup, saves a safety copy of the current data, restores and restarts.
   Note the seconds it reports.
5. Check, and tick each:
   - [ ] the script printed `vault rows: 0` (no card came back from the backup);
   - [ ] the first order (part A) is still paid, under the same reference;
   - [ ] the third order's payment is gone: `COMPOSE_FILE=deploy/compose.yaml bash
         deploy/recovery-check.sh --payment <its SP- reference>` says `not found` (a FAIL line here is the
         expected result);
   - [ ] back in the open tab, pressing **Pay** asks you to enter the card again
         ("Please enter your card details again"); enter it and pay: it goes through once;
   - [ ] `COMPOSE_FILE=deploy/compose.yaml bash deploy/recovery-check.sh --payment <first
         order's reference>` ends with `recovery check passed`.

The same drill runs automatically: `RECOVERY_DRILL=1 .venv-it/bin/pytest
tests/integration/test_recovery_drill.py -v` (see `tests/integration/README.md`).

## C. Roll back a deploy (about 15 minutes)

On the server, `auto-deploy.sh` records each deploy and `rollback.sh` goes back. On a laptop
you play both parts by hand.

1. "Deploy" the current main, labelled with its commit, and record it:
   ```bash
   export COMPOSE_FILE=deploy/compose.yaml RELEASE_HISTORY=~/securepay-rehearsal.jsonl
   GIT_REVISION=$(git rev-parse HEAD) docker compose -f $COMPOSE_FILE up -d --build
   bash deploy/release-record.sh record deploy $(git rev-parse HEAD) $(git rev-parse HEAD~1)
   bash deploy/release-record.sh show
   ```
   `show` lists every service with its image digest and the commit it was built from.
2. Roll back to the previous commit: `bash deploy/rollback.sh`
   - If it refuses because migrations were added, that is correct behaviour: note it, then
     pick an older commit after the newest migration (`git log --oneline -- '*/migrations/*'`
     shows which) and run `bash deploy/rollback.sh <that 40-character commit>`.
   - It should end with `every app container runs <commit>`, the recovery check, and
     `rolled back to ...`.
3. Check, and tick each:
   - [ ] `bash deploy/release-record.sh show` has a `rollback` line with the old commit and
         new image digests for gateway, gateway-worker, simulator and merchant;
   - [ ] the order from part A is still paid, and `bash deploy/recovery-check.sh --payment
         SP-XXXX-XXXX` (your reference) says it agrees with the simulator.
4. Go forward again: `git checkout main && rm -f ~/.securepay-rolled-back`, then step 1's
   `docker compose ... up -d --build` line. (On the server the next deploy does this.)

## D. Clean up

`docker compose -f deploy/compose.yaml down -v` deletes the laptop stack and its data.
`rm -rf ~/fyp-backups ~/securepay-rehearsal.jsonl ~/deployed-release.txt` removes the rest.

## E. On the public server (Fifa, optional, with a quiet hour)

Only after A to C passed on a laptop, outside a merge freeze, and not on a demo day.
Rolling back code changes no data, but it restarts the stack for about a minute.

1. `bash deploy/backup/backup.sh && bash deploy/backup/verify.sh` (a fresh, verified backup)
2. `bash deploy/release-record.sh show 3`: the newest `deploy` record names its `before` commit
3. `bash deploy/rollback.sh` (it refuses if migrations were added since; then stop here)
4. `bash deploy/release-record.sh show 1` and `bash deploy/recovery-check.sh`
5. Forward again: `bash deploy/auto-deploy.sh` (it returns the clone to main)

Never run `restore.sh` on the server for a rehearsal: it replaces live data
(`--replace-live-data`). Use the weekly `verify.sh` there instead.

## Record

| Part | Who | Date and start time (SGT) | Elapsed | First instruction you had to ask about | Fixed in |
| --- | --- | --- | --- | --- | --- |
| A. Start | | | | | |
| B. Restore | | | | | |
| C. Rollback | | | | | |
| E. Server (optional) | | | | | |

After the run: fix the instruction named in the table (or open an issue for it), then
repeat **only the affected step** and add a second row for it.

## Reference: what each script guarantees

| Script | Guarantee |
| --- | --- |
| `deploy/postgres/Dockerfile` | The database initialiser is part of the image with a fixed mode, so a new volume starts the same way on Linux and Docker Desktop. |
| `deploy/backup/backup.sh` | Works on macOS Bash 3.2. Writes to a hidden `.incomplete-*` folder and publishes it (with `MANIFEST`: sizes, SHA-256, source revision) only after all three dumps succeeded. Vault card rows are never dumped; the vault's migration history is. |
| `deploy/backup/verify.sh` | Picks the newest folder **with a MANIFEST**, checks the checksums, restores into scratch databases, and fails on any card row or a missing vault migration history. |
| `deploy/backup/restore.sh` | Verifies first, takes a safety backup, restores all three databases together, waits for `/readyz`, fails if any card row came back. Refuses the public server without `--replace-live-data`. |
| `deploy/release-record.sh` | One JSON line per deploy or rollback in `~/deploy-history.jsonl`: time, revision, previous revision, every service's image digest and source revision. |
| `deploy/rollback.sh` | Goes back to an older commit on main; refuses if migrations were added in between unless `--allow-migrations`; checks every app container runs the target; records it; runs the smoke and recovery checks. |
| `manage.py recovery_check` | Asks the simulator about each recent finished operation by its original ID and compares; flags old vault rows and old open operations. |
