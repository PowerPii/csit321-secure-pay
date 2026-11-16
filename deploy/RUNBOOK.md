# Running SecurePay on the public server

Sprint 9: the whole stack on one Ubuntu server in Fifa's account: an Oracle Cloud Always Free
VM for now, or a DigitalOcean droplet on Student Pack credit (both covered below), with free
`sslip.io` names and Let's Encrypt certificates. The marketing website stays on
Vercel and does not link here (decided 14 Nov 2026). Share the addresses with the team and
assessors directly.

| Name | What | Who |
| --- | --- | --- |
| `https://gateway.<domain>` | Merchant API, hosted checkout (`/pay/...`), guest status (`/guest/status`), staff dashboard (`/dashboard/`) | Public; the dashboard needs a staff account with TOTP |
| `https://shop.<domain>` | Demo shop | Public |
| `https://mail.<domain>` | Demo inbox (Mailpit): verification codes, receipts, guest status codes | Team and assessors (basic auth) |
| `simulator.securepay.internal:8443` | Payment simulator, including its fault controls | Inside the server only |

`<domain>` is the droplet's IPv4 with dashes plus `.sslip.io`: for `203.0.113.5` it is
`203-0-113-5.sslip.io`. The names follow the IP, so keep it stable: a DigitalOcean droplet
keeps its IP until it is destroyed; on Oracle, use a reserved public IP. Moving to another
server later means new names, which is fine because nothing public links here.

What is different from the local stack (`compose.yaml`): `DJANGO_DEBUG=0`; the Django admin is
off in every service and Caddy answers `/admin*` with 404; the simulator has no public name
(Caddy serves it on port 8443, which is not published); the gateway's block on private
webhook addresses is fully on, so the worker reaches the shop at its public address like any
merchant; Mailpit is behind basic auth; the checkout and dashboard bundles are built into the
Caddy image (no Node.js on the server); container logs are capped at 50 MB each.

## 1. Create the server (Fifa, once)

Either option; the rest of the runbook is the same. Signing in below uses `ubuntu@` on Oracle
and `root@` on DigitalOcean for step 2 only, and `securepay@` from then on.

**Oracle Cloud Always Free (for now)**

1. Sign up with **home region Singapore** (it cannot be changed, and Always Free VMs only run
   in the home region). Then upgrade the account to **Pay As You Go**: it stays free within the
   Always Free limits, and Oracle no longer reclaims a mostly idle free VM after 7 days.
2. Create an instance: image **Canonical Ubuntu 24.04**, shape **VM.Standard.A1.Flex (Arm)**
   with **2 OCPU / 12 GB**, your laptop's SSH public key. "Out of capacity" means try another
   availability domain, or again later.
3. Networking > the instance's VNIC > IPv4 addresses: change the public IP to a **reserved**
   public IP (free).
4. The VCN's security list (or a network security group): add ingress rules from `0.0.0.0/0`
   for **TCP 80**, **TCP 443** and **UDP 443**. SSH 22 is there by default.

Every image in the stack runs on Arm (Postgres, Caddy, Mailpit, Python and Node have Arm
builds, and the Python packages have Arm wheels), and the model file loads the same way.

**DigitalOcean (Student Pack)**

1. Redeem the DigitalOcean offer in the GitHub Student Developer Pack (benefits arrive 72 hours
   after academic approval).
2. Create a droplet: **Ubuntu 24.04 LTS x64**, region **Singapore (SGP1)**, Basic, Regular,
   **2 vCPU / 4 GB RAM** (about US$24 a month, paid from the credit), authentication **SSH key**,
   free monitoring on. Its public IPv4 is all you need; no reserved IP.

## 2. Set up the server (once)

```bash
ssh ubuntu@203.0.113.5      # Oracle;  DigitalOcean: ssh root@203.0.113.5
curl -fsSL https://raw.githubusercontent.com/PowerPii/csit321-secure-pay/main/deploy/server-setup.sh -o setup.sh
less setup.sh               # read it first
sudo bash setup.sh
```

It installs security updates (and turns on daily automatic ones), Docker with the Compose
plugin, a `securepay` user that signs in with the same SSH key, SSH with keys only and no root
sign-in, a firewall with only 22, 80 and 443 open, and 2 GB of swap. On Oracle it also replaces
the image's own reject-all iptables rules with that firewall, and puts the reserved public IP
on the loopback interface so containers can reach the server's own public names (the worker's
webhooks to the shop). **Before closing the first session**, check in a second terminal that `ssh securepay@203.0.113.5` works.

Team members get access by adding their public key to `/home/securepay/.ssh/authorized_keys`.

## 3. Get the code

```bash
ssh securepay@203.0.113.5
git clone https://github.com/PowerPii/csit321-secure-pay.git
cd csit321-secure-pay
```

If the repository is private: `ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N ""`, add
`~/.ssh/deploy_key.pub` as a **read-only deploy key** (repository Settings > Deploy keys), then
`GIT_SSH_COMMAND="ssh -i ~/.ssh/deploy_key" git clone git@github.com:PowerPii/csit321-secure-pay.git`
and `git config core.sshCommand "ssh -i ~/.ssh/deploy_key"` inside the clone.

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

and set `RISK_MODEL_VERSION=hgb-fs02-2026-11-13` in `deploy/.env`. Left empty, the stub model
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

Staff emails (lockout notices) go to the demo inbox, like everything else.

## 8. Check it

From a laptop:

```bash
bash deploy/smoke-check.sh 203-0-113-5.sslip.io
```

It checks the health endpoint, the checkout, guest status and dashboard pages, that `/admin/`
is 404 on the gateway and the shop, that the API needs a key, that the inbox needs a password,
HTTP to HTTPS, the security headers, and that the simulator does not answer from outside.

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
A dump is only useful together with the secrets (step 4), which are not in it. Restore one
database: `$P exec -T db pg_restore -U postgres --clean -d gateway < gateway.dump`.

## 10. Updating after a merge

```bash
cd ~/csit321-secure-pay && git pull
docker compose -f deploy/compose.prod.yaml up -d --build
bash deploy/smoke-check.sh <domain>    # from a laptop
```

Migrations run when the gateway, simulator and shop start.

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
| Server slow or out of memory | `free -h`, `docker stats`; a droplet can be resized up without losing its IP; an Oracle A1 VM can grow to 4 OCPU / 24 GB within the free limits |
| Oracle: pages time out from outside | The security list rules for 80/443 (step 1), then `sudo ufw status` |
| Need the Django admin for a one-off | Use `manage.py shell` through `$P exec` instead; the admin stays off on the public server |
