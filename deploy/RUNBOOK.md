# Running SecurePay on the public server

Sprint 9: the whole stack on one Ubuntu server in Fifa's account: a Google Cloud VM (chosen
16 Nov 2026; it stays there through M6, switching from the free trial to paid billing before
the trial ends, Fifa's decision of 19 Nov 2026), with Let's Encrypt certificates for its names:
first free `sslip.io` names, since 19 Nov 2026 the domain `securepaysg.me` (section 13a). The marketing website stays on
Vercel and does not link here (decided 14 Nov 2026). Share the addresses with the team and
assessors directly.

**Current server (19 Nov 2026):** Google Cloud project `securepay-demo`, VM `securepay`
(e2-medium, asia-southeast1), static IP `35.213.144.96`, domain `securepaysg.me` (Namecheap,
GitHub Student Pack; moved from `35-213-144-96.sslip.io` with section 13a, whose names
redirect to the new ones for now). Real email through a provider: section 13b.
First deploy: all smoke checks and all 11 integration tests passed on it.
Automatic deploys are on (step 10) since 16 Nov 2026: the first run from GitHub Actions passed
its smoke check.

| Name | What | Who |
| --- | --- | --- |
| `https://gateway.<domain>` | Merchant API, hosted checkout (`/pay/...`), guest status (`/guest/status`), staff dashboard (`/dashboard/`) | Public; the dashboard needs a staff account with TOTP |
| `https://shop.<domain>` | Demo shop | Public |
| `https://mail.<domain>` | Demo inbox (Mailpit): verification codes, receipts, guest status codes | Team and assessors (basic auth) |
| `simulator.securepay.internal:8443` | Payment simulator, including its fault controls | Inside the server only |

`<domain>` is `securepaysg.me` on the live server. On a new server without a domain it can be
the IPv4 with dashes plus `.sslip.io`: for `203.0.113.5` it is `203-0-113-5.sslip.io`. A real
domain needs `gateway`, `shop` and `mail` pointed at the server in its DNS (section 13a). The names follow the IP, so keep it stable: on Google Cloud, reserve a static external IP. Moving to another
server later means new names, which is fine because nothing public links here.

What is different from the local stack (`compose.yaml`): `DJANGO_DEBUG=0`; the Django admin is
off in every service and Caddy answers `/admin*` with 404; the simulator has no public name
(Caddy serves it on port 8443, which is not published); the gateway's block on private
webhook addresses is fully on, so the worker reaches the shop at its public address like any
merchant; Mailpit is behind basic auth; the checkout and dashboard bundles are built into the
Caddy image (no Node.js on the server); container logs are capped at 50 MB each.

## 1. Create the server (Fifa, once)

For step 2 only, sign in as your own Google Cloud user (`fifa@` below); from then on as
`securepay@`.

**Google Cloud (the live server, through M6)**

The free trial gives US$300 for 90 days (until about 14 February 2027). When it ends the VM
stops unless the account is upgraded, so before then upgrade the **same** billing account to
paid (Billing > Upgrade; the VM, disk and static IP stay as they are) and set a budget alert
(Billing > Budgets & alerts, for example US$30 a month). The e2-medium VM costs about US$25 a
month. Nothing moves, so the addresses stay the same.

1. Sign up at cloud.google.com/free and create a project (for example `securepay-demo`).
   Enable the Compute Engine API when asked.
2. VPC network > IP addresses > **Reserve external static IP address**: region
   **asia-southeast1 (Singapore)**, IPv4, Standard or Premium tier.
3. Compute Engine > VM instances > **Create instance**:
   - Region **asia-southeast1 (Singapore)**, any zone
   - Machine **e2-medium** (2 vCPU, 4 GB), roughly US$25 to 30 a month from the credit
   - Boot disk: **Ubuntu 24.04 LTS**, the "x86/64, amd64 noble image" (not Minimal, not
     Arm64), **30 GB** (the default 10 GB is too small), balanced persistent disk
   - Networking: tick **Allow HTTP traffic** and **Allow HTTPS traffic**; open the network
     interface, set Network Service Tier to the same tier as the static IP, and External IPv4
     address to the static IP from step 2 (not "Ephemeral")
   - Security > Manage access > **Add item**: paste your laptop's public key
     (`~/.ssh/id_ed25519.pub`, ending in a comment such as `fifa`). That comment is the user
     name you sign in with: `ssh fifa@<ip>`.
4. Check that both firewall boxes really are ticked (VM > Edit > Networking). If they are not,
   Let's Encrypt cannot reach port 80 and Caddy logs "Timeout during connect (likely firewall
   problem)"; tick them, Save, and `restart caddy`. HTTP/3 on UDP 443 is optional.

The server-setup script notices that the external IP is NAT'd (the VM itself only holds a
`10.x` address) and puts it on the loopback interface, so the worker's webhooks to the shop
stay inside the VM.

**Another provider (fallback only)**

