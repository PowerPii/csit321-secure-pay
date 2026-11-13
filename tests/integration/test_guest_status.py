"""Emailed receipt (FR-CHK-15) and the guest status check (FR-ACC-05/06) on the stack."""
import re
import time

from conftest import (APPROVE_2, GATEWAY_URL, create_payment, pay, unique_email)


def test_receipt_then_status_by_emailed_code(browser_factory, merchant_api, mailpit):
    email = unique_email("guest")
    payment = create_payment(merchant_api, email=email)
    started = time.time()
    assert pay(browser_factory(), payment, APPROVE_2)["result"] == "approved"

    receipt = mailpit.wait_for(email, "Receipt", started)
    reference = payment["reference"]
    assert reference in receipt["Subject"]
    link = f"{GATEWAY_URL}/guest/status?ref={reference}"
    assert link in receipt["Text"] and "Mastercard ending 4444" in receipt["Text"]

    # The link opens the C9 page (the checkout bundle), with a strict CSP.
    guest = browser_factory()
    page = guest.get(f"/guest/status?ref={reference}")
    assert page.status_code == 200 and '<div id="root">' in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]

    # Same reply for a wrong email; only the real pair gets a code.
    other = guest.post("/guest/status/code", json={"reference": reference,
                                                   "email": unique_email("nobody")})
    asked = time.time()
    real = guest.post("/guest/status/code", json={"reference": reference.lower(),
                                                  "email": email})
    assert other.status_code == real.status_code == 202
    assert other.json()["message"] == real.json()["message"]
    code_mail = mailpit.wait_for(email, "status code", asked)
    code = re.search(r"status code is (\d{6})", code_mail["Text"]).group(1)

    unlocked = guest.post("/guest/status/verify",
                          json={"challenge_id": real.json()["challenge_id"], "code": code})
    assert unlocked.status_code == 200, unlocked.text
    view = unlocked.json()
    assert view["reference"] == reference and view["status_label"] == "Paid"
    assert "sp_guest_status" in unlocked.headers["set-cookie"]
    assert "HttpOnly" in unlocked.headers["set-cookie"]
    again = guest.get("/guest/status/payment")
    assert again.status_code == 200 and again.json()["reference"] == reference
    assert guest.post("/guest/status/sign-out", json={}).status_code == 204
    assert guest.get("/guest/status/payment").status_code == 401


def test_three_wrong_codes_lock_the_check(browser_factory, merchant_api):
    email = unique_email("locked")
    payment = create_payment(merchant_api, email=email)
    guest = browser_factory()
    challenge = guest.post("/guest/status/code", json={
        "reference": payment["reference"], "email": email}).json()
    replies = [guest.post("/guest/status/verify",
                          json={"challenge_id": challenge["challenge_id"], "code": "000000"})
               for _ in range(3)]
    # The real code is 000000 one time in a million; then this test may fail once.
    assert [r.status_code for r in replies] == [400, 400, 429]
    assert replies[2].json()["error"]["code"] == "status_check_locked"
    assert int(replies[2].headers["retry-after"]) > 14 * 60
