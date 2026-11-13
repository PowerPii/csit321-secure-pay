"""Fault controls, record list and notifications (SIMULATOR-CONTRACT.md sections 8 and 9)."""
import hashlib
import hmac
import json

import httpx
import pytest

from apps.faults import notify
from apps.faults.models import FaultRule
from apps.operations.models import OperationRecord
from apps.operations.tests import MER, PAY, body, signature_ok

OP2 = "op_" + "D" * 24
OP3 = "op_" + "E" * 24
OP4 = "op_" + "F" * 24


def op(n: int) -> str:
    return "op_" + f"{n:024d}"


@pytest.fixture
def controls(settings, db):
    settings.SIM_TEST_CONTROLS = True
    from conftest import GatewayClient

    return GatewayClient(settings.SIMULATOR_TEST_CONTROL_KEY)


@pytest.fixture
def sent(monkeypatch, settings):
    """Run notifications at once and capture what reaches the 'gateway'."""
    received = []

    def handler(request):
        received.append(request)
        return httpx.Response(200, json={"received": True})

    monkeypatch.setattr(notify, "TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(notify, "run_later", lambda delay, fn: fn())
    return received


def add(controls, **rule):
    response = controls.post_json("/sim/faults", rule)
    assert response.status_code == 201, response.content
    return response.json()


# --- the test-control API ------------------------------------------------------------

def test_controls_are_absent_when_switched_off(settings, db):
    settings.SIM_TEST_CONTROLS = False
    from conftest import GatewayClient

    client = GatewayClient(settings.SIMULATOR_TEST_CONTROL_KEY)
    assert client.get("/sim/faults").status_code == 404
    assert client.post_json("/sim/faults", {"match": {}, "action": "notify"}).status_code == 404


def test_gateway_key_does_not_open_controls(controls, gw):
    response = gw.get("/sim/faults")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "api_key_invalid"


def test_create_list_delete(controls):
    rule = add(controls, match={"operation_type": "capture"}, action="drop_response",
               remaining=1)
    assert rule["id"].startswith("flt_") and rule["remaining"] == 1
    assert [r["id"] for r in controls.get("/sim/faults").json()["data"]] == [rule["id"]]
    assert controls.delete(f"/sim/faults/{rule['id']}",
                           HTTP_AUTHORIZATION=f"Bearer {controls.key}").status_code == 204
    assert controls.delete(f"/sim/faults/{rule['id']}",
                           HTTP_AUTHORIZATION=f"Bearer {controls.key}").status_code == 404
    add(controls, match={}, action="notify")
    assert controls.delete("/sim/faults",
                           HTTP_AUTHORIZATION=f"Bearer {controls.key}").status_code == 204
    assert controls.get("/sim/faults").json()["data"] == []


@pytest.mark.parametrize("rule, param", [
    ({"action": "notify"}, "match"),
    ({"match": {"colour": "red"}, "action": "notify"}, "match.colour"),
    ({"match": {"operation_type": "pay"}, "action": "notify"}, "match.operation_type"),
    ({"match": {}, "action": "explode"}, "action"),
    ({"match": {}, "action": "delay_request"}, "delay_ms"),
    ({"match": {}, "action": "drop_request", "delay_ms": 5}, "delay_ms"),
    ({"match": {}, "action": "notify", "copies": 11}, "copies"),
    ({"match": {}, "action": "drop_request", "copies": 2}, "copies"),
    ({"match": {}, "action": "drop_request", "remaining": 0}, "remaining"),
])
def test_bad_rules_are_refused(controls, rule, param):
    response = controls.post_json("/sim/faults", rule)
    assert response.status_code == 400
    assert response.json()["error"]["param"] == param


# --- request faults ------------------------------------------------------------------

def test_drop_request_records_nothing_and_is_used_up(controls, gw):
    add(controls, match={"card_last4": "4242"}, action="drop_request", remaining=1)
    response = gw.post_json("/sim/authorise", body())
    assert response.status_code == 504 and "Simulator-Signature" not in response
    assert not OperationRecord.objects.exists()
    assert controls.get("/sim/faults").json()["data"] == []  # used up
    # The status query then retires the ID; the late arrival is rejected.
    assert gw.get(f"/sim/operations/{body()['operation_id']}").json()["status"] == "no_record"
    late = gw.post_json("/sim/authorise", body())
    assert late.status_code == 409 and late.json()["error"]["code"] == "operation_retired"


def test_drop_response_records_then_hangs_up(controls, gw):
    add(controls, match={"operation_type": "authorise", "payment_id": PAY},
        action="drop_response")
    response = gw.post_json("/sim/authorise", body())
    assert response.status_code == 504
    record = OperationRecord.objects.get()
    assert record.status == OperationRecord.Status.APPROVED
    # remaining null: the rule stays until removed
    assert len(controls.get("/sim/faults").json()["data"]) == 1


def test_rule_that_does_not_match_changes_nothing(controls, gw):
    add(controls, match={"merchant_id": "mer_" + "Z" * 24}, action="drop_request")
    assert gw.post_json("/sim/authorise", body()).status_code == 200


def test_replay_does_not_use_up_a_rule(controls, gw):
    assert gw.post_json("/sim/authorise", body()).status_code == 200
    add(controls, match={}, action="drop_response", remaining=1)
    replay = gw.post_json("/sim/authorise", body())
    assert replay.status_code == 200 and replay["Simulator-Replayed"] == "true"
    assert len(controls.get("/sim/faults").json()["data"]) == 1


def test_delay_request_then_retired_by_status_query(controls, gw, monkeypatch):
    """A status query during the wait retires the ID; the delayed request then gets 409."""
    add(controls, match={}, action="delay_request", delay_ms=10, remaining=1)
    from apps.operations import views

    def query_during_wait(rule):
        assert gw.get(f"/sim/operations/{body()['operation_id']}").json()["status"] == \
            "no_record"

    monkeypatch.setattr(views, "_sleep_ms", query_during_wait)
    response = gw.post_json("/sim/authorise", body())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "operation_retired"
    assert signature_ok(response, gw_secret())


def gw_secret():
    from django.conf import settings

    return settings.SIMULATOR_SIGNING_SECRET


def test_delay_response_records_then_replies(controls, gw, monkeypatch):
    add(controls, match={}, action="delay_response", delay_ms=1, remaining=1)
    response = gw.post_json("/sim/authorise", body())
    assert response.status_code == 200 and response.json()["status"] == "approved"


def test_capture_fault_matches_on_the_authorisations_payment(controls, gw):
    assert gw.post_json("/sim/authorise", body()).status_code == 200
    add(controls, match={"operation_type": "capture", "payment_id": PAY},
        action="drop_response", remaining=1)
    capture = {"operation_id": OP2, "authorisation_id": body()["operation_id"], "amount": 4590}
    assert gw.post_json("/sim/capture", capture).status_code == 504
    assert OperationRecord.objects.get(operation_id=OP2).status == "approved"
    # The gateway's status query then finds the capture.
    assert gw.get(f"/sim/operations/{OP2}?type=capture").json()["status"] == "approved"


def test_fail_status_query_answers_503_without_retiring(controls, gw):
    add(controls, match={"operation_type": "authorise"}, action="fail_status_query",
        remaining=2)
    for _ in range(2):
        response = gw.get(f"/sim/operations/{OP3}?type=authorise")
        assert response.status_code == 503 and "Simulator-Signature" not in response
        assert response.json()["error"]["code"] == "service_unavailable"
    assert not OperationRecord.objects.filter(operation_id=OP3).exists()
    assert gw.get(f"/sim/operations/{OP3}?type=authorise").json()["status"] == "no_record"


def test_faults_ignored_when_controls_switched_off(controls, gw, settings):
    add(controls, match={}, action="drop_request")
    settings.SIM_TEST_CONTROLS = False
    assert gw.post_json("/sim/authorise", body()).status_code == 200


# --- notifications -------------------------------------------------------------------

def test_notify_sends_signed_copies(controls, gw, sent, settings):
    add(controls, match={"operation_type": "authorise"}, action="notify", copies=3,
        remaining=1)
    response = gw.post_json("/sim/authorise", body())
    assert response.status_code == 200
    assert len(sent) == 3
    bodies = [json.loads(r.content) for r in sent]
    assert len({b["id"] for b in bodies}) == 1 and bodies[0]["id"].startswith("ntf_")
    assert [b["delivery"] for b in bodies] == [1, 2, 3]
    assert bodies[0]["type"] == "operation.recorded"
    assert bodies[0]["data"] == response.json()
    for request in sent:
        assert str(request.url) == settings.SIM_GATEWAY_NOTIFY_URL
        parts = dict(p.split("=", 1) for p in request.headers["Simulator-Signature"].split(","))
        mac = hmac.new(settings.SIMULATOR_SIGNING_SECRET.encode(),
                       f"{parts['t']}.".encode() + request.content, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(mac, parts["v1"])


def test_notify_with_a_lost_response(controls, gw, sent):
    """The S4 variant: the reply is lost but a notification carries the record."""
    add(controls, match={}, action="drop_response", remaining=1)
    add(controls, match={}, action="notify", remaining=1)
    assert gw.post_json("/sim/authorise", body()).status_code == 504
    assert len(sent) == 1 and json.loads(sent[0].content)["data"]["status"] == "approved"


def test_no_notification_without_a_rule(controls, gw, sent):
    assert gw.post_json("/sim/authorise", body()).status_code == 200
    assert sent == []


def test_notification_matches_contract_schema(controls, gw, sent, operation_schema):
    add(controls, match={}, action="notify", remaining=1)
    gw.post_json("/sim/authorise", body())
    data = json.loads(sent[0].content)
    assert set(data) == {"id", "type", "created_at", "delivery", "data"}
    operation_schema.validate(data["data"])


# --- record list (FR-TXN-11) -----------------------------------------------------------

def test_list_operations_pages_oldest_first(gw):
    for n in range(1, 4):
        assert gw.post_json("/sim/authorise", body(op=op(n))).status_code == 200
    gw.get(f"/sim/operations/{op(9)}")  # a no_record entry is listed too
    first = gw.get("/sim/operations?limit=2")
    assert first.status_code == 200 and signature_ok(first, gw_secret())
    page = first.json()
    assert [r["operation_id"] for r in page["data"]] == [op(1), op(2)]
    rest = gw.get(f"/sim/operations?limit=2&cursor={page['next_cursor']}").json()
    assert [r["operation_id"] for r in rest["data"]] == [op(3), op(9)]
    assert rest["next_cursor"] is None
    assert rest["data"][1]["status"] == "no_record"


def test_list_operations_filters_and_never_retires(gw):
    gw.post_json("/sim/authorise", body(op=op(1)))
    other = body(op=op(2))
    other["payment_id"] = "pay_" + "Q" * 24
    gw.post_json("/sim/authorise", other)
    data = gw.get(f"/sim/operations?payment_id={PAY}").json()["data"]
    assert [r["operation_id"] for r in data] == [op(1)]
    assert gw.get("/sim/operations?recorded_after=2999-01-01T00:00:00Z").json()["data"] == []
    assert OperationRecord.objects.count() == 2
    assert MER  # same merchant for both


@pytest.mark.parametrize("query, param", [
    ("limit=0", "limit"), ("limit=x", "limit"), ("cursor=!!", "cursor"),
    ("payment_id=nope", "payment_id"), ("recorded_after=yesterday", "recorded_after"),
])
def test_list_operations_rejects_bad_queries(gw, query, param):
    response = gw.get(f"/sim/operations?{query}")
    assert response.status_code == 400 and response.json()["error"]["param"] == param


def test_list_needs_gateway_key(db, client):
    assert client.get("/sim/operations").status_code == 401


def test_rule_str():
    assert "notify" in str(FaultRule(public_id="flt_x", action="notify", match={}))