Not planned: the Student Pack no longer includes DigitalOcean credit (checked 19 Nov 2026), so
the demo stays on Google Cloud. If the Google Cloud account ever cannot continue, any Ubuntu
24.04 VM with 2 vCPU / 4 GB RAM, a stable public IPv4 and an SSH key works the same way (for
example Azure for Students); move with section 13.

## 2. Get the code and set up the server (once)

The repository is private, so the server gets a **read-only deploy key** for it (a public
`raw.githubusercontent.com` download answers 404). Sign in as your own user first:

```bash
ssh fifa@203.0.113.5        # Google Cloud: the name in your SSH key's comment (often root@ elsewhere)
ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N "" -C securepay-server
cat ~/.ssh/deploy_key.pub
```

On GitHub: repository Settings > Deploy keys > **Add deploy key**, title `securepay-server`,
paste the key, leave **Allow write access unticked** (the server only ever reads). Then:

```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/deploy_key -o StrictHostKeyChecking=accept-new" \
  git clone git@github.com:PowerPii/csit321-secure-pay.git
less csit321-secure-pay/deploy/server-setup.sh       # read it first
sudo bash csit321-secure-pay/deploy/server-setup.sh
```

The setup installs security updates (and turns on daily automatic ones), Docker with the
Compose plugin, a `securepay` user that signs in with the same SSH key, SSH with keys only and
no root sign-in, a firewall with only 22, 80 and 443 open, and 2 GB of swap. On clouds that NAT
the public IP (Google Cloud, Oracle) it also puts that IP on the loopback interface so
containers can reach the server's own public names (the worker's webhooks to the shop), and on
Oracle it replaces the image's own reject-all iptables rules with that firewall.

## 3. Hand the code to the `securepay` user

Still as your own user:

```bash
sudo mv ~/csit321-secure-pay /home/securepay/
sudo install -m 600 -o securepay -g securepay ~/.ssh/deploy_key /home/securepay/.ssh/deploy_key
sudo chown -R securepay:securepay /home/securepay/csit321-secure-pay
sudo -u securepay git -C /home/securepay/csit321-secure-pay config core.sshCommand \
  "ssh -i /home/securepay/.ssh/deploy_key -o StrictHostKeyChecking=accept-new"
rm ~/.ssh/deploy_key ~/.ssh/deploy_key.pub
```

**Before closing this session**, check in a second terminal:

```bash
ssh securepay@203.0.113.5
cd csit321-secure-pay && git pull && docker --version
```

From here on everything runs as `securepay` inside `~/csit321-secure-pay`. Team members get
access by adding their public key to `/home/securepay/.ssh/authorized_keys`.

## 4. Secrets and settings

```bash
bash deploy/make-secrets.sh
nano deploy/.env      # DOMAIN=203-0-113-5.sslip.io (or a real domain) and ACME_EMAIL=<a team address>
```

The script makes every `deploy/secrets/*` file that does not exist yet (fresh random values;
never copy the development ones), and makes `deploy/.env` from `prod.env.example`. It prints the
demo inbox password **once**: put it in the team password manager.

Then keep an **offline copy** of `vault_encryption_key`, `field_encryption_key` and
`card_fingerprint_key` in the team password manager (Bitwarden is free). Losing the vault or
field key makes what they protect unreadable; losing the fingerprint key resets fraud history.
Nothing in `deploy/secrets/` or `deploy/.env` is ever committed (`.gitignore`, gitleaks in CI).

## 5. The fraud model (optional, recommended)

The model folder is git-ignored. From a laptop with the team folder:

```bash
scp -r fyp/02-research/gateway-model/hgb-fs02-2026-11-13 \
  securepay@203.0.113.5:csit321-secure-pay/gateway/apps/risk/model_artifacts/
```

then on the server make it readable for the app inside the container (scp keeps the laptop's
owner-only permissions, and the gateway logs "manifest.json unreadable: Permission denied"):

```bash
chmod -R a+rX gateway/apps/risk/model_artifacts/hgb-fs02-2026-11-13
```

and set `RISK_MODEL_VERSION=hgb-fs02-2026-11-13` in `deploy/.env`, then
`docker compose -f deploy/compose.prod.yaml up -d gateway`. Left empty, the stub model
runs (score 0, rules decide). A bad copy fails its SHA-256 check and blocks every payment as
`screening_unavailable`, so it shows at once.

Every decision stores a plain-language "why" (rule hits plus the model's TreeSHAP
contributions, `apps/risk/explain.py`), shown on the case and payment pages and in Fraud
insights. Decisions made before that existed have none; fill them in once, after a deploy:

```bash
docker compose -f deploy/compose.prod.yaml exec gateway python manage.py explain_decisions
```

It only writes the explanation field, and adds model contributions only to records scored by
the model installed now.

## 6. Start

```bash
docker compose -f deploy/compose.prod.yaml up -d --build      # first build takes a few minutes
docker compose -f deploy/compose.prod.yaml ps
docker compose -f deploy/compose.prod.yaml logs -f caddy      # wait for "certificate obtained successfully"
```

Caddy asks Let's Encrypt for the three public names on its own (port 80 must be open, which
step 2 did). If Let's Encrypt refuses (for example its rate limit for `sslip.io`), Caddy falls
back to ZeroSSL by itself; check the log.

