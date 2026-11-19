# Changelog

## 0.1.0 (2026-11-19)

First release.

- `SecurePay` client: `payments.create`, `retrieve`, `capture`, `cancel`; `refunds.create`, `list`, `retrieve`.
- Automatic `Idempotency-Key` on every `POST`; retries for timeouts, network failures, `429`, `5xx` and `409 idempotency_request_in_progress`, always with the same key.
- Signature checks on every reply when `signingSecret` is set.
- Webhooks: `constructEvent`, `verifySignature`, `signPayload`.
- Types generated from the merchant API's OpenAPI 3.1 file.
