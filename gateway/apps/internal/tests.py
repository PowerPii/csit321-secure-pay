"""Staff API (D3 to D6b and the administrator pages): roles, merchant scoping, actions."""
import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.internal.models import ReviewCase
from apps.merchants.models import ApiKey, Merchant
from apps.payments.models import Operation, Payment
from apps.refunds.models import Refund
from apps.risk.models import ScreeningEvent

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


def pay(shop, card="4242424242424242", **body):
    """A payment through the hosted checkout (screened, then sent to the fake simulator)."""
    from conftest import valid_body

    payment = Payment.objects.get(public_id=shop.create_payment(valid_body(**body)).json()["id"])
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    browser.post(f"{base}/card", {"number": card, "expiry_month": 12, "expiry_year": 2030,
                                  "cvc": "123", "privacy_consent": True}, format="json")
    browser.post(f"{base}/submit", {}, format="json")
    payment.refresh_from_db()
    return payment


@pytest.fixture
def operator(staff_client, shop):
    return staff_client("merchant_operator", merchant=shop.merchant)


@pytest.fixture
def analyst(staff_client):
    return staff_client("fraud_analyst")


@pytest.fixture
def admin(staff_client):
    return staff_client("administrator")


def post(client, path, body=None):
    return client.post(path, body or {}, content_type="application/json")


# --- D3 / D4: who sees what -----------------------------------------------------------------

def test_operator_sees_only_their_merchant(operator, shop, other_shop, fake_sim):
    mine = pay(shop)
    theirs = pay(other_shop)
    data = operator.get("/internal/payments").json()
    assert [row["id"] for row in data["data"]] == [mine.public_id]
    assert data["summary"]["awaiting_capture"] == 1 and data["summary"]["escalated"] is None
    row = data["data"][0]
    assert row["card"] == {"brand": "visa", "last4": "4242"}
    assert row["customer"] == "a•••@example.com"
    assert row["risk"] == {"decision": "allow", "verification": None}
    # Another merchant's payment is "not found", never "forbidden" (FR-MER-08).
    r = operator.get(f"/internal/payments/{theirs.public_id}")
    assert r.status_code == 404
    r = post(operator, f"/internal/payments/{theirs.public_id}/capture")
    assert r.status_code == 404
    assert operator.get("/internal/payments?merchant=" + other_shop.merchant.public_id) \
        .json()["count"] == 1  # the merchant filter cannot widen an operator's scope


def test_admin_and_analyst_see_every_merchant_and_views_are_logged(admin, analyst, shop,
                                                                   other_shop, fake_sim):
    pay(shop)
    theirs = pay(other_shop)
    for client in (admin, analyst):
        assert client.get("/internal/payments").json()["count"] == 2
    detail = admin.get(f"/internal/payments/{theirs.public_id}").json()
    assert detail["merchant"]["name"] == "Other Shop"
    assert detail["actions"] == {"capture": False, "cancel": False, "refund": False,
                                 "recheck": False, "review": False}
    assert AuditEvent.objects.filter(action="payment.viewed", target_id=theirs.public_id,
                                     actor_id=admin.account.public_id).exists()
    filtered = admin.get(f"/internal/payments?merchant={shop.merchant.public_id}").json()
    assert filtered["count"] == 1


def test_list_filters(operator, shop, fake_sim):
    ok = pay(shop)
    declined = pay(shop, card="4000000000000002", order_reference="ORD-77")
    assert declined.status == "declined"

    def get(query):
        return [r["id"] for r in operator.get(f"/internal/payments?{query}").json()["data"]]

    assert get("status=declined") == [declined.public_id]
    assert set(get("status=declined,authorised")) == {ok.public_id, declined.public_id}
    assert get("q=ORD-77") == [declined.public_id]
    assert get(f"q={ok.reference}") == [ok.public_id]
    assert set(get("q=alex@example.com")) == {ok.public_id, declined.public_id}
    assert get("decision=block") == []
    assert get("from=2000-01-01&to=2000-01-02") == []
    assert operator.get("/internal/payments?status=nope").status_code == 400
    assert operator.get("/internal/payments?from=13/11/2026").status_code == 400


