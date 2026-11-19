# Deploy

Local / demo stack:

- `compose.yaml`: the whole demo stack (Postgres 17, gateway, gateway worker, simulator, merchant, Caddy, Mailpit). Each trust domain has its own internal network; only Caddy publishes ports.
- `Caddyfile`: HTTPS with a local CA for `gateway.localhost`, `simulator.localhost`, `shop.localhost`, `mail.localhost`.

Public server (sprint 9), step by step in **[`RUNBOOK.md`](RUNBOOK.md)**:

- `compose.prod.yaml`: the same services with production settings (`DJANGO_DEBUG=0`, Django admin off, simulator private, webhooks to public addresses only, capped logs) and an on-demand `integration-tests` service. Mailpit can relay emails to a real provider (`MAIL_RELAY_*` in `.env`, RUNBOOK.md 13b).
- `Caddyfile.prod` + `caddy/Dockerfile`: Let's Encrypt for `gateway.`, `shop.` and `mail.<domain>` (`securepaysg.me` on the live server, or sslip.io), Mailpit behind basic auth, 308 redirects from `OLD_DOMAIN`'s names while moving (`caddy/old-domain.caddy.tmpl`), `/admin*` answered with 404, and the private `:8443` sites for the simulator hop; the image carries the checkout and dashboard builds.
- `prod.env.example`: settings for `deploy/.env` on the server (domain, ACME email, model version, fault controls).
- `server-setup.sh`: one-time hardening of a fresh Ubuntu 24.04 server (Google Cloud, DigitalOcean or Oracle).
- `make-secrets.sh`: fresh secrets on the server and the demo inbox password.
- `smoke-check.sh`: checks the public server from outside (`public-ip.sh` finds the server's IP for sslip.io or a real domain).
- `change-domain.sh`: moves the running stack to a new domain on the same server (checks DNS, sets `DOMAIN`/`OLD_DOMAIN`, restarts, moves webhook URLs, smoke check). RUNBOOK.md section 13a.
- `move-server.sh`: moves the stack to a new server and/or domain: `export` on the old server makes one encrypted file (databases, secrets, `.env`, fraud model), `import` on the new one restores it and moves the webhook URLs (`manage.py change_domain`). RUNBOOK.md section 13.
- `auto-deploy.sh`: updates the server to the latest `main` and runs the smoke check; GitHub Actions (`.github/workflows/deploy.yml`) runs it after CI passes on `main`.
- `setup-auto-deploy.sh`: one-time set-up of that: an SSH key locked to `auto-deploy.sh`, and the values to add in GitHub.
- `watchdog.sh` (sprint 16): cron every 5 minutes; checks containers, the gateway's `/readyz` (databases + worker heartbeat), the shop's `/healthz`, disk, memory, certificate and backup age; restarts a service that stays down; posts to the team chat (Discord/Slack webhook or Telegram). RUNBOOK.md section 9a.
- `freeze.sh` (sprint 16): deploy freeze before a demo; `auto-deploy.sh` refuses while it is on. The GitHub variable `MERGE_FREEZE_UNTIL` is the other half. RUNBOOK.md section 10a.
- `demo.sh`: `seed` a fresh stack with the Volt & Co. demo, `reset` it on demo mornings, `preflight` an hour before (READY / NOT READY). [`docs/DEMO-DAY.md`](../docs/DEMO-DAY.md).

Both:

- `postgres/init/`: creates the gateway, simulator and merchant databases, their roles, and the vault schema with its own role.
- `secrets/`: templates for the Compose secret files.
- `backup/backup.sh`: `pg_dump` of all three databases, 14 days kept. `backup/verify.sh` restores the newest one into scratch databases to prove it works (weekly cron).
