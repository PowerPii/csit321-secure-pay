"""HTTP client for the processing simulator (contracts/SIMULATOR-CONTRACT.md).

Only a signed reply is evidence (section 7). Everything else (timeout, connection error,
5xx, 400, 401, a bad or missing signature, a record for another operation) is "no answer",
and the operation becomes Unresolved for reconciliation to settle with the same ID.
"""
import json
import logging
from dataclasses import dataclass
from enum import StrEnum

import httpx
from django.conf import settings

from apps.events import signing
from apps.payments.models import Operation, Payment

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "Simulator-Signature"
# Tests replace this with an httpx.MockTransport; None means real network calls.
TRANSPORT: httpx.BaseTransport | None = None


class AnswerKind(StrEnum):
    RECORDED = "recorded"  # signed 200: the operation record
    CONFLICT = "conflict"  # signed 409: operation_retired / operation_id_conflict + record
    NO_ANSWER = "no_answer"


@dataclass(frozen=True)
class Answer:
    kind: AnswerKind
    record: dict | None = None
    conflict_code: str | None = None
    raw_body: str = ""
    signature: str = ""
    problem: str = ""  # why there is no answer, for logs and audit (never card data)


def _client() -> httpx.Client:
    rules = settings.GATEWAY_RULES
    timeout = httpx.Timeout(rules["SIMULATOR_TIMEOUT_SECONDS"],
                            connect=rules["SIMULATOR_CONNECT_TIMEOUT_SECONDS"])
    return httpx.Client(
        base_url=settings.SIMULATOR_URL,
        timeout=timeout,
        verify=settings.SIMULATOR_CA_BUNDLE or True,
        follow_redirects=False,
        transport=TRANSPORT,
        headers={"Authorization": f"Bearer {settings.SIMULATOR_API_KEY}",
                 "User-Agent": "SecurePay-Gateway/1.0"},
    )


def _interpret(response: httpx.Response, operation: Operation) -> Answer:
    signature = response.headers.get(SIGNATURE_HEADER, "")
    if response.status_code not in (200, 409):
        return Answer(AnswerKind.NO_ANSWER, problem=f"http_{response.status_code}")
    tolerance = settings.GATEWAY_RULES["SIMULATOR_SIGNATURE_TOLERANCE_SECONDS"]
    if not signature or not signing.verify(response.content, signature,
                                           settings.SIMULATOR_SIGNING_SECRET, tolerance):
        return Answer(AnswerKind.NO_ANSWER, problem="bad_signature")
    try:
        data = json.loads(response.content)
    except ValueError:
        return Answer(AnswerKind.NO_ANSWER, problem="invalid_json")
    raw = response.content.decode()
    if response.status_code == 409:
        record = data.get("operation") or {}
        code = (data.get("error") or {}).get("code")
        if record.get("operation_id") != operation.public_id:
            return Answer(AnswerKind.NO_ANSWER, problem="wrong_operation")
        return Answer(AnswerKind.CONFLICT, record=record, conflict_code=code, raw_body=raw,
                      signature=signature)
    if data.get("operation_id") != operation.public_id:
        return Answer(AnswerKind.NO_ANSWER, problem="wrong_operation")
    return Answer(AnswerKind.RECORDED, record=data, raw_body=raw, signature=signature)


def _call(operation: Operation, method: str, path: str, **kwargs) -> Answer:
    try:
        with _client() as client:
            response = client.request(method, path, **kwargs)
    except httpx.TimeoutException:
        return Answer(AnswerKind.NO_ANSWER, problem="timeout")
    except httpx.HTTPError as exc:
        return Answer(AnswerKind.NO_ANSWER, problem=type(exc).__name__)
    answer = _interpret(response, operation)
    if answer.kind is AnswerKind.NO_ANSWER:
        logger.warning("No usable simulator answer for %s: %s", operation.public_id,
                       answer.problem)
    return answer


def authorise(operation: Operation, payment: Payment, card) -> Answer:
    """Send the one authorisation for this payment. `card` comes from vault.take()."""
    body = {
        "operation_id": operation.public_id,
        "merchant_id": payment.merchant.public_id,
        "payment_id": payment.public_id,
        "amount": operation.amount,
        "currency": payment.currency,
        "card": {"number": card.number, "expiry_month": card.expiry_month,
                 "expiry_year": card.expiry_year, "cvc": card.cvc},
    }
    return _call(operation, "POST", "/sim/authorise", json=body)


def status_query(operation: Operation) -> Answer:
    """Ask about an operation by its original ID (section 6). Used by reconciliation."""
    return _call(operation, "GET", f"/sim/operations/{operation.public_id}",
                 params={"type": operation.type})