def test_detail_has_decision_record_timeline_and_webhooks(operator, shop, fake_sim):
    payment = pay(shop)
    data = operator.get(f"/internal/payments/{payment.public_id}").json()
    assert data["status"] == "authorised"
    assert data["screening"]["outcome"] == "allow"
    # Merchant operators get the decision, not the screening internals (test_explanations).
    assert data["screening"]["merchant_view"] is True
    assert "features" not in data["screening"] and "thresholds" not in data["screening"]
    actions = [e["action"] for e in data["timeline"]]
    assert actions[0] == "payment.created" and "payment.authorised" in actions
    assert [w["type"] for w in data["webhooks"]] == ["payment.processing",
                                                     "payment.authorised"]
    assert data["operations"][0]["type"] == "authorise"
    assert data["actions"]["capture"] and data["actions"]["cancel"]
    assert not data["actions"]["refund"] and not data["actions"]["recheck"]
    text = str(data)
    assert "4242424242424242" not in text and "alex@example.com" not in text


def test_signed_out_and_wrong_role_are_refused(client, analyst, shop, fake_sim):
    assert client.get("/internal/payments").json()["error"]["code"] == "not_signed_in"
    payment = pay(shop)
    r = post(analyst, f"/internal/payments/{payment.public_id}/capture")
    assert r.status_code == 403 and r.json()["error"]["code"] == "role_not_allowed"
    assert analyst.get("/internal/merchants").status_code == 403
    assert analyst.get("/internal/audit").status_code == 403


# --- capture, cancel, refund from the dashboard (S1, S6) ------------------------------------

def test_operator_captures_then_refunds_twice(operator, shop, fake_sim):
    payment = pay(shop)
    r = post(operator, f"/internal/payments/{payment.public_id}/capture")
    assert r.status_code == 200, r.content
    assert r.json()["status"] == "captured" and r.json()["actions"]["refund"]
    event = AuditEvent.objects.get(action="payment.capture_requested",
                                   target_id=payment.public_id)
    assert (event.actor_type, event.actor_id) == ("staff", operator.account.public_id)

    url = f"/internal/payments/{payment.public_id}/refunds"
    r = post(operator, url, {"amount": 1000, "reason": "One item returned"})
    assert r.status_code == 201 and r.json()["status"] == "completed"
    r = post(operator, url, {"amount": 4000})
    assert r.status_code == 422 and r.json()["error"]["code"] == "refund_exceeds_refundable"
    assert operator.get(url).json()["refundable_amount"] == 3590
    detail = operator.get(f"/internal/payments/{payment.public_id}").json()
    assert detail["refunded_amount"] == 1000
    assert [e["action"] for e in detail["timeline"]][-1] == "refund.rejected"
    staff_name = operator.account.user.email
    assert any(e["actor"] == staff_name for e in detail["timeline"])


