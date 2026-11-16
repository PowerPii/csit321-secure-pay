"""Input primitives shared by simulator operations and fault controls."""
import json

from apps.common.http import ApiError


def invalid(code: str, message: str, param: str | None = None) -> ApiError:
    return ApiError(400, code, message, param)


def is_integer(value) -> bool:
    # bool is an int subclass, but not an amount, month or fault-rule count.
    return isinstance(value, int) and not isinstance(value, bool)


def json_object(raw: bytes) -> dict:
    try:
        body = json.loads(raw or b"")
    except (ValueError, UnicodeDecodeError):
        raise invalid("invalid_json", "The request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise invalid("invalid_json", "The request body must be a JSON object.")
    return body
