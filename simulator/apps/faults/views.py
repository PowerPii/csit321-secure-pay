"""Test-control API: /sim/faults (SIMULATOR-CONTRACT.md section 8).

Present only when SIM_TEST_CONTROLS=1; otherwise every path answers 404 as if it did not
exist. Uses its own key (`simc_...`, secret `simulator_test_control_key`) which only the
test runner holds; the gateway's key does not open it.
"""
import hashlib
import hmac
from functools import wraps

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.http import ApiError, error_reply, json_reply
from apps.common.ids import new_id
from apps.faults import service
from apps.faults.models import FaultRule


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def test_controls_only(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        request.request_id = new_id("req")
        if not settings.SIM_TEST_CONTROLS:
            return error_reply(request, 404, "resource_not_found", "No such resource.")
        scheme, _, key = request.headers.get("Authorization", "").partition(" ")
        expected = settings.SIMULATOR_TEST_CONTROL_KEY
        if (scheme.lower() != "bearer" or not expected
                or not hmac.compare_digest(_digest(key.strip()), _digest(expected))):
            return error_reply(request, 401, "api_key_invalid",
                               "Missing or wrong test-control key.")
        try:
            return view(request, *args, **kwargs)
        except ApiError as exc:
            return error_reply(request, exc.status, exc.code, exc.message, exc.param)

    return wrapper


@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
@test_controls_only
def faults(request):
    if request.method == "POST":
        rule = service.create(request.body)
        return json_reply(rule.to_dict(), 201)
    if request.method == "DELETE":
        FaultRule.objects.all().delete()
        return HttpResponse(status=204)
    return json_reply({"data": [rule.to_dict() for rule in FaultRule.objects.all()]})


@csrf_exempt
@require_http_methods(["DELETE"])
@test_controls_only
def fault(request, fault_id: str):
    deleted, _ = FaultRule.objects.filter(public_id=fault_id).delete()
    if not deleted:
        return error_reply(request, 404, "resource_not_found", "No such fault rule.")
    return HttpResponse(status=204)