def test_operator_cancels(operator, shop, fake_sim):
    payment = pay(shop)
    r = post(operator, f"/internal/payments/{payment.public_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    again = post(operator, f"/internal/payments/{payment.public_id}/cancel")
    assert again.status_code == 409


def test_capture_without_answer_is_202_and_admin_rechecks(operator, admin, shop, fake_sim):
    payment = pay(shop)
    fake_sim.settle_mode = "hang"
    r = post(operator, f"/internal/payments/{payment.public_id}/capture")
    assert r.status_code == 202
    assert r.json()["pending_operation"]["type"] == "capture"
    assert not r.json()["actions"]["capture"]
    op = Operation.objects.get(type="capture")
    Operation.objects.filter(pk=op.pk).update(escalated_at=op.created_at)
    listing = admin.get("/internal/payments?attention=escalated").json()
    assert [row["id"] for row in listing["data"]] == [payment.public_id]
    assert listing["summary"]["escalated"] == 1
    assert admin.get(f"/internal/payments/{payment.public_id}").json()["actions"]["recheck"]

    assert post(operator, f"/internal/operations/{op.public_id}/recheck").status_code == 403
    fake_sim.settle_mode = "normal"
    r = post(admin, f"/internal/operations/{op.public_id}/recheck")
    assert r.status_code == 200, r.content
    # The fake simulator never recorded the hung capture, so the check retires it.
    assert r.json()["settled"] and r.json()["operation"]["status"] == "not_processed"
    assert AuditEvent.objects.filter(action="operation.rechecked",
                                     actor_id=admin.account.public_id).exists()
    r = post(admin, f"/internal/operations/{op.public_id}/recheck")
    assert r.status_code == 409


# --- D6 / D6b fraud review ------------------------------------------------------------------

@pytest.fixture
def flagged(shop, fake_sim):
    """One blocked payment (blocklisted email) and one that passed verification."""
    from django.core.management import call_command

    call_command("seed_risk_lists")
    blocked = pay(shop, customer_email="blocked@example.com")
    assert blocked.status == "blocked"
    verify = pay(shop, customer_email="review@example.com")
    assert verify.status == "verification_required"
    return blocked, verify


def test_review_queue_lists_flagged_cases(analyst, operator, flagged, shop, fake_sim):
    pay(shop)  # allowed: not a case
    blocked, verify = flagged
    data = analyst.get("/internal/reviews").json()
    assert data["counts"] == {"open": 2, "mine": 0, "closed": 0}
    decisions = {row["payment"]["id"]: row["decision"] for row in data["data"]}
    assert decisions == {blocked.public_id: "blocked", verify.public_id: "verify_pending"}
    row = next(r for r in data["data"] if r["decision"] == "blocked")
    assert row["reasons"] == ["blocklisted_email"]
    only = analyst.get("/internal/reviews?decision=blocked").json()["data"]
    assert [r["payment"]["id"] for r in only] == [blocked.public_id]
    assert operator.get("/internal/reviews").status_code == 403


def test_analyst_records_a_finding_without_changing_the_payment(analyst, flagged):
    blocked, _ = flagged
    case_id = ScreeningEvent.objects.get(payment=blocked).public_id
    detail = analyst.get(f"/internal/reviews/{case_id}").json()
    assert detail["review"]["status"] == "open"
    assert detail["linked_activity"]["email"]["attempts"] == 0
    assert detail["payment"]["customer"] == "b•••@example.com"

    r = post(analyst, f"/internal/reviews/{case_id}", {"action": "assign"})
    assert r.json()["review"]["assigned_to"]["id"] == analyst.account.public_id
    assert analyst.get("/internal/reviews?tab=mine").json()["count"] == 1
    r = post(analyst, f"/internal/reviews/{case_id}", {"action": "save"})
    assert r.status_code == 400
    r = post(analyst, f"/internal/reviews/{case_id}",
             {"action": "save", "finding": "false_positive", "notes": "Known customer"})
    assert r.status_code == 200
    review = r.json()["review"]
    assert (review["status"], review["finding"]) == ("closed", "false_positive")
    blocked.refresh_from_db()
    assert blocked.status == "blocked"  # findings never rewrite outcomes
    counts = analyst.get("/internal/reviews?tab=closed").json()["counts"]
    assert counts == {"open": 1, "mine": 0, "closed": 1}
    audit = AuditEvent.objects.get(action="review.finding_recorded")
    assert audit.target_id == blocked.public_id and audit.details["false_positive"] is True
    r = post(analyst, f"/internal/reviews/{case_id}", {"action": "reopen"})
    assert r.json()["review"]["status"] == "open"
    assert ReviewCase.objects.get().finding == "false_positive"


def test_case_shows_linked_attempts(analyst, shop, fake_sim):
    from django.core.management import call_command

    call_command("seed_risk_lists")
    earlier = pay(shop)  # same card, allowed
    blocked = pay(shop, customer_email="blocked@example.com")
    case_id = ScreeningEvent.objects.get(payment=blocked).public_id
    detail = analyst.get(f"/internal/reviews/{case_id}").json()
    related = {r["payment"]["id"]: r for r in detail["related"]}
    assert "card" in related[earlier.public_id]["shared"]
    assert related[earlier.public_id]["case_id"] is None  # allowed: not a case
    assert detail["linked_activity"]["card"]["attempts"] == 1


# --- administrator pages --------------------------------------------------------------------

def test_admin_creates_and_approves_a_merchant(admin):
    r = post(admin, "/internal/merchants", {"name": "Book Nook",
                                            "webhook_url": "https://books.example/hooks"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    merchant_id = r.json()["id"]
    assert r.json()["api_key"] is None
    r = post(admin, f"/internal/merchants/{merchant_id}/approve")
    assert r.status_code == 200
    creds = r.json()["credentials"]
    assert creds["api_key"].startswith("sp_test_") and creds["signing_secret"].startswith(
        "whsec_")
    merchant = Merchant.objects.get(public_id=merchant_id)
    assert merchant.status == "active" and merchant.signing_secret == creds["signing_secret"]
    assert ApiKey.objects.active().get(merchant=merchant).hint == creds["api_key"][:12]
    # Shown once: the list never carries them.
    listing = admin.get("/internal/merchants").json()["data"]
    assert "credentials" not in listing[0] and listing[0]["api_key"]["hint"].endswith("…")
    assert post(admin, f"/internal/merchants/{merchant_id}/approve").status_code == 409
    r = post(admin, f"/internal/merchants/{merchant_id}/webhook", {"approved": True})
    assert r.json()["webhook_url_approved"] is True
    r = post(admin, f"/internal/merchants/{merchant_id}/webhook",
             {"webhook_url": "http://insecure.example", "approved": True})
    assert r.status_code == 400


def test_admin_rejects_with_a_reason(admin):
    merchant_id = post(admin, "/internal/merchants", {"name": "Shady"}).json()["id"]
    assert post(admin, f"/internal/merchants/{merchant_id}/reject").status_code == 400
    r = post(admin, f"/internal/merchants/{merchant_id}/reject", {"reason": "No documents"})
    assert r.json()["status"] == "rejected"
    event = AuditEvent.objects.get(action="merchant.rejected")
    assert event.details == {"reason": "No documents"}


def test_audit_log_is_filterable_and_read_only(admin, operator, shop, fake_sim):
    payment = pay(shop)
    data = admin.get(f"/internal/audit?target={payment.public_id}").json()
    assert data["count"] >= 2
    assert {e["action"] for e in data["data"]} >= {"payment.created", "payment.authorised"}
    signins = admin.get("/internal/audit?action=staff.signed_in").json()
    assert signins["count"] == 2
    for method in ("put", "patch", "delete"):
        assert getattr(admin, method)("/internal/audit").status_code == 405


def test_refund_rows_hold_no_card_data(operator, shop, fake_sim):
    payment = pay(shop)
    post(operator, f"/internal/payments/{payment.public_id}/capture")
    post(operator, f"/internal/payments/{payment.public_id}/refunds", {"amount": 500})
    assert Refund.objects.count() == 1
    detail = operator.get(f"/internal/payments/{payment.public_id}").json()
    assert "4242424242424242" not in str(detail)


def test_the_receipt_reference_finds_the_payment_however_it_is_typed(operator, other_shop,
                                                                     shop, fake_sim):
    """One public reference from receipt to dashboard (completion audit, 19 Nov 2026): the
    SP- reference as a customer reads it out, and a refund receipt's RF- reference."""
    payment = pay(shop)
    pay(shop, order_reference="ORD-2")
    theirs = pay(other_shop)

    def get(q):
        return [r["id"] for r in operator.get("/internal/payments", {"q": q}).json()["data"]]

    ref = payment.reference  # SP-XXXX-XXXX
    for typed in (ref, ref.lower(), ref.replace("-", " "), ref.replace("-", ""), f" {ref} "):
        assert get(typed) == [payment.public_id], typed
    post(operator, f"/internal/payments/{payment.public_id}/capture")
    post(operator, f"/internal/payments/{payment.public_id}/refunds", {"amount": 500})
    refund = Refund.objects.get()
    assert get(refund.reference) == [payment.public_id]
    assert get(refund.reference.lower().replace("-", "")) == [payment.public_id]
    # Scope still applies: another merchant's reference finds nothing for this operator.
    assert get(theirs.reference) == []


# --- Overview (demo-day polish) -------------------------------------------------------------

def test_overview_counts_today_and_is_scoped_to_the_operators_merchant(operator, admin, shop,
                                                                       other_shop, fake_sim):
    pay(shop)
    pay(shop, card="4000000000000002")  # declined by the simulated bank
    pay(other_shop)
    mine = operator.get("/internal/overview").json()
    today = mine["today"]
    assert today["payments"] == 2 and today["approved"] == 1 and today["declined"] == 1
    assert today["approval_rate"] == 0.5
    assert len(mine["daily"]) == 14
    assert mine["daily"][-1]["approved"] == 1 and mine["daily"][-1]["declined"] == 1
    assert {row["merchant"]["id"] for row in mine["recent"]} == {shop.merchant.public_id}
    assert mine["screening_7d"]["allow"] == 2
    everyone = admin.get("/internal/overview").json()
    assert everyone["today"]["payments"] == 3 and len(everyone["recent"]) == 3


def test_overview_needs_a_signed_in_staff_member(client):
    assert client.get("/internal/overview").status_code == 401
