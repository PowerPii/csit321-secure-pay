# Production Caddy image: builds the checkout page and staff dashboard bundles, so the server
# needs no Node.js. Built from the repository root by deploy/compose.prod.yaml.
FROM node:22-slim AS frontend
WORKDIR /src
COPY frontend/checkout ./frontend/checkout
COPY frontend/dashboard ./frontend/dashboard
RUN cd frontend/checkout && npm ci && npm run build
RUN cd frontend/dashboard && npm ci && npm run build

FROM caddy:2
COPY --from=frontend /src/frontend/checkout/dist /srv/checkout
COPY --from=frontend /src/frontend/dashboard/dist /srv/dashboard
COPY deploy/Caddyfile.prod /etc/caddy/Caddyfile
