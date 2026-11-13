"""Error replies in the contract format (API-CONTRACT.md section 4, schemas/error.schema.json).

    {"error": {"type": ..., "code": ..., "message": ..., "param": ..., "request_id": ...}}

Views raise `ApiError`; DRF's own exceptions (authentication, throttling, 404, parse errors)
are mapped onto the same shape by `exception_handler`, which settings.REST_FRAMEWORK uses.
"""
import logging
import math

from django.http import Http404
from rest_framework import exceptions as drf
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# HTTP status -> error type (one type per status family, as the contract table lists them)
TYPES = {
    400: "invalid_request",
    401: "authentication",
    403: "permission",
    404: "not_found",
    405: "invalid_request",
    409: "conflict",
    415: "invalid_request",
    422: "business_rule",
    429: "rate_limit",
    500: "server",
    503: "server",
}


class ApiError(drf.APIException):
    """An error with a stable machine-readable `code` from the contract table."""

    def __init__(self, http_status, code, message, param=None, retry_after=None):
        super().__init__(detail=message, code=code)
        self.status_code = http_status
        self.code = code
        self.message = message
        self.param = param
        self.retry_after = retry_after


def invalid(code, message, param=None):
    return ApiError(status.HTTP_400_BAD_REQUEST, code, message, param)


def not_found():
    return ApiError(status.HTTP_404_NOT_FOUND, "resource_not_found", "No such resource.")


def error_body(request, http_status, code, message, param=None):
    return {
        "error": {
            "type": TYPES.get(http_status, "server" if http_status >= 500 else "invalid_request"),
            "code": code,
            "message": message,
            "param": param,
            "request_id": getattr(request, "request_id", None),
        }
    }


def error_response(exc: ApiError, request) -> Response:
    response = Response(
        error_body(request, exc.status_code, exc.code, exc.message, exc.param),
        status=exc.status_code,
    )
    if exc.retry_after is not None:
        response["Retry-After"] = str(exc.retry_after)
    return response


def to_api_error(exc) -> ApiError | None:
    """Map a DRF or Django exception to an ApiError; None for unexpected exceptions."""
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, drf.NotAuthenticated | drf.AuthenticationFailed):
        return ApiError(401, "api_key_invalid", "Missing, unknown or revoked API key.")
    if isinstance(exc, drf.PermissionDenied):
        code = exc.get_codes() if isinstance(exc.get_codes(), str) else "permission_denied"
        return ApiError(403, code, str(exc.detail))
    if isinstance(exc, drf.NotFound | Http404):
        return not_found()
    if isinstance(exc, drf.Throttled):
        wait = max(1, math.ceil(exc.wait or 1))
        return ApiError(429, "rate_limited", "Too many requests. Try again later.",
                        retry_after=wait)
    if isinstance(exc, drf.ParseError):
        return invalid("invalid_json", "The request body is not valid JSON.")
    if isinstance(exc, drf.MethodNotAllowed):
        return ApiError(405, "method_not_allowed", str(exc.detail))
    if isinstance(exc, drf.UnsupportedMediaType):
        return ApiError(415, "unsupported_media_type", str(exc.detail))
    if isinstance(exc, drf.APIException):
        return ApiError(exc.status_code, "invalid_request" if exc.status_code < 500
                        else "internal_error", str(exc.detail))
    return None


def exception_handler(exc, context):
    request = context.get("request")
    api_error = to_api_error(exc)
    if api_error is None:
        logger.exception("Unhandled error in %s", context.get("view").__class__.__name__,
                         exc_info=exc)
        api_error = ApiError(500, "internal_error",
                             "Something went wrong. Retry with the same Idempotency-Key.")
    response = error_response(api_error, request)
    if api_error.status_code == 401:
        response["WWW-Authenticate"] = 'Bearer realm="securepay"'
    return response
