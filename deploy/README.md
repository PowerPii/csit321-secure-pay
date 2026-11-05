# Deploy

- `compose.yaml`: the whole demo stack (Postgres 17, gateway, gateway worker, simulator, merchant, Caddy, Mailpit). Each trust domain has its own internal network; only Caddy publishes ports.
- `Caddyfile`: HTTPS with a local CA for `gateway.localhost`, `simulator.localhost`, `shop.localhost`, `mail.localhost`.
- `postgres/init/`: creates the gateway, simulator and merchant databases, their roles, and the vault schema with its own role.
- `secrets/`: templates for the Compose secret files.
- `backup/backup.sh`: `pg_dump` of all three databases.
