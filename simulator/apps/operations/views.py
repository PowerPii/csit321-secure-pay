"""Simulator API views (contracts/openapi/simulator.yaml). Called only by the gateway."""
import time

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.common.http import ApiError, error_reply, gateway_only, json_reply
from apps.operations import service
from apps.operations.models import OperationRecord
from apps.operations.test_cards import Behaviour, behaviour_for

CONFLICT_MESSAGES = {
    "operation_retired": "This operation_id was reported as no_record and can never be "
                         "processed.",
    "operation_id_conflict": "This operation_id was already used with a different request.",
}


def _hold_then_hang_up() -> HttpResponse:
    """Stand-in for "never replies": hold the connection, then end it with no record reply.

    Django cannot drop a connection, so after the hold we send an unsigned 504. The gateway
    has given up long before (10 s, proposal S1) and an unsigned reply is never evidence.
    """
    time.sleep(settings.SIM_HOLD_SECONDS)
    return HttpResponse(status=504)


def _existing_reply(request, exc: service.Existing) -> HttpResponse:
    data = service.to_dict(exc.record)
    if exc.conflict_code:
        return error_reply(request, 409, exc.conflict_code, CONFLICT_MESSAGES[exc.conflict_code],
                           "operation_id", operation=data)
    return json_reply(data, signed=True, replayed=True)


@csrf_exempt
@require_POST
@gateway_only
def authorise(request):
    body = service.parse_authorise(request.body)
    request_fingerprint = service.fingerprint(body)
    try:
        service.check_existing(body["operation_id"], request_fingerprint)
        behaviour = behaviour_for(body["card"]["number"])
        if behaviour is Behaviour.DROP_REQUEST:
            return _hold_then_hang_up()  # lost request: nothing recorded
        record = service.record_authorise(body, behaviour, request_fingerprint)
    except service.Existing as exc:
        return _existing_reply(request, exc)

    if behaviour is Behaviour.TIMEOUT and record.status == OperationRecord.Status.APPROVED:
        return _hold_then_hang_up()  # lost response: recorded, never answered
    if behaviour is Behaviour.SLOW and record.status == OperationRecord.Status.APPROVED:
        time.sleep(settings.SIM_HOLD_SECONDS)  # replies after the gateway gave up
    return json_reply(service.to_dict(record), signed=True)


@require_GET
@gateway_only
def operation_status(request, operation_id: str):
    if not service.OPERATION_ID.match(operation_id):
        raise ApiError(400, "invalid_field", "Not an operation ID.", "operation_id")
    op_type = request.GET.get("type")
    if op_type is not None and op_type not in OperationRecord.Type.values:
        raise ApiError(400, "invalid_field", "'type' must be authorise, capture, cancel or "
                       "refund.", "type")
    record = service.status_query(operation_id, op_type)
    return json_reply(service.to_dict(record), signed=True)


def _settle(request, parse, op_type):
    body = parse(request.body)
    request_fingerprint = service.fingerprint(body)
    try:
        service.check_existing(body["operation_id"], request_fingerprint)
        if op_type == OperationRecord.Type.REFUND:
            record = service.record_refund(body, request_fingerprint)
        else:
            record = service.record_settlement(body, op_type, request_fingerprint)
    except service.Existing as exc:
        return _existing_reply(request, exc)
    return json_reply(service.to_dict(record), signed=True)


@csrf_exempt
@require_POST
@gateway_only
def capture(request):
    return _settle(request, service.parse_capture, OperationRecord.Type.CAPTURE)


@csrf_exempt
@require_POST
@gateway_only
def cancel(request):
    return _settle(request, service.parse_cancel, OperationRecord.Type.CANCEL)


@csrf_exempt
@require_POST
@gateway_only
def refund(request):
    return _settle(request, service.parse_refund, OperationRecord.Type.REFUND)
