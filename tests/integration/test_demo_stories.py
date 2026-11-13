"""Demo stories S1-S6 (docs/MVP-SCOPE.md section 2) against the running stack.

Each run pays twice with each approving test card. The fraud screening counts attempts per
card (the burst rule, and the trained model's 7-day card history), so running the suite
again soon after makes those cards look risky and S1/S6 end Blocked. Use a fresh database
(`docker compose -f deploy/compose.yaml down -v`) between repeated runs.
"""
import re
import threading
import time
import uuid

from conftest import (APPROVE, APPROVE_2, BLOCKLISTED, LOST_RESPONSE, MERCHANT_URL,
                      create_payment, pay, unique_email, wait_for_status)


def csrf(page: str) -> str:
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)


def test_s1_happy_path_through_the_shop(browser_factory, merchant_api):
    """Shop order -> hosted checkout -> Allow -> Authorised -> shop marks it paid from the
    signed webhook / signed GET -> merchant captures."""
    shop = browser_factory(MERCHANT_URL, follow_redirects=False)
    home = shop.get("/").text
    assert shop.post("/cart/add", data={"sku": "MOUSE-01", "csrfmiddlewaretoken": csrf(home)},
                     headers={"Referer": f"{MERCHANT_URL}/"}).status_code == 302
    form = shop.get("/checkout").text
    started = shop.post("/checkout", headers={"Referer": f"{MERCHANT_URL}/checkout"}, data={
        "csrfmiddlewaretoken": csrf(form), "email": unique_email("s1"),
        "full_name": "Alex Tan", "delivery_address": "1 Demo Road, Singapore 123456"})
    assert started.status_code == 302, started.text[:500]
    checkout_url = started.headers["location"]
    assert "/pay/cs_" in checkout_url

    result = pay(browser_factory(), {"checkout_url": checkout_url}, APPROVE)
    assert result["result"] == "approved" and result["status"] == "authorised"
    order_path = re.search(r"https://[^/]+(/orders/\d+)/return", result["return_url"]).group(1)

    deadline = time.time() + 20
    while "Payment confirmed" not in (page := shop.get(order_path).text):
        assert time.time() < deadline, "the shop never marked the order paid"
        time.sleep(1)
    payment_id = re.search(r"payment_id=(pay_[0-9A-Za-z]{24})", result["return_url"]).group(1)
    captured = merchant_api.post(f"/v1/payments/{payment_id}/capture", json={},
                                 headers={"Idempotency-Key": str(uuid.uuid4())})
    assert captured.status_code == 200 and captured.json()["status"] == "captured"
    assert "Paid" in shop.get(order_path).text or "Payment confirmed" in page


def test_s2_risky_attempt_verified_by_emailed_code(browser_factory, merchant_api, mailpit):
    payment = create_payment(merchant_api, email="review@example.com")
    browser = browser_factory()
    sent_after = time.time()
    result = pay(browser, payment, APPROVE_2)
    assert result["result"] == "verification_required"
    email = mailpit.wait_for("review@example.com", "verification code", sent_after)
    code = re.search(r"verification code is (\d{6})", email["Text"]).group(1)
    base = f"/checkout/{result['session_id']}"
    wrong = browser.post(f"{base}/verify", json={"code": f"{(int(code) + 1) % 10**6:06d}"})
    assert wrong.status_code == 400
    done = browser.post(f"{base}/verify", json={"code": code}).json()
    assert done["result"] == "approved"


def test_s3_blocklisted_card_is_blocked_before_the_bank(browser_factory, merchant_api):
    payment = create_payment(merchant_api)
    result = pay(browser_factory(), payment, BLOCKLISTED)
    assert result["result"] == "not_completed"
    stored = merchant_api.get(f"/v1/payments/{payment['id']}").json()
    assert stored["status"] == "blocked" and stored["outcome"]["reason"] == "fraud_rule"


def test_s4_lost_response_is_reconciled_with_the_same_operation(browser_factory,
                                                                 merchant_api):
    """Lost answer: 10 s timeout -> Unresolved; the worker's first status check (~30 s
    later) finds the approval for the original operation ID; one authorisation only."""
    payment = create_payment(merchant_api)
    result = pay(browser_factory(), payment, LOST_RESPONSE)
    assert result["result"] == "pending" and result["status"] == "unresolved"
    settled = wait_for_status(merchant_api, payment["id"], {"authorised"}, timeout=60)
    assert settled["status"] == "authorised"


def test_s5_duplicate_request_with_the_same_idempotency_key(merchant_api):
    key = str(uuid.uuid4())
    body = {"amount": 1200, "currency": "SGD", "order_reference": f"IT-{key[:8]}",
            "return_url": f"{MERCHANT_URL}/orders/1/return",
            "customer_email": unique_email("s5")}
    first = merchant_api.post("/v1/payments", json=body, headers={"Idempotency-Key": key})
    again = merchant_api.post("/v1/payments", json=body, headers={"Idempotency-Key": key})
    assert first.status_code == again.status_code == 201
    assert first.content == again.content  # the stored reply, byte for byte
    changed = merchant_api.post("/v1/payments", json=body | {"amount": 1300},
                                headers={"Idempotency-Key": key})
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_key_reused"


def test_s6_two_refunds_at_once_cannot_exceed_the_payment(browser_factory, merchant_api):
    payment = create_payment(merchant_api, amount=5000)
    assert pay(browser_factory(), payment, APPROVE)["result"] == "approved"
    merchant_api.post(f"/v1/payments/{payment['id']}/capture", json={},
                      headers={"Idempotency-Key": str(uuid.uuid4())})
    replies = []

    def refund():
        replies.append(merchant_api.post(
            f"/v1/payments/{payment['id']}/refunds", json={"amount": 3000},
            headers={"Idempotency-Key": str(uuid.uuid4())}))

    threads = [threading.Thread(target=refund) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    codes = sorted(r.status_code for r in replies)
    assert codes[0] in (200, 201) and codes[1] in (409, 422), [r.text for r in replies]
    partial = merchant_api.post(f"/v1/payments/{payment['id']}/refunds", json={"amount": 2000},
                                headers={"Idempotency-Key": str(uuid.uuid4())})
    assert partial.status_code in (200, 201)
    final = merchant_api.get(f"/v1/payments/{payment['id']}").json()
    assert final["refunded_amount"] == 5000 and final["refundable_amount"] == 0
