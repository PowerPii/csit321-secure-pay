"""Replies, signatures and the gateway key check for the /sim API.

The signature scheme is the same as the merchant API's (API-CONTRACT.md section 2), with
its own header and secret: `Simulator-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256>`
over `"<t>." + raw body`. This is the simulator's own copy; nothing is imported from the
gateway (CONTRIBUTING rule 6).
"""
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from functools import wraps

from django.conf import settings
from django.http import HttpResponse

from apps.common.ids import new_id

SIGNATURE_HEADER = "Simulator-Signature"
REPLAYED_HEADER = "Simulator-Replayed"

TYPES = {400: "invalid_request", 401: "authentication", 404: "not_found", 405: "invalid_request",
         409: "conflict", 503: "server"}


def rfc3339(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign(body: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def json_reply(data: dict, status: int = 200, *, signed: bool = False,
               replayed: bool = False) -> HttpResponse:
    body = json.dumps(data, separators=(",", ":")).encode()
    response = HttpResponse(body, status=status, content_type="application/json")
    if signed:
        response[SIGNATURE_HEADER] = sign(body, settings.SIMULATOR_SIGNING_SECRET)
    if replayed:
        response[REPLAYED_HEADER] = "true"
    return response


def error_reply(request, status: int, code: str, message: str, param: str | None = None,
                **extra) -> HttpResponse:
    data = {"error": {"type": TYPES.get(status, "invalid_request"), "code": code,
                      "message": message, "param": param,
                      "request_id": getattr(request, "request_id", None) or new_id("req")}}
    data.update(extra)
    # 409 replies carry the existing record and are evidence, so they are signed too.
    return json_reply(data, status, signed=status == 409)


class ApiError(Exception):
    def __init__(self, status, code, message, param=None):
        super().__init__(message)
        self.status, self.code, self.message, self.param = status, code, message, param


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def gateway_only(view):
    """Require `Authorization: Bearer simk_...` (proposal S4); 401 replies are not signed."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        request.request_id = new_id("req")
        scheme, _, key = request.headers.get("Authorization", "").partition(" ")
        expected = settings.SIMULATOR_API_KEY
        if (scheme.lower() != "bearer" or not expected
                or not hmac.compare_digest(_digest(key.strip()), _digest(expected))):
            data = {"error": {"type": "authentication", "code": "api_key_invalid",
                              "message": "Missing or wrong simulator key.", "param": None,
                              "request_id": request.request_id}}
            return json_reply(data, 401)
        try:
            return view(request, *args, **kwargs)
        except ApiError as exc:
            return error_reply(request, exc.status, exc.code, exc.message, exc.param)

    return wrapper
