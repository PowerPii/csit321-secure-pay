# Frontend

Two separate Vite + React + TypeScript builds, so the payment page stays small and auditable.

| Folder | What | Dev port |
| --- | --- | --- |
| `checkout/` | Hosted checkout bundle. No UI library, no third-party scripts, strict CSP with nonces and SRI on built assets. | 5173 |
| `dashboard/` | Merchant operator, administrator and analyst SPA (MUI, React Router, TanStack Query). | 5174 |

API types are generated from `contracts/openapi/gateway.yaml` into `contracts/generated/`, not written by hand.

```bash
cd checkout && npm install && npm run dev
```
