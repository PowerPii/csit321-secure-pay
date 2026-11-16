# Running SecurePay on the public server

Sprint 9: the whole stack on one Ubuntu server in Fifa's account: a Google Cloud VM on the
free trial for now (chosen 16 Nov 2026), then a DigitalOcean droplet on Student Pack credit
before the trial ends (both covered below), with free
`sslip.io` names and Let's Encrypt certificates. The marketing website stays on
Vercel and does not link here (decided 14 Nov 2026). Share the addresses with the team and
assessors directly.

**Current server (16 Nov 2026):** Google Cloud project `securepay-demo`, VM `securepay`
(e2-medium, asia-southeast1), static IP `35.213.144.96`, domain `35-213-144-96.sslip.io`.
First deploy: all smoke checks and all 11 integration tests passed on it.
Automatic deploys are on (step 10) since 16 Nov 2026: the first run from GitHub Actions passed
its smoke check.

| Name | What | Who |
| --- | --- | --- |
| `https://gateway.<domain>` | Merchant API, hosted checkout (`/pay/...`), guest status (`/guest/status`), staff dashboard (`/dashboard/`) | Public; the dashboard needs a staff account with TOTP |
| `https://shop.<domain>` | Demo shop | Public |
| `https://mail.<domain>` | Demo inbox (Mailpit): verification codes, receipts, guest status codes | Team and assessors (basic auth) |
| `simulator.securepay.internal:8443` | Payment simulator, including its fault controls | Inside the server only |

`<domain>` is the droplet's IPv4 with dashes plus `.sslip.io`: for `203.0.113.5` it is
`203-0-113-5.sslip.io`. The names follow the IP, so keep it stable: a DigitalOcean droplet
keeps its IP until it is destroyed; on Google Cloud, reserve a static external IP. Moving to another
server later means new names, which is fine because nothing public links here.

What is different from the local stack (`compose.yaml`): `DJANGO_DEBUG=0`; the Django admin is
off in every service and Caddy answers `/admin*` with 404; the simulator has no public name
(Caddy serves it on port 8443, which is not published); the gateway's block on private
webhook addresses is fully on, so the worker reaches the shop at its public address like any
merchant; Mailpit is behind basic auth; the checkout and dashboard bundles are built into the
Caddy image (no Node.js on the server); container logs are capped at 50 MB each.

## 1. Create the server (Fifa, once)

Either option; the rest of the runbook is the same. For step 2 only, sign in as your own
Google Cloud user (`fifa@` below) or as `root@` on DigitalOcean; from then on as `securepay@`.

**Google Cloud free trial (now, until about mid-February 2027)**

The trial gives US$300 for 90 days. When it ends the VM stops unless the account is upgraded,
so move to DigitalOcean before then (copy the backups and secrets; the names change with the IP).

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

**DigitalOcean (Student Pack)**

1. Redeem the DigitalOcean offer in the GitHub Student Developer Pack (benefits arrive 72 hours
   after academic approval).
2. Create a droplet: **Ubuntu 24.04 LTS x64**, region **Singapore (SGP1)**, Basic, Regular,
   **2 vCPU / 4 GB RAM** (about US$24 a month, paid from the credit), authentication **SSH key**,
   free monitoring on. Its public IPv4 is all you need; no reserved IP.

## 2. Get the code and set up the server (once)

The repository is private, so the server gets a **read-only deploy key** for it (a public
`raw.githubusercontent.com` download answers 404). Sign in as your own user first:

```bash
ssh fifa@203.0.113.5        # Google Cloud: the name in your SSH key's comment; DigitalOcean: root@
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
nano deploy/.env      # DOMAIN=203-0-113-5.sslip.io and ACME_EMAIL=<a team address>
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
  within seconds. (The worker calls `shop.<domain>` at the droplet's public IP, which Docker
  routes back to Caddy. If orders stay unpaid, look at `logs gateway-worker`.)
- **The gateway sees real client IPs** (velocity rules use them). After a payment, the
  screening decision on the payment's dashboard page shows your own IP, not a `172.x` one.

## 9. Backups

```bash
crontab -e
# 02:15 Singapore time every night; keeps 14 days
15 18 * * * /home/securepay/csit321-secure-pay/deploy/backup/backup.sh >> /home/securepay/backup.log 2>&1
```

Copy them off the server now and then (from a laptop): `scp -r securepay@203.0.113.5:fyp-backups ./`.
A dump is only useful together with the secrets (step 4), which are not in it.
The `vault_encryption_key` and `field_encryption_key` secrets are master keys: the data keys
in the database are encrypted with them (rotate the data keys on the dashboard's Integrity and
keys page, at least every 90 days). Never regenerate those two files on a running server, or
card data in flight, signing secrets and queued emails can no longer be read. Restore one
database: `$P exec -T db pg_restore -U postgres --clean -d gateway < gateway.dump`.

## 10. Updating after a merge

**Automatic (set up once):** after every merge to `main`, once CI passes, GitHub Actions
(`.github/workflows/deploy.yml`) signs in to the server and runs `deploy/auto-deploy.sh`. That
script fast-forwards the clone to `main`, rebuilds and restarts what changed, removes old image
layers and runs the smoke check (up to 3 minutes while migrations run). The Actions tab shows
the result, and `~/deploy.log` on the server keeps every run.

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
forwarding. Whatever command is asked for, it only deploys what is already on `main`. If it
leaks, the worst case is an extra deploy of `main`; replace it with
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
bash ~/csit321-secure-pay/deploy/auto-deploy.sh
```

Migrations run when the gateway, simulator and shop start. The integration tests are not part
of a deploy because they make payments; run them by hand when a change touches the payment flow
(step 8).

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

## 12. When something is wrong

| Symptom | Look at |
| --- | --- |
| Browser shows a certificate error | `logs caddy`: port 80 blocked, or wrong `DOMAIN` in `deploy/.env` |
| Every payment Blocked, `screening_unavailable` | `logs gateway`: model folder or `RISK_MODEL_VERSION` wrong (step 5) |
| A service restarts over and over | `logs <service>`: usually a missing secret file (run `make-secrets.sh` again) |
| Orders stay unpaid | `logs gateway-worker` (webhook delivery) and `logs merchant` |
| Server slow or out of memory | `free -h`, `docker stats`; a droplet can be resized up without losing its IP; on Google Cloud, stop the VM, change the machine type (e2-standard-2, 8 GB) and start it (the static IP stays) |
| Pages time out from outside | Google Cloud: the VM's "Allow HTTP/HTTPS traffic" boxes (network tags `http-server`, `https-server`); then `sudo ufw status` |
| Need the Django admin for a one-off | Use `manage.py shell` through `$P exec` instead; the admin stays off on the public server |
