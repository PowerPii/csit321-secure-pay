# Cross-service integration tests

End-to-end, recovery, concurrency and security scenarios that need the gateway, simulator and merchant running together (`docker compose -f deploy/compose.yaml up`).

Suggested files as the work grows: `test_payment_flow.py`, `test_lost_response_recovery.py`, `test_refund_concurrency.py`, `test_access_control.py`, `test_webhook_signatures.py`, plus Playwright specs under `e2e/` and Locust files under `load/`.
