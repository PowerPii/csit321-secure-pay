# SecurePay website

Public marketing site for SecurePay: Home, Product, Developers, Security, Pricing, About, Contact, Status, Privacy and Terms. Vite + React + TypeScript + MUI, React Router. It is a static site, so it can be deployed on its own (Vercel). The only call to the gateway is the Status page (`/status`), which reads the public `GET /status.json` every 60 seconds and says "We can't reach SecurePay" when that fails. The Developers pages (`/developers` guides with the SDK section, `/developers/api` reference and `/developers/api/explorer`, the interactive OpenAPI reference served from `public/openapi/`) only link to the live gateway for merchant sign-up.

```bash
npm install
npm run dev      # http://localhost:5175
npm run build    # type-check and build to dist/
```

## Deploying on Vercel

| Setting | Value |
| --- | --- |
| Root Directory | `frontend/website` |
| Framework Preset | Vite (picked up from `vercel.json`) |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | `npm install` (default) |
| Node.js version | 20.x or newer |

`vercel.json` rewrites every path to `index.html` so routes like `/pricing` work on reload, and adds basic security headers.

Optional environment variable: `VITE_CONTACT_EMAIL`. When set, the contact form opens the visitor's email app addressed to it. When unset, the form points visitors to GitHub issues instead.

Optional environment variable: `VITE_GATEWAY_URL` (default `https://gateway.securepaysg.me`). The developer docs use it for the base URL in code samples and the sign-up and dashboard links. Set it in Vercel when the server moves, then redeploy.

## Content

Product facts (limits, timings, test cards, webhook events, team) are in `src/content/site.ts`, code samples in `src/content/snippets.ts`, and the API reference (endpoints, objects, events, error codes) in `src/content/apiReference.ts`. They come from `docs/MVP-SCOPE.md`, `contracts/API-CONTRACT.md`, `simulator/apps/operations/test_cards.py` and the URS. Update them when those change.

The privacy policy (`src/pages/Privacy.tsx`) states what the demo keeps, for how long and with which providers (Google Cloud Singapore, Resend, Vercel, GitHub), taken from `gateway/apps/security/retention.py`, the vault purge and the cookies the apps set. Keep it in step when those change. The public OpenAPI files in `public/openapi/` are generated: run `python contracts/bundle_openapi.py` after changing the API contract.

The site must keep saying that SecurePay is a student project, not a licensed payment provider, and that pricing is illustrative (the top banner, footer, Pricing page and the About page's `#disclaimer` section).
