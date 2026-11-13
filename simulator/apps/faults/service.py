"""Parse, store and apply fault rules (SIMULATOR-CONTRACT.md section 8).

Which rules an operation can trigger:

* one *request* rule (`drop_request`, `delay_request`, `drop_response`, `delay_response`),
  the oldest that matches, for each new authorise, capture, cancel or refund. A replay of an
  operation already recorded never triggers or uses up a rule;
* every matching `notify` rule, once the operation is recorded (never for `no_record`);
* one `fail_status_query` rule for each status query.

Taking a rule uses up one of its `remaining` and deletes it at zero, under a row lock, so
two requests at once never both use the last one. With SIM_TEST_CONTROLS off nothing is
looked up at all, so the demo pays no cost for the feature.
"""
import json
import re

from django.conf import settings
from django.db import transaction

from apps.common.http import ApiError
from apps.faults.models import MATCH_FIELDS, FaultRule

REQUEST_ACTIONS = (FaultRule.Action.DROP_REQUEST, FaultRule.Action.DELAY_REQUEST,
                   FaultRule.Action.DROP_RESPONSE, FaultRule.Action.DELAY_RESPONSE)
DELAY_ACTIONS = (FaultRule.Action.DELAY_REQUEST, FaultRule.Action.DELAY_RESPONSE,
                 FaultRule.Action.NOTIFY)
OPERATION_TYPES = ("authorise", "capture", "cancel", "refund")
MATCH_PATTERNS = {
    "payment_id": re.compile(r"^pay_[0-9A-Za-z]{24}$"),
    "merchant_id": re.compile(r"^mer_[0-9A-Za-z]{24}$"),
    "card_last4": re.compile(r"^[0-9]{4}$"),
}
INPUT_FIELDS = {"match", "action", "delay_ms", "copies", "remaining"}


def _bad(code: str, message: str, param: str | None = None) -> ApiError:
    return ApiError(400, code, message, param)


def _int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_rule(raw: bytes) -> dict:
    """Validate a FaultRuleInput (contracts/openapi/simulator.yaml)."""
    try:
        body = json.loads(raw or b"")
    except (ValueError, UnicodeDecodeError):
        raise _bad("invalid_json", "The request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise _bad("invalid_json", "The request body must be a JSON object.")
    for name in ("match", "action"):
        if name not in body:
            raise _bad("missing_field", f"'{name}' is required.", name)
    for name in body:
        if name not in INPUT_FIELDS:
            raise _bad("invalid_field", f"Unknown field '{name}'.", name)
    match = body["match"]
    if not isinstance(match, dict):
        raise _bad("invalid_field", "'match' must be an object.", "match")
    for name, value in match.items():
        if name not in MATCH_FIELDS:
            raise _bad("invalid_field", f"Unknown match field '{name}'.", f"match.{name}")
        ok = (value in OPERATION_TYPES if name == "operation_type"
              else isinstance(value, str) and MATCH_PATTERNS[name].match(value))
        if not ok:
            raise _bad("invalid_field", f"'match.{name}' is not valid.", f"match.{name}")
    if body["action"] not in FaultRule.Action.values:
        raise _bad("invalid_field", "'action' is not a fault action.", "action")
    delay = body.get("delay_ms")
    if delay is not None and (not _int(delay) or not 0 <= delay <= 600_000):
        raise _bad("invalid_field", "'delay_ms' must be 0 to 600000.", "delay_ms")
    if delay is None and body["action"] in (FaultRule.Action.DELAY_REQUEST,
                                            FaultRule.Action.DELAY_RESPONSE):
        raise _bad("missing_field", "'delay_ms' is required for a delay.", "delay_ms")
    if delay is not None and body["action"] not in DELAY_ACTIONS:
        raise _bad("invalid_field", "'delay_ms' only applies to delays and notify.", "delay_ms")
    copies = body.get("copies", 1)
    if not _int(copies) or not 1 <= copies <= 10:
        raise _bad("invalid_field", "'copies' must be 1 to 10.", "copies")
    if "copies" in body and body["action"] != FaultRule.Action.NOTIFY:
        raise _bad("invalid_field", "'copies' only applies to notify.", "copies")
    remaining = body.get("remaining")
    if remaining is not None and (not _int(remaining) or remaining < 1):
        raise _bad("invalid_field", "'remaining' must be 1 or more, or null.", "remaining")
    return {"match": match, "action": body["action"], "delay_ms": delay, "copies": copies,
            "remaining": remaining}


def create(raw: bytes) -> FaultRule:
    return FaultRule.objects.create(**parse_rule(raw))


def _take(actions, context: dict, many: bool) -> list[FaultRule]:
    if not settings.SIM_TEST_CONTROLS:
        return []
    taken = []
    with transaction.atomic():
        for rule in FaultRule.objects.select_for_update().filter(action__in=actions):
            if not rule.matches(context):
                continue
            taken.append(rule)
            if rule.remaining is not None:
                rule.remaining -= 1
                if rule.remaining == 0:
                    rule.delete()
                else:
                    rule.save(update_fields=["remaining"])
            if not many:
                break
    return taken


def take_request_rule(context: dict) -> FaultRule | None:
    rules = _take(REQUEST_ACTIONS, context, many=False)
    return rules[0] if rules else None


def take_notify_rules(context: dict) -> list[FaultRule]:
    return _take((FaultRule.Action.NOTIFY,), context, many=True)


def take_status_rule(context: dict) -> FaultRule | None:
    rules = _take((FaultRule.Action.FAIL_STATUS_QUERY,), context, many=False)
    return rules[0] if rules else None


def context_for(record_or_body: dict, operation_type: str) -> dict:
    """What a rule can match on: type, payment, merchant and card's last four digits."""
    return {"operation_type": operation_type,
            "payment_id": record_or_body.get("payment_id"),
            "merchant_id": record_or_body.get("merchant_id"),
            "card_last4": record_or_body.get("card_last4")}