## 7. Register the demo shop and staff accounts

```bash
P="docker compose -f deploy/compose.prod.yaml"
$P exec gateway python manage.py create_merchant "Demo Shop" \
  --webhook-url "https://shop.$(grep ^DOMAIN= deploy/.env | cut -d= -f2)/webhooks/securepay" \
  | tee /dev/stderr | awk '/API key:/{print $3 > "deploy/secrets/securepay_api_key"}
                           /Signing secret:/{print $3 > "deploy/secrets/securepay_signing_secret"}'
$P restart merchant

# Staff for the dashboard (password prompt, 12+ characters; TOTP is set up at first sign-in).
# Use the team's real addresses here only if they agree; demo customers use @example.com.
$P exec gateway python manage.py create_staff ops@demoshop.sg --role merchant_operator --merchant mer_... --name "Aisha Rahman"
$P exec gateway python manage.py create_staff analyst@securepay.sg --role fraud_analyst --name "Daniel Lim"
$P exec gateway python manage.py create_staff admin@securepay.sg --role administrator --name "Mei Tan"
```

Staff emails (lockout notices, password reset links, registration notices) go to the demo
inbox, like everything else.

Since sprint 10 a merchant can also register itself at `https://gateway.<domain>/dashboard/register`:
it verifies its email from the link in the demo inbox, every administrator gets a notice, an
administrator approves it on the Merchants page, and its operator then signs in and generates
the API key on the API keys page. The registration links use `DASHBOARD_URL`, which
`compose.prod.yaml` sets from `DOMAIN`, so there is nothing to add to `.env`.

To make several accounts at once with random temporary passwords (printed once; share each
privately; since sprint 10 anyone can also set their own with "Forgot your password?" on the
sign-in page). The `</dev/null` matters:
without it `docker compose exec` reads the rest of the list and only the first account is made.

```bash
while IFS='|' read -r email name; do
  pw="$(openssl rand -base64 12 | tr -d '/+=')-Sp1"
  $P exec -T -e STAFF_PASSWORD="$pw" gateway python manage.py create_staff "$email" \
    --role administrator --name "$name" </dev/null >/dev/null && echo "$name  $email  $pw"
done <<'EOF'
someone@example.com|Full Name
EOF
```

A new password for an existing account: `$P exec gateway python manage.py changepassword <email>`.

Staff get 10 one-time backup codes when they first set up the authenticator app, and can make
a new set under "Two-step verification" in the dashboard. Someone who has lost both their phone
and their backup codes needs a reset (check who is asking first, outside the dashboard); the
next sign-in then shows the setup QR code again:

```bash
$P exec gateway python manage.py reset_staff_mfa <email>
```

## 8. Check it

From a laptop:

```bash
bash deploy/smoke-check.sh 203-0-113-5.sslip.io
```

It checks the health endpoint, the checkout, guest status and dashboard pages, that `/admin/`
is 404 on the gateway and the shop, that the API needs a key, that the inbox needs a password,
HTTP to HTTPS, the security headers, and that the simulator does not answer from outside.

On the server itself works too (`bash deploy/smoke-check.sh <domain>`).

Then the cross-service tests (S1 to S6, receipts, guest status, fault controls), from inside
the server so they can reach the simulator's test controls and the inbox:

```bash
docker compose -f deploy/compose.prod.yaml run --rm integration-tests    # about 2 minutes
```

They make real (simulated) payments with the test cards, and a second run soon after the first
sees those cards as risky. On a server that is already shared, run them once at the start, or
reset first (`down -v` deletes **all** data; then steps 6 and 7 again).

Two things worth checking by hand once:

- **Webhooks reach the shop.** Pay in the shop with `4242 4242 4242 4242`; the order turns paid
  within seconds. (The worker calls `shop.<domain>` at the server's public IP, which Docker
  routes back to Caddy. If orders stay unpaid, look at `logs gateway-worker`.)
- **The gateway sees real client IPs** (velocity rules use them). After a payment, the
  screening decision on the payment's dashboard page shows your own IP, not a `172.x` one.

## 9. Backups

```bash
crontab -e
# 02:15 Singapore time every night; keeps 14 days
15 18 * * * /home/securepay/csit321-secure-pay/deploy/backup/backup.sh >> /home/securepay/backup.log 2>&1
# Sunday 03:30 Singapore time: prove the newest backup restores (sprint 16)
30 19 * * 6 /home/securepay/csit321-secure-pay/deploy/backup/verify.sh >> /home/securepay/backup.log 2>&1
```

Backups never hold card data: `backup.sh` dumps the vault tables' definitions but not their
rows (a payment in progress at 2:15 needs its card entered again after a restore), and
`verify.sh` fails if a restored backup has a stored card in it. `verify.sh` restores each dump of the newest backup into a scratch database
(`restorecheck_gateway` and so on), counts tables and rows, and drops the scratch copies; the
live databases are not touched. `grep -E "ok|FAIL" ~/backup.log | tail` shows the last result.
A backup nobody has restored is only a hope; run it by hand after any change to the schema.

