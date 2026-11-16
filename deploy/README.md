# Deploy

Local / demo stack:

- `compose.yaml`: the whole demo stack (Postgres 17, gateway, gateway worker, simulator, merchant, Caddy, Mailpit). Each trust domain has its own internal network; only Caddy publishes ports.
- `Caddyfile`: HTTPS with a local CA for `gateway.localhost`, `simulator.localhost`, `shop.localhost`, `mail.localhost`.

Public server (sprint 9), step by step in **[`RUNBOOK.md`](RUNBOOK.md)**:

- `compose.prod.yaml`: the same services with production settings (`DJANGO_DEBUG=0`, Django admin off, simulator private, webhooks to public addresses only, capped logs) and an on-demand `integration-tests` service.
- `Caddyfile.prod` + `caddy/Dockerfile`: Let's Encrypt for `gateway.`, `shop.` and `mail.<domain>` (sslip.io), Mailpit behind basic auth, `/admin*` answered with 404, and the private `:8443` sites for the simulator hop; the image carries the checkout and dashboard builds.
- `prod.env.example`: settings for `deploy/.env` on the server (domain, ACME email, model version, fault controls).
- `server-setup.sh`: one-time hardening of a fresh Ubuntu 24.04 server (Google Cloud, DigitalOcean or Oracle).
- `make-secrets.sh`: fresh secrets on the server and the demo inbox password.
- `smoke-check.sh`: checks the public server from outside.

Both:

- `postgres/init/`: creates the gateway, simulator and merchant databases, their roles, and the vault schema with its own role.
- `secrets/`: templates for the Compose secret files.
- `backup/backup.sh`: `pg_dump` of all three databases, 14 days kept.
