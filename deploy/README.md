# Deploy

Local / demo stack:

- `compose.yaml`: the whole demo stack (Postgres 17, gateway, gateway worker, simulator, merchant, Caddy, Mailpit). Each trust domain has its own internal network; only Caddy publishes ports.
- `Caddyfile`: HTTPS with a local CA for `gateway.localhost`, `simulator.localhost`, `shop.localhost`, `mail.localhost`.

Public server (sprint 9), step by step in **[`RUNBOOK.md`](RUNBOOK.md)**:

- `compose.prod.yaml`: the same services with production settings (`DJANGO_DEBUG=0`, Django admin off, simulator private, webhooks to public addresses only, capped logs) and an on-demand `integration-tests` service.
- `Caddyfile.prod` + `caddy/Dockerfile`: Let's Encrypt for `gateway.`, `shop.` and `mail.<domain>` (sslip.io or a real domain), Mailpit behind basic auth, `/admin*` answered with 404, and the private `:8443` sites for the simulator hop; the image carries the checkout and dashboard builds.
- `prod.env.example`: settings for `deploy/.env` on the server (domain, ACME email, model version, fault controls).
- `server-setup.sh`: one-time hardening of a fresh Ubuntu 24.04 server (Google Cloud, DigitalOcean or Oracle).
- `make-secrets.sh`: fresh secrets on the server and the demo inbox password.
- `smoke-check.sh`: checks the public server from outside (`public-ip.sh` finds the server's IP for sslip.io or a real domain).
- `move-server.sh`: moves the stack to a new server and/or domain: `export` on the old server makes one encrypted file (databases, secrets, `.env`, fraud model), `import` on the new one restores it and moves the webhook URLs (`manage.py change_domain`). RUNBOOK.md section 13.
- `auto-deploy.sh`: updates the server to the latest `main` and runs the smoke check; GitHub Actions (`.github/workflows/deploy.yml`) runs it after CI passes on `main`.
- `setup-auto-deploy.sh`: one-time set-up of that: an SSH key locked to `auto-deploy.sh`, and the values to add in GitHub.

Both:

- `postgres/init/`: creates the gateway, simulator and merchant databases, their roles, and the vault schema with its own role.
- `secrets/`: templates for the Compose secret files.
- `backup/backup.sh`: `pg_dump` of all three databases, 14 days kept.
