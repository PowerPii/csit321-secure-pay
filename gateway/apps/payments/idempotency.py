"""Idempotency-Key handling for merchant POSTs (API-CONTRACT.md section 5, FR-CHK-09/10).

    1. Key missing or malformed       -> 400, not stored.
    2. Body not JSON / has card data  -> 400, not stored (card data never reaches the fingerprint).
    3. Claim the key: insert an `in_progress` record and commit it at once, so a concurrent
       request with the same key sees it.
         same key, other fingerprint  -> 409 idempotency_key_reused, nothing runs
         same key, still running      -> 409 idempotency_request_in_progress, Retry-After: 1
         same key, finished           -> the stored status and body, Idempotent-Replayed: true
    4. Run the handler and store its reply in ONE transaction with the handler's writes.
       2xx and 4xx are stored. A 5xx or crash rolls everything back and frees the key, so a
       retry with the same key runs again.

A record left `in_progress` by a process that died is taken over after
IDEMPOTENCY_STALE_SECONDS; its writes were rolled back with it, so that is safe.
"""
import hashlib
import json
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.renderers import JSONRenderer

from apps.common.carddata import contains_card_number
from apps.common.errors import ApiError, error_response, invalid, to_api_error
from apps.payments.models import IdempotencyRecord

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
KEY_PATTERN = re.compile(r"^[\x21-\x7E]{8,255}$")


def parse_json_body(request) -> dict:
    """Parse the raw body ourselves, so it is checked for card data before anything else."""
    raw = request.body or b"{}"
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise invalid("invalid_json", "The request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise invalid("invalid_json", "The request body must be a JSON object.")
    if contains_card_number(body):
        raise invalid("card_data_not_allowed",
                      "Card numbers must never be sent to this API. Use the hosted checkout.")
    return body


def request_fingerprint(method: str, path: str, body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256()
    for part in (method.upper(), path, canonical):
        digest.update(part.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _json_response(body: bytes, status: int, replayed: bool = False) -> HttpResponse:
    response = HttpResponse(body, status=status, content_type="application/json")
    if replayed:
        response[REPLAYED_HEADER] = "true"
    return response


def _claim(merchant, key, method, path, fingerprint):
    """Return (record, None) if we own the key now, or (None, reply) to send instead."""
    rules = settings.GATEWAY_RULES
    now = timezone.now()
    try:
        with transaction.atomic():
            record = IdempotencyRecord.objects.create(
                merchant=merchant, key=key, method=method, path=path,
                request_fingerprint=fingerprint, locked_at=now, created_at=now,
                expires_at=now + timedelta(hours=rules["IDEMPOTENCY_TTL_HOURS"]),
            )
        return record, None
    except IntegrityError:
        pass

    with transaction.atomic():
        record = (IdempotencyRecord.objects.select_for_update()
                  .filter(merchant=merchant, key=key).first())
        if record is None:  # deleted between our insert and this read; try once more
            return _claim(merchant, key, method, path, fingerprint)
        if record.is_expired:
            # 24 hours after first use the key is free again (rule 2).
            record.delete()
            return _claim(merchant, key, method, path, fingerprint)
        if record.request_fingerprint != fingerprint:
            raise ApiError(409, "idempotency_key_reused",
                           "This Idempotency-Key was used with a different request.",
                           param=HEADER)
        if record.status == IdempotencyRecord.Status.COMPLETED:
            return None, _json_response(record.response_body.encode(), record.response_status,
                                        replayed=True)
        stale = timedelta(seconds=rules["IDEMPOTENCY_STALE_SECONDS"])
        if now - record.locked_at < stale:
            raise ApiError(409, "idempotency_request_in_progress",
                           "A request with this Idempotency-Key is still running.",
                           param=HEADER, retry_after=1)
        record.locked_at = now  # the first attempt died; take it over
        record.save(update_fields=["locked_at"])
        return record, None


def run_idempotent(request, handler):
    """Run `handler(body)` at most once per merchant + key, replaying its stored reply.

    `handler` gets the parsed body and returns a DRF Response, or raises ApiError.
    Returns an HttpResponse with the exact bytes that were (or will be) stored.
    """
    key = request.headers.get(HEADER)
    if key is None:
        raise invalid("idempotency_key_missing", "Send an Idempotency-Key header with every "
                      "POST.", param=HEADER)
    if not KEY_PATTERN.match(key):
        raise invalid("idempotency_key_invalid", "Idempotency-Key must be 8 to 255 printable "
                      "ASCII characters.", param=HEADER)
    body = parse_json_body(request)
    merchant = request.user
    method, path = request.method, request.path
    record, reply = _claim(merchant, key, method, path,
                           request_fingerprint(method, path, body))
    if reply is not None:
        return reply

    try:
        with transaction.atomic():
            try:
                with transaction.atomic():
                    response = handler(body)
            except Exception as exc:  # mapped below or re-raised
                api_error = to_api_error(exc)
                if api_error is None or api_error.status_code >= 500:
                    raise
                response = error_response(api_error, request)
            if response.status_code >= 500:
                raise RuntimeError(f"handler returned {response.status_code}")
            rendered = JSONRenderer().render(response.data)
            record.status = IdempotencyRecord.Status.COMPLETED
            record.response_status = response.status_code
            record.response_body = rendered.decode()
            record.save(update_fields=["status", "response_status", "response_body"])
    except BaseException:
        # Nothing was committed; free the key so a retry runs again (rule 7).
        IdempotencyRecord.objects.filter(pk=record.pk,
                                         status=IdempotencyRecord.Status.IN_PROGRESS).delete()
        raise

    reply = _json_response(rendered, response.status_code)
    for header in ("Retry-After",):
        if header in response:
            reply[header] = response[header]
    return reply
