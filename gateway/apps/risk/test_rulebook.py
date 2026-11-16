"""Editable fraud rules (FR-FRD-02, FR-FRD-03), analyst search (FR-FRD-06) and the block list
(FR-FRD-09), through the staff API and the hosted checkout."""
import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.payments.models import Payment
from apps.risk.models import FraudRule, RiskListEntry, ScreeningEvent
from conftest import valid_body

pytestmark = pytest.mark.django_db(databases=["default", "vault"])

PAN = "4242424242424242"


def post(client, path, body=None):
    return client.post(path, body or {}, content_type="application/json")


def pay(shop, amount=4590, email="alex@example.com", ip="198.51.100.7"):
    payment = Payment.objects.get(public_id=shop.create_payment(
        valid_body(amount=amount, customer_email=email)).json()["id"])
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    browser.post(f"{base}/card", {"number": PAN, "expiry_month": 12, "expiry_year": 2030,
                                  "cvc": "123", "privacy_consent": True}, format="json",
                 REMOTE_ADDR=ip)
    browser.post(f"{base}/submit", {}, format="json", REMOTE_ADDR=ip)
    payment.refresh_from_db()
    return payment


@pytest.fixture
def admin(staff_client):
    return staff_client("administrator")


@pytest.fixture
def analyst(staff_client):
    return staff_client("fraud_analyst")


RULE = {"code": "large_order", "feature": "amount_cents", "op": "gt", "value": 20_000,
        "action": "block", "description": "Block orders over S$200 during the test"}


# --- FR-FRD-02: add, edit, switch off, versions ---------------------------------------------

def test_seeded_rules_match_rules_0_1(analyst):
    data = analyst.get("/internal/rules").json()
    assert data["version"] == "rules-0.1" and data["frozen"] is None
    assert {r["code"]: r["condition"] for r in data["rules"]} == {
        "card_attempt_burst": "card_attempts_10m >= 5", "high_amount": "amount_cents > 50000"}
    assert post(analyst, "/internal/rules", {"rule": RULE}).status_code == 403


def test_new_rule_applies_to_new_payments_only_and_keeps_versions(admin, shop, fake_sim):
    before = pay(shop, amount=30_000)
    assert before.status == "authorised"
    # FR-FRD-03: blocking above S$200 overlaps "verify above S$500" with another action.
    r = post(admin, "/internal/rules", {"rule": RULE})
    assert r.status_code == 409 and r.json()["error"]["code"] == "rule_conflict"
    assert r.json()["conflicts"][0]["code"] == "high_amount"
    assert r.json()["conflicts"][0]["kind"] == "opposite_action"
    r = post(admin, "/internal/rules", {"rule": RULE, "confirm_conflicts": True})
    assert r.status_code == 201 and r.json()["version"] == "rules-0.2"
    rule_id = r.json()["rule"]["id"]

    after = pay(shop, amount=30_000)
    assert after.status == "blocked"
    event = ScreeningEvent.objects.get(payment=after)
    assert "large_order" in event.reasons and event.rules_version == "rules-0.2"
    before.refresh_from_db()
    assert before.status == "authorised"  # earlier outcomes unchanged
    assert ScreeningEvent.objects.get(payment=before).rules_version == "rules-0.1"

    # Edit (new revision) and switch off; every revision is kept.
    r = post(admin, f"/internal/rules/{rule_id}",
             {"rule": {**RULE, "value": 40_000}, "confirm_conflicts": True})
    assert r.status_code == 200 and r.json()["rule"]["revision"] == 2
    r = post(admin, f"/internal/rules/{rule_id}/enabled", {"enabled": False})
    assert r.json()["rule"]["enabled"] is False and r.json()["version"] == "rules-0.4"
    assert pay(shop, amount=45_000).status == "authorised"
    history = admin.get(f"/internal/rules/{rule_id}").json()["revisions"]
    assert [h["revision"] for h in history] == [3, 2, 1]
    assert history[2]["superseded_at"] is not None and history[0]["superseded_at"] is None
    assert FraudRule.objects.filter(rule_id=rule_id).count() == 3
    assert AuditEvent.objects.filter(action__startswith="fraud_rule.").count() == 3


def test_conflict_check_and_validation(admin):
    r = post(admin, "/internal/rules/check",
             {"rule": {**RULE, "code": "again", "feature": "card_attempts_10m", "op": "gte",
                       "value": 5}})
    assert r.json()["conflicts"][0]["kind"] == "duplicate"
    r = post(admin, "/internal/rules/check",
             {"rule": {**RULE, "op": "lt", "value": 100, "action": "verify"}})
    assert r.json()["conflicts"] == []  # below S$1 never meets "above S$500"
    for bad in ({"feature": "card_number"}, {"op": "like"}, {"value": "5"},
                {"code": "blocklisted_card"}, {"code": "Bad Code"}, {"action": "allow"}):
        assert post(admin, "/internal/rules", {"rule": {**RULE, **bad}}).status_code == 400
    r = post(admin, "/internal/rules", {"rule": {**RULE, "code": "high_amount"},
                                         "confirm_conflicts": True})
    assert r.status_code == 400  # the code is taken by another rule


