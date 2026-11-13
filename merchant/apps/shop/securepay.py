"""The shop's SecurePay client: create a payment and read it back, both signed.

Every reply from the gateway carries `SecurePay-Signature`, made with our signing secret
(API-CONTRACT.md section 2). A reply whose signature is missing, wrong or stale is treated
as no reply at all, so a forged or replayed "authorised" can never mark an order paid.
"""
import json
import logging
from dataclasses import dataclass

import httpx
from django.conf import settings

from apps.webhooks.signing import verify

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "SecurePay-Signature"
# Tests replace this with an httpx.MockTransport; None means real network calls.
TRANSPORT: httpx.BaseTransport | None = None


class GatewayError(Exception):
    """No usable answer: network error, timeout, 5xx, or a reply we cannot trust."""


@dataclass(frozen=True)
class Reply:
    status: int
    data: dict


def configured() -> bool:
    return bool(settings.SECUREPAY_API_KEY and settings.SECUREPAY_SIGNING_SECRET)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.SECUREPAY_API_URL,
        timeout=settings.SECUREPAY_TIMEOUT_SECONDS,
        verify=settings.SECUREPAY_CA_BUNDLE or True,
        follow_redirects=False,
        transport=TRANSPORT,
        headers={"Authorization": f"Bearer {settings.SECUREPAY_API_KEY}",
                 "User-Agent": "DemoShop/1.0"},
    )


def _request(method: str, path: str, **kwargs) -> Reply:
    if not configured():
        raise GatewayError("SecurePay API key and signing secret are not configured")
    try:
        with _client() as client:
            response = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise GatewayError(type(exc).__name__) from exc
    if response.status_code >= 500 or response.status_code == 401:
        raise GatewayError(f"HTTP {response.status_code}")
    header = response.headers.get(SIGNATURE_HEADER, "")
    if not verify(response.content, header, settings.SECUREPAY_SIGNING_SECRET,
                  settings.SECUREPAY_SIGNATURE_TOLERANCE_SECONDS):
        logger.warning("Rejected a SecurePay reply with a bad signature (%s %s)", method, path)
        raise GatewayError("bad signature")
    try:
        data = json.loads(response.content)
    except ValueError as exc:
        raise GatewayError("invalid JSON") from exc
    return Reply(response.status_code, data)


def create_payment(*, idempotency_key: str, amount: int, order_reference: str,
                   return_url: str, customer_email: str, description: str,
                   line_items: list[dict]) -> Reply:
    body = {"amount": amount, "currency": "SGD", "order_reference": order_reference,
            "return_url": return_url, "customer_email": customer_email,
            "description": description, "line_items": line_items}
    return _request("POST", "/v1/payments", json=body,
                    headers={"Idempotency-Key": idempotency_key})


def get_payment(payment_id: str) -> Reply:
    return _request("GET", f"/v1/payments/{payment_id}")


def capture_payment(payment_id: str, *, idempotency_key: str, amount: int | None = None) -> Reply:
    """Capture all (amount None) or part of an authorised payment, once (UC-25)."""
    body = {} if amount is None else {"amount": amount}
    return _request("POST", f"/v1/payments/{payment_id}/capture", json=body,
                    headers={"Idempotency-Key": idempotency_key})


def cancel_payment(payment_id: str, *, idempotency_key: str) -> Reply:
    """Void an authorised payment; nothing is charged."""
    return _request("POST", f"/v1/payments/{payment_id}/cancel", json={},
                    headers={"Idempotency-Key": idempotency_key})


def refund_payment(payment_id: str, *, idempotency_key: str, amount: int,
                   reason: str = "") -> Reply:
    """Refund all or part of a captured payment (UC-24). A new key per refund; reuse it only
    to retry the same refund."""
    body = {"amount": amount}
    if reason:
        body["reason"] = reason
    return _request("POST", f"/v1/payments/{payment_id}/refunds", json=body,
                    headers={"Idempotency-Key": idempotency_key})
