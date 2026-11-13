"""Simulator fault controls and notifications (SIMULATOR-CONTRACT.md sections 8 and 9)."""
import time

from conftest import LOST_RESPONSE, SLOW, create_payment, pay, wait_for_status


def test_controls_need_their_own_key(browser_factory, merchant_api, ca_bundle):
    from conftest import SIMULATOR_URL

    anonymous = browser_factory(SIMULATOR_URL)
    assert anonymous.get("/sim/faults").status_code == 401


def test_lost_response_settled_by_a_notification(browser_factory, merchant_api, controls):
    """drop_response + notify: the gateway's call times out (Unresolved), but the signed
    notification settles the payment long before the first status check is due (30 s)."""
    payment = create_payment(merchant_api)
    match = {"payment_id": payment["id"]}
    assert controls.post("/sim/faults", json={"match": match, "action": "drop_response",
                                              "remaining": 1}).status_code == 201
    assert controls.post("/sim/faults", json={"match": match, "action": "notify",
                                              "delay_ms": 11000, "copies": 2,
                                              "remaining": 1}).status_code == 201
    started = time.time()
    result = pay(browser_factory(), payment, LOST_RESPONSE)
    assert result["result"] == "pending"  # the reply was lost after 10 s
    settled = wait_for_status(merchant_api, payment["id"], {"authorised"}, timeout=15)
    assert settled["status"] == "authorised"
    assert time.time() - started < 28, "settled by the notification, not a status check"
    assert controls.get("/sim/faults").json()["data"] == []  # both rules used up


def test_lost_request_is_retired_and_declined(browser_factory, merchant_api, controls):
    """drop_request (here on the slow card, which would otherwise approve late): nothing
    recorded; the first status check retires the ID (no_record)
    and the payment is declined as not_processed, never charged."""
    payment = create_payment(merchant_api)
    assert controls.post("/sim/faults", json={"match": {"payment_id": payment["id"]},
                                              "action": "drop_request"}).status_code == 201
    assert pay(browser_factory(), payment, SLOW)["result"] == "pending"
    settled = wait_for_status(merchant_api, payment["id"], {"declined"}, timeout=60)
    assert settled["status"] == "declined" and settled["outcome"]["reason"] == "not_processed"