Copy them off the server now and then, and always the week of a demo (from a laptop):
`rsync -a securepay@203.0.113.5:fyp-backups/ ./fyp-backups/` (or `scp -r`).
A dump is only useful together with the secrets (step 4), which are not in it.
The `vault_encryption_key` and `field_encryption_key` secrets are master keys: the data keys
in the database are encrypted with them (rotate the data keys on the dashboard's Integrity and
keys page, at least every 90 days). Never regenerate those two files on a running server, or
card data in flight, signing secrets and queued emails can no longer be read. Restore one
database: `$P exec -T db pg_restore -U postgres --clean -d gateway < gateway.dump`.

**Server snapshot the day before a demo** (the whole disk: code, secrets, model, databases).
Run `deploy/backup/backup.sh` first so the dumps inside the snapshot are fresh, then:

- Google Cloud: Compute Engine > Disks > the VM's disk > **Create snapshot**, or
  `gcloud compute snapshots create securepay-$(date +%Y%m%d) --source-disk=securepay --source-disk-zone=<zone>`.

Restoring a snapshot makes a new disk; the IP stays because it is the reserved static one.

## 9a. Monitoring (sprint 16)

Two layers, because a server cannot report that it is down:

**Inside: `deploy/watchdog.sh`, every 5 minutes.** It checks that every container runs, the
gateway's `/readyz` (both databases answer and the worker's heartbeat is under 2 minutes old),
the shop's `/healthz`, disk (85 %), memory, the certificate (14 days) and the newest backup
(36 hours). A service that fails two runs in a row is restarted, at most once per 30 minutes
each and never during a deploy: that covers the worker loop hanging without exiting, which
Docker's restart policy cannot see. When the list of problems changes it posts to the team
chat, and once more when all is clear.

```bash
crontab -e
*/5 * * * * /home/securepay/csit321-secure-pay/deploy/watchdog.sh >> /home/securepay/watchdog.log 2>&1
```

Alerts need one of these in `deploy/.env` (they are secrets: never commit them):

- **Discord:** channel > Edit channel > Integrations > Webhooks > New webhook > Copy URL, then
  `ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/...`. A Slack incoming webhook URL works
  the same way.