def test_rules_are_frozen_during_an_evaluation_run(admin):
    assert post(admin, "/internal/rules/freeze").status_code == 400
    r = post(admin, "/internal/rules/freeze", {"note": "Evaluation run EV-3"})
    assert r.json()["frozen"]["note"] == "Evaluation run EV-3"
    r = post(admin, "/internal/rules", {"rule": RULE, "confirm_conflicts": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "rules_frozen"
    rule_id = FraudRule.objects.filter(code="high_amount").first().rule_id
    assert post(admin, f"/internal/rules/{rule_id}/enabled",
                {"enabled": False}).status_code == 409
    assert post(admin, "/internal/rules/unfreeze").json()["frozen"] is None
    assert post(admin, f"/internal/rules/{rule_id}/enabled",
                {"enabled": False}).status_code == 200


# --- FR-FRD-06: search -----------------------------------------------------------------------

def test_analyst_searches_by_email_ip_and_card_and_each_search_is_logged(
        analyst, shop, other_shop, fake_sim):
    first = pay(shop, email="mule@example.com", ip="203.0.113.9")
    pay(other_shop, email="mule@example.com", ip="203.0.113.10")
    pay(shop, email="someone@example.com", ip="203.0.113.9")

    r = analyst.get("/internal/fraud/search?by=email&value=MULE@example.com").json()
    assert r["count"] == 2 and r["summary"]["merchants"] == 2
    assert r["searched"] == "m•••@example.com"
    r = analyst.get("/internal/fraud/search?by=ip&value=203.0.113.9").json()
    assert r["count"] == 2 and r["searched"] == "203.0.113.•"
    r = analyst.get(f"/internal/fraud/search?by=card&value={first.reference}").json()
    assert r["count"] == 3 and r["searched"] == "Visa •••• 4242"
    assert analyst.get("/internal/fraud/search?by=ip&value=nope").status_code == 400
    logged = AuditEvent.objects.filter(action="fraud.history_searched")
    assert logged.count() == 3
    assert "mule@example.com" not in str(list(logged.values_list("details", "target_id")))
    assert "203.0.113.9" not in str(list(logged.values_list("details", "target_id")))


def test_a_card_number_is_refused_and_never_logged(analyst, admin, shop, fake_sim):
    pay(shop)
    before = AuditEvent.objects.count()
    for value in ("4242424242424242", "4242 4242 4242 4242", "4242-4242-4242-4242"):
        for by in ("card", "email", "ip"):
            r = analyst.get(f"/internal/fraud/search?by={by}&value={value}")
            assert r.status_code == 400, (by, value, r.content)
            assert r.json()["error"]["code"] == "card_number_not_accepted"
            assert "4242424242" not in r.content.decode().replace(" ", "").replace("-", "")
    r = post(admin, "/internal/blocklist", {"kind": "card", "card_fingerprint": "4242424242424242",
                                            "reason": "test"})
    assert r.status_code == 400
    assert AuditEvent.objects.count() == before
    assert not RiskListEntry.objects.filter(value_hash__startswith="4242").exists()
    # A real fingerprint (64 hex digits) still searches.
    fingerprint = ScreeningEvent.objects.first().card_fingerprint
    r = analyst.get(f"/internal/fraud/search?by=card&value={fingerprint}")
    assert r.status_code == 200 and r.json()["count"] == 1


def test_operators_cannot_search_or_use_the_blocklist(staff_client, shop):
    operator = staff_client("merchant_operator", merchant=shop.merchant)
    assert operator.get("/internal/fraud/search?by=ip&value=1.2.3.4").status_code == 403
    assert operator.get("/internal/blocklist").status_code == 403
    assert operator.get("/internal/rules").status_code == 403


# --- FR-FRD-09: block list ------------------------------------------------------------------

def test_blocklisting_from_a_case_blocks_later_attempts_only(analyst, admin, shop, fake_sim):
    earlier = pay(shop, amount=60_000)  # verify -> a case
    case_id = ScreeningEvent.objects.get(payment=earlier).public_id
    assert post(analyst, "/internal/blocklist", {"kind": "card", "case_id": case_id}) \
        .status_code == 400  # a reason is needed
    r = post(analyst, "/internal/blocklist",
             {"kind": "card", "case_id": case_id, "reason": "Confirmed stolen card"})
    assert r.status_code == 201 and r.json()["display"] == "Visa •••• 4242"
    entry_id = r.json()["id"]
    again = post(analyst, "/internal/blocklist",
                 {"kind": "card", "case_id": case_id, "reason": "x"})
    assert again.status_code == 409

    later = pay(shop)
    assert later.status == "blocked" and later.outcome_reason == "fraud_rule"
    assert "blocklisted_card" in ScreeningEvent.objects.get(payment=later).reasons
    status = APIClient().get(f"/checkout/{later.checkout_session_id}").json()
    assert "blocklist" not in str(status).lower()  # the customer sees a general message
    earlier.refresh_from_db()
    assert earlier.status == "verification_required"  # unchanged

    # Only an administrator removes an entry; it is kept, switched off.
    assert post(analyst, f"/internal/blocklist/{entry_id}/remove",
                {"reason": "x"}).status_code == 403
    r = post(admin, f"/internal/blocklist/{entry_id}/remove", {"reason": "Card reissued"})
    assert r.status_code == 200 and r.json()["active"] is False
    assert pay(shop).status == "authorised"
    assert RiskListEntry.objects.filter(pk=entry_id).exists()
    actions = set(AuditEvent.objects.filter(action__startswith="blocklist.")
                  .values_list("action", flat=True))
    assert actions == {"blocklist.added", "blocklist.removed"}
    listed = analyst.get("/internal/blocklist?show=all").json()
    assert listed["can_remove"] is False and listed["data"][0]["removal_reason"] == "Card reissued"


def test_blocklisting_an_ip_by_address(analyst, shop, fake_sim):
    r = post(analyst, "/internal/blocklist",
             {"kind": "ip", "ip": "198.51.100.77", "reason": "Botnet range"})
    assert r.status_code == 201 and r.json()["display"] == "198.51.100.•"
    assert pay(shop, ip="198.51.100.77").status == "blocked"
    assert pay(shop, ip="198.51.100.78").status == "authorised"