- **Telegram:** make a bot with @BotFather (it gives the token), add the bot to the team
  group, send it a message, read the chat ID from
  `https://api.telegram.org/bot<token>/getUpdates`, then set `ALERT_TELEGRAM_BOT_TOKEN=` and
  `ALERT_TELEGRAM_CHAT_ID=` (a group's ID starts with `-`).

`bash deploy/watchdog.sh --test-alert` sends one test message; `bash deploy/watchdog.sh
--check` only reports (no restart, no alert). `tail ~/watchdog.log` shows the history. Delete
`~/.securepay-watchdog/*.restarted` to allow an immediate second restart.

**Outside: a free uptime monitor** (Fifa, once; nothing to install). UptimeRobot's free plan
checks every 5 minutes and emails, or pushes to the same Discord/Slack/Telegram, when a check
fails twice:

1. Sign up at uptimerobot.com with a team address.
2. Add two **HTTP(s)** monitors, interval 5 minutes:
   `https://gateway.<domain>/readyz` (fails with 503 when the worker or a database is down)
   and `https://shop.<domain>/healthz`.
3. Alert contacts: the team email, and the Discord/Slack webhook or Telegram if you set one up.
4. Optional: a public status page with the two monitors, to show at the demo.

After a move to a new domain (section 13 or 13a), change the two monitor URLs. A GitHub Actions
schedule could do the same checks, but every 5 minutes it would use more than the private
repository's free Actions minutes, so it is not used.

## 10. Updating after a merge

**Automatic (set up once):** after every merge to `main`, once CI passes, GitHub Actions
(`.github/workflows/deploy.yml`) signs in to the server and runs `deploy/auto-deploy.sh` for the
exact commit CI tested. That script fast-forwards the clone to that commit (never to a newer
`main` that has not passed its own checks, and never back to an older one), rebuilds with every
image labelled with the commit, checks that every app container runs an image built from it,
removes old image layers and runs the smoke check (up to 3 minutes while migrations run). The
commit that is live is in `~/deployed-revision`. The Actions tab shows the result, and
`~/deploy.log` on the server keeps every run. A run started by hand (Actions > deploy > Run
workflow) takes an optional commit and refuses one whose CI run on `main` did not pass.

Set-up, on the server as `securepay`:

```bash
cd ~/csit321-secure-pay && git pull
bash deploy/setup-auto-deploy.sh
```

It prints three values. On GitHub, open the repository's Settings > Secrets and variables >
Actions, and add the secret `DEPLOY_SSH_KEY` and the variables `DEPLOY_HOST` and
`DEPLOY_KNOWN_HOSTS` exactly as printed. Then try it: Actions tab > **deploy** > **Run
workflow**. Until `DEPLOY_HOST` is set the workflow skips itself.

What the GitHub key can do: the script adds it to `~/.ssh/authorized_keys` as
`restrict,command="... auto-deploy.sh"`, so it gets no shell, no file copy and no port
forwarding. The only command it accepts is `deploy <full commit>` for a commit already on
`main`; anything else is refused. If it leaks, the worst case is a deploy of a commit on `main`; replace it with
`ROTATE=1 bash deploy/setup-auto-deploy.sh` and update the secret.

What it does not change: anyone who can merge to `main` decides what runs on the server, by
hand or automatically (the compose file and these scripts are in the repository). Keep `main`
changing only through reviewed pull requests with CI green.

A deploy stops without changing anything running if the server clone is not on `main` or has
hand edits that clash with the new code (`git status` shows them). If the smoke check fails
after a deploy, the new code is running: look at `docker compose -f deploy/compose.prod.yaml
logs --tail 100 <service>`, then fix forward with a new PR, or go back by hand:
`git checkout <previous commit>` and `up -d --build` (the previous commit is in
`~/deploy.log`; return with `git checkout main` once fixed). Migrations are not undone.

**By hand** (or if Actions is down):

```bash
bash ~/csit321-secure-pay/deploy/auto-deploy.sh             # the newest main
bash ~/csit321-secure-pay/deploy/auto-deploy.sh <commit>    # one commit on main
```

A hand run is your own sign-off: run the checks for that commit first (CI, or locally while
Actions minutes are used up). Images are rebuilt on the server, so a deploy can pick up a newer
`python:3.12-slim` or a newer package within the version ranges in `pyproject.toml`; the
revision check proves the code, not every dependency.

Migrations run when the gateway, simulator and shop start. The integration tests are not part
of a deploy because they make payments; run them by hand when a change touches the payment flow
(step 8).

## 10a. Merge freeze before a demo (sprint 16)

Auto-deploy restarts the stack on every merge, so nothing merges to `main` in the 48 hours
before a demo. Two switches, use both:

1. **GitHub** (stops people merging and stops the deploy workflow): Settings > Secrets and
   variables > Actions > Variables > New repository variable `MERGE_FREEZE_UNTIL`, value a
   date and time with its zone, for example `2027-04-02T18:00+08:00`. While it is in the
   future, every pull request shows a red **ci-ok** check (the `changes` job says "Merge
   freeze for a demo ... Do not merge") and the
   deploy workflow fails without touching the server. Delete the variable, or let the time
   pass, to end it. (Branch protection would enforce it, but the free private plan does not
   have it.)
2. **Server** (works even if the variable is forgotten): `bash deploy/freeze.sh on` (48 hours;
   `on 72`, or `until "2027-04-02 18:00"` in Singapore time). `auto-deploy.sh` refuses to
   deploy until then. `bash deploy/freeze.sh status` shows it and `off` ends it early.

A merge made during the freeze is deployed by the next merge after it, or by hand
(`freeze.sh off`, then `auto-deploy.sh`, or Actions > deploy > Run workflow).

## 11. Demo story S4 with the fault controls

The fault controls are on (`SIM_TEST_CONTROLS=1`, decided 14 Nov 2026) but only reachable
inside the server, with `simulator_test_control_key`. The test cards `4000 0000 0000 0119`,
`...0127` and `...0135` show S4 without them. To add a rule by hand:

```bash
docker run --rm --network deploy_gateway -v deploy_caddy_ca:/ca:ro \
  -e KEY="$(cat deploy/secrets/simulator_test_control_key)" curlimages/curl sh -c \
  'curl -s --cacert /ca/root.crt https://simulator.securepay.internal:8443/sim/faults \
     -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d "{\"match\": {\"operation_type\": \"capture\"}, \"action\": \"drop_response\", \"remaining\": 1}"'
```

(`DELETE` on the same URL clears all rules.) Before the M8 demo, make a new key:
`rm deploy/secrets/simulator_test_control_key && bash deploy/make-secrets.sh && $P up -d simulator`.
Never put the key on the website or in slides. `SIM_TEST_CONTROLS=0` in `deploy/.env` turns
the controls off.

## 11a. Demo day (Volt & Co.)

The demo shop plays **Volt & Co.**, a fictional gadget store. Once, after the deploy that
brings it, give the merchant its new name (the payment page, receipts and dashboard show it):

```bash
$P exec gateway python manage.py demo_check --merchant mer_... --rename "Volt & Co."
```

The full demo-day timeline (freeze, snapshot, reset, preflight, fallbacks, rehearsals) is in
[`docs/DEMO-DAY.md`](../docs/DEMO-DAY.md). On the morning of a demo and again an hour before,
run one command:

```bash
bash deploy/demo.sh reset
```

For the dashboard's Fraud insights charts, run real traffic first (about 55 payments: ordinary,
declined, step-up, block list, a card-testing burst; nothing is written to the database
directly). `--minutes 90` spreads them so "Last 24 hours" shows several hours; run it on a few
days before the demo to fill "Last 7 days". It must finish before `reset`, which empties the
inbox of the step-up code emails it sends:

```bash
nohup bash deploy/demo.sh traffic --minutes 90 > traffic.log 2>&1 &
```

Then, an hour before, `bash deploy/demo.sh preflight`: deploy freeze, watchdog, smoke check,
one real test payment through the shop with a fresh card, and `demo_check`; it ends with
**READY** or **NOT READY** and what failed.

It does steps 1 to 4 below by itself and prints today's cards and emails; copy them onto the
cheat sheet. Exit code 1 means a health check FAILed. It deletes no payments, screening
records or audit events (they stay as evidence); fresh cards and emails are what make every
run behave the same.

1. **Stock:** paid orders take items off the shelf and a product at 0 shows "Sold out", so
   it puts everything back (`$P exec merchant python manage.py restock`, 25 of each). To show
   the low-stock label on purpose afterwards: `restock --sku HEAD-01 --to 3`.
2. **Mailpit:** it empties the demo inbox so the demo emails are easy to find.
3. **Fresh cards and emails:** it prints one new card per scene from the simulator's demo
   ranges (`$P exec simulator python manage.py new_demo_card --set`; SIMULATOR-CONTRACT.md
   section 5): approve cards for S1 to S3, a lost-response card for S4 and a spare decline.
   They have no screening history, unlike `4242 4242 4242 4242` or `4000 0000 0000 0119`
   after weeks of rehearsals. It also prints new `@example.com` addresses (`mei.<stamp>@...`),
   so the email history is empty too. The team keeps the fixed cards for testing.
4. **Health:** `demo_check` (it finds the merchant named Volt & Co.; `bash deploy/demo.sh
   reset --merchant mer_...` picks another). Every line should be PASS; fix any FAIL (the
   line says what to look at) and close open security alerts so the Security page starts
   clean.
5. **Card testing (S3) from another network:** screening also counts attempts per IP for an
   hour, so leave an hour between the last rehearsal and the demo, and run the "fraudster"
   step from a phone hotspot, not the presenter's laptop.
6. **No merges** to `main` in the 48 hours before the demo: auto-deploy would restart the
   stack. Turn on both freeze switches (section 10a).

**Fresh stack (fallback laptop or a brand-new server):** after the stack is up (README quick
start steps 1 to 3, or RUNBOOK steps 1 to 6), `bash deploy/demo.sh seed` does step 7 in one
go: it creates the Volt & Co. merchant with its webhook URL, the three staff logins
(`ops@demoshop.sg`, `analyst@securepay.sg`, `admin@securepay.sg`, temporary passwords printed
once) and the risk lists, puts the API key and signing secret into the shop's secrets and
restarts the shop. On a stack that already has them it changes nothing, so it is safe to run
again. It does not invent past payments: the dashboard shows only what really went through.

## 12. When something is wrong

| Symptom | Look at |
| --- | --- |
| Browser shows a certificate error | `logs caddy`: port 80 blocked, or wrong `DOMAIN` in `deploy/.env` |
| Every payment Blocked, `screening_unavailable` | `logs gateway`: model folder or `RISK_MODEL_VERSION` wrong (step 5) |
| A service restarts over and over | `logs <service>`: usually a missing secret file (run `make-secrets.sh` again) |
| Orders stay unpaid | `logs gateway-worker` (webhook delivery) and `logs merchant` |
| `/readyz` says `"worker"`, no emails | The worker loop is stuck or down: `restart gateway-worker` (the watchdog does this after 10 minutes), then `logs gateway-worker` |
| Watchdog alert you do not understand | `tail -50 ~/watchdog.log`; `bash deploy/watchdog.sh --check` for the state now |
| Server slow or out of memory | `free -h`, `docker stats`; on Google Cloud, stop the VM, change the machine type (e2-standard-2, 8 GB) and start it (the static IP stays) |
| Pages time out from outside | Google Cloud: the VM's "Allow HTTP/HTTPS traffic" boxes (network tags `http-server`, `https-server`); then `sudo ufw status` |
| Need the Django admin for a one-off | Use `manage.py shell` through `$P exec` instead; the admin stays off on the public server |

## 13a. New domain, same server (19 Nov 2026: securepaysg.me)

The server stays where it is (Google Cloud through M6, Fifa's hosting decision of 19 Nov 2026);
only the names change, from `*.35-213-144-96.sslip.io` to `*.securepaysg.me`. Nothing is
copied and nothing in the databases changes except the shop's webhook URL.
`deploy/change-domain.sh` does steps 2 and 3.

**1. DNS (Fifa, at Namecheap).** Domain List > `securepaysg.me` > **Manage** > **Advanced DNS**.
Under Host Records, delete the parking records Namecheap adds (`CNAME www
parkingpage.namecheap.com` and the `URL Redirect @` record), then add:

| Type | Host | Value | TTL |
| --- | --- | --- | --- |
| A Record | `gateway` | `35.213.144.96` | 5 min |
| A Record | `shop` | `35.213.144.96` | 5 min |
| A Record | `mail` | `35.213.144.96` | 5 min |

Wait until `dig +short gateway.securepaysg.me` (and `shop.`, `mail.`) prints `35.213.144.96`
from a laptop; Namecheap usually takes 5 to 30 minutes. The bare `securepaysg.me` and `www`
are not used (the website stays on Vercel). The mail records come in section 13b.

**2. Code.** Merge the pull request that adds `change-domain.sh`, then on the server
`bash ~/csit321-secure-pay/deploy/auto-deploy.sh` (while GitHub Actions minutes are used up).

**3. Switch, on the server** (about 3 minutes; checkout is down for under a minute while the
apps restart):

```bash
cd ~/csit321-secure-pay
bash deploy/change-domain.sh securepaysg.me
```

It refuses to start until all three names point at this server (so Let's Encrypt is not
asked for certificates it cannot issue). Then it sets `DOMAIN=securepaysg.me` and
`OLD_DOMAIN=35-213-144-96.sslip.io` in `deploy/.env` (a copy of the old file stays as
`deploy/.env.before-securepaysg.me`), rebuilds and restarts the stack, Caddy gets the new
certificates, `manage.py change_domain` points the demo shop's webhook URL at
`shop.securepaysg.me` (audited as `merchant.webhook_url_moved`), and the smoke check runs on
the new names. The old names answer with a 308 redirect to the same path on the new ones, so
links already shared (and the old webhook URL of any other merchant) keep working.

**4. After it** (Fifa):

- `bash deploy/demo.sh preflight` on the server: one real payment, receipt in
  `https://mail.securepaysg.me`.
- UptimeRobot: change the two monitor URLs (section 9a).
- Vercel project settings > Environment Variables: `VITE_GATEWAY_URL=https://gateway.securepaysg.me`
  and `VITE_SHOP_URL=https://shop.securepaysg.me`, then redeploy (the code's fallback is the
  new name already).
- Claude cloud environment: add `gateway.securepaysg.me`, `shop.securepaysg.me` and
  `mail.securepaysg.me` to the allowed domains, so Claude sessions can test the live server.
- Tell the team and update shared links and bookmarks. Automatic deploys need nothing: they
  sign in by IP.
- In a few weeks, drop the redirects: set `OLD_DOMAIN=` in `deploy/.env`, then
  `docker compose -f deploy/compose.prod.yaml up -d caddy`.

To go back: `bash deploy/change-domain.sh 35-213-144-96.sslip.io --drop-old`.

## 13b. Real email (provider relay, Mailpit kept)

Decided by Fifa on 18 Nov 2026: once the domain exists, emails go to real inboxes through a
provider, with Mailpit kept as the switchable fallback for demo day.

How it works: the apps keep sending every email to Mailpit, unchanged, so the demo inbox at
`https://mail.<domain>` still shows everything. When `MAIL_RELAY_HOST` is set in
`deploy/.env`, Mailpit also passes a copy of each email whose recipient matches
`MAIL_RELAY_MATCHING` to the provider, which delivers it as `SecurePay
<no-reply@securepaysg.me>`. Made-up demo addresses (`example.com`, `demoshop.sg`,
`securepay.sg`, `.test`) are never relayed (`MAIL_RELAY_BLOCKED` in `compose.prod.yaml`), so
the provider sees no bounces. In the Mailpit page, an email can also be sent on by hand with
**Release**.

**1. Provider account (Fifa).** Resend is suggested (free plan: 3,000 emails a month, 100 a
day, one domain; SMTP with the API key as password). Brevo's free plan (300 a day) works the
same way. Sign up with a team address.

**2. Domain and DNS.** Resend > Domains > **Add domain** `securepaysg.me`: region Tokyo
(`ap-northeast-1`, the closest), Custom Return-Path `send`, click and open tracking **off**
(click tracking would rewrite the links in reset and verification emails). It then shows four
records (19 Nov 2026). **Go to Namecheap** can add them for you; by hand, at Namecheap >
Advanced DNS, copy each value in full from Resend (the page shortens them with `[...]`):

| Type | Host | Value | Why |
| --- | --- | --- | --- |
| TXT Record | `resend._domainkey` | `p=MIGfMA...QIDAQAB` (from Resend) | DKIM: signs every email |
| CNAME Record | `rsend` | `rsend-ap...mta.net` (from Resend) | SPF for the return address |
| CNAME Record | `send` | `send.for...mta.net` (from Resend) | Return-Path: bounces go back to Resend |
| TXT Record | `_dmarc` | `v=DMARC1; p=none;` | DMARC. Change to `p=quarantine` once mail is seen to pass |

Host without `.securepaysg.me` (Namecheap adds it), TTL Automatic, "Enable receiving" off.
Then **I've already added the records** in Resend, and wait for Verified (usually minutes).

**3. API key.** Resend > API Keys > **Create**: permission **Sending access**, domain
`securepaysg.me` only. Copy it once (it is shown only then) into the team password manager.

**4. On the server**, add to `deploy/.env` (`nano deploy/.env`):

```bash
MAIL_RELAY_HOST=smtp.resend.com
MAIL_RELAY_PORT=587
MAIL_RELAY_USERNAME=resend
MAIL_RELAY_PASSWORD=re_...           # the API key
MAIL_RELAY_MATCHING='.*'             # or only the team: '(?i)@(gmail\.com|uowmail\.edu\.au)$'
```

then `docker compose -f deploy/compose.prod.yaml up -d mailpit` and check
`docker compose -f deploy/compose.prod.yaml logs mailpit | grep relay`: it prints the
"auto-relaying new messages to recipients matching" line. Make a payment with your own email
at the demo shop (or reset your staff password): the code lands in your inbox and in
Mailpit. Gmail's **Show original** should say SPF, DKIM and DMARC: PASS.

Real people need real addresses: staff and customer accounts made with `example.com` or
`securepay.sg` addresses only get their email in Mailpit. Make demo accounts with the
team's own addresses where a real inbox is wanted on the day.

**Fallback (demo day, or when the free quota runs out):** set `MAIL_RELAY_HOST=` in
`deploy/.env` and `docker compose -f deploy/compose.prod.yaml up -d mailpit`. Everything
keeps working; emails are then only in Mailpit, as before. Recreating Mailpit empties the
demo inbox (it keeps messages in memory), so switch before `demo.sh reset`, not after.

## 13. Moving to a new server or domain

Sprint 12 kit. The domain part is done: on 19 Nov 2026 the live server moved from `sslip.io` to
`securepaysg.me` with `change-domain.sh` (section 13a), on the same Google Cloud VM. Moving to
another server is not planned (the demo stays on Google Cloud through M6); this section is kept
as the fallback if the VM ever has to change. `deploy/move-server.sh` carries everything that matters:
the three databases, every secret (including the vault and field master keys, without which
the copied data cannot be read), `deploy/.env` and the fraud model folder. Payments, refunds,
staff accounts with their TOTP, merchants and their API keys, audit log and integrity seals,
screening history and shop orders all come across unchanged.

Not carried over: Mailpit messages (the demo inbox starts empty), certificates (Caddy gets new
ones), the GitHub deploy key (made again in step 6 below).

**1. Domain (Fifa, once).** Redeem the domain from the GitHub Student Developer Pack (for
example a free `.me` from Namecheap or a `.tech`/`.live` from get.tech). In its DNS settings
add three **A records**, `gateway`, `shop` and `mail`, pointing at the new server's IPv4 (or
one `*` record). TTL 5 minutes while moving. Check from a laptop:
`dig +short gateway.<domain>` prints the new IP.

**2. New server.** Steps 1 to 3 above on the new VM ( `server-setup.sh`, code for
`securepay`). Stop before step 4: the secrets come from the old server.

**3. Export, on the old server** (stops the apps there; the database stays up for the copy):

```bash
cd ~/csit321-secure-pay && git pull
bash deploy/move-server.sh export
```

It asks for a passphrase twice (put it in the team password manager) and writes one encrypted
file, `~/securepay-move-<time>.tar.gz.enc`. From the laptop, pass it across:

```bash
scp securepay@<old-ip>:securepay-move-*.tar.gz.enc .
scp securepay-move-*.tar.gz.enc securepay@<new-ip>:
```

**4. Import, on the new server:**

```bash
cd ~/csit321-secure-pay
bash deploy/move-server.sh import ~/securepay-move-<time>.tar.gz.enc <new-domain>
```

It refuses to run on a server that already has secrets or a database. It restores the
databases into a fresh volume, starts the stack and runs
`manage.py change_domain --from <old> --to <new>`, which points the demo shop's webhook URL at
`shop.<new-domain>` (audited as `merchant.webhook_url_moved`). Without a new domain it keeps
the old one (a move with the same name, for example after DNS changes).

**5. Check:** `bash deploy/smoke-check.sh <new-domain>` from a laptop (all ok once Caddy has
its certificates; `logs caddy` shows them), then `bash deploy/demo.sh preflight` on the new
server (watchdog, smoke check, one real payment with a fresh demo card, `demo_check`), and
look for the receipt in `https://mail.<new-domain>`.

**6. Repoint automatic deploys:** on the new server `bash deploy/setup-auto-deploy.sh`, then
on GitHub replace `DEPLOY_SSH_KEY`, `DEPLOY_HOST` and `DEPLOY_KNOWN_HOSTS` with the printed
values. Until then a merge to `main` deploys to the old server. Add the crontab lines for
the backup and its weekly restore test (step 9) and the watchdog (section 9a); the alert
settings came across in `deploy/.env`, so `bash deploy/watchdog.sh --test-alert` should reach
the team chat. Change the two uptime monitor URLs to the new domain.

**7. Tidy up:** update the "Current server" line at the top of this file and the website's
`VITE_GATEWAY_URL` (Vercel project settings; `frontend/website/src/content/site.ts` holds the
fallback). Delete the move file from the laptop and both servers. Keep the old server stopped
(`docker compose -f deploy/compose.prod.yaml down`, no `-v`) for a few days as a fallback,
then delete the old VM and release its static IP so it stops being billed.

To go back during the move: on the old server `docker compose -f deploy/compose.prod.yaml up -d`.
