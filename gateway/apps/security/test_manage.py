"""Account management and limits: FR-ADM-02 to FR-ADM-05, FR-ADM-07, FR-ADM-12."""
import pytest
from django.test import Client

from apps.accounts.models import StaffAccount
from apps.audit.models import AuditEvent
from apps.merchants.models import ApiKey, Merchant
from apps.security.models import SecurityAlert
from conftest import STAFF_PASSWORD, current_totp, valid_body

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


def post(client, path, body=None):
    return client.post(path, body or {}, content_type="application/json")


@pytest.fixture
def admin(staff_client):
    return staff_client("administrator")


@pytest.fixture
def analyst(staff_client):
    return staff_client("fraud_analyst")


@pytest.fixture
def operator(staff_client, shop):
    return staff_client("merchant_operator", merchant=shop.merchant)


SUSPEND = {"action": "suspend", "reason": "Suspected misuse", "confirm": True}


# --- FR-ADM-02 / FR-ADM-03: suspend, deactivate, reinstate staff ----------------------------

def test_suspending_staff_ends_their_session_and_reinstating_lets_them_back(admin, analyst):
    found = admin.get("/internal/staff?q=fraud_analyst").json()["data"]
    assert [a["id"] for a in found] == [analyst.account.public_id]
    target = f"/internal/staff/{analyst.account.public_id}/status"
    r = post(admin, target, {**SUSPEND, "confirm": False})
    assert r.status_code == 400 and r.json()["error"]["code"] == "confirmation_required"
    assert post(admin, target, {**SUSPEND, "reason": ""}).status_code == 400

    r = post(admin, target, SUSPEND)
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert analyst.get("/internal/me").status_code == 401  # session ended
    fresh = Client()
    r = post(fresh, "/internal/auth/login", {"email": analyst.account.email,
                                             "password": STAFF_PASSWORD})
    assert r.status_code == 401  # cannot sign in
    entry = AuditEvent.objects.get(action="staff.suspended")
    assert entry.details["reason"] == "Suspected misuse" and entry.details["sessions_ended"] == 1

    r = post(admin, target, {"action": "reinstate", "reason": "Cleared", "confirm": True})
    assert r.status_code == 200 and r.json()["status"] == "active"
    r = post(fresh, "/internal/auth/login", {"email": analyst.account.email,
                                             "password": STAFF_PASSWORD})
    assert r.status_code == 200


def test_deactivation_is_permanent(admin, analyst):
    target = f"/internal/staff/{analyst.account.public_id}/status"
    assert post(admin, target, {**SUSPEND, "action": "deactivate"}).status_code == 200
    r = post(admin, target, {"action": "reinstate", "reason": "x", "confirm": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "account_deactivated"
    assert StaffAccount.objects.filter(pk=analyst.account.pk).exists()  # history kept


def test_admin_cannot_suspend_themselves(admin):
    r = post(admin, f"/internal/staff/{admin.account.public_id}/status", SUSPEND)
    assert r.status_code == 409 and r.json()["error"]["code"] == "cannot_change_own_account"


def test_only_administrators_manage_accounts(analyst, operator, admin):
    for client in (analyst, operator):
        assert client.get("/internal/staff").status_code == 403
        r = post(client, f"/internal/staff/{admin.account.public_id}/role",
                 {"role": "fraud_analyst"})
        assert r.status_code == 403
    denied = AuditEvent.objects.filter(action="staff.role_change_denied")
    assert denied.count() == 2 and denied.first().target_id == admin.account.public_id


# --- FR-ADM-04 / FR-ADM-05: roles and the last administrator ---------------------------------

def test_role_change_applies_from_the_next_request(admin, analyst, shop):
    assert analyst.get("/internal/reviews").status_code == 200
    r = post(admin, f"/internal/staff/{analyst.account.public_id}/role",
             {"role": "merchant_operator"})
    assert r.status_code == 400  # an operator needs a merchant
    r = post(admin, f"/internal/staff/{analyst.account.public_id}/role",
             {"role": "merchant_operator", "merchant_id": shop.merchant.public_id})
    assert r.status_code == 200 and r.json()["merchant"]["id"] == shop.merchant.public_id
    assert analyst.get("/internal/reviews").status_code == 403  # same session, new role
    assert analyst.get("/internal/merchant").status_code == 200
    entry = AuditEvent.objects.get(action="staff.role_changed")
    assert entry.details["old_role"] == "fraud_analyst"
    assert entry.details["new_role"] == "merchant_operator"
    assert entry.actor_id == admin.account.public_id
    r = post(admin, f"/internal/staff/{analyst.account.public_id}/role", {"role": "boss"})
    assert r.status_code == 400


def test_the_last_administrator_cannot_be_removed(admin, staff_client):
    r = post(admin, f"/internal/staff/{admin.account.public_id}/role", {"role": "fraud_analyst"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_administrator"
    second = staff_client("administrator")
    # With a second administrator, the first can step down; then the second is the last.
    r = post(admin, f"/internal/staff/{admin.account.public_id}/role", {"role": "fraud_analyst"})
    assert r.status_code == 200
    third = staff_client("administrator")
    assert post(third, f"/internal/staff/{second.account.public_id}/status",
                SUSPEND).status_code == 200
    r = post(third, f"/internal/staff/{third.account.public_id}/role", {"role": "fraud_analyst"})
    assert r.status_code == 409


# --- merchants ------------------------------------------------------------------------------

def test_suspending_a_merchant_stops_its_key_and_operators_until_reinstated(admin, operator,
                                                                            shop):
    r = post(admin, f"/internal/merchants/{shop.merchant.public_id}/status", SUSPEND)
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    r = shop.create_payment()
    assert r.status_code == 403 and r.json()["error"]["code"] == "merchant_not_active"
    assert operator.get("/internal/me").status_code == 401
    r = post(Client(), "/internal/auth/login", {"email": operator.account.email,
                                                "password": STAFF_PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "merchant_suspended"

    r = post(admin, f"/internal/merchants/{shop.merchant.public_id}/status",
             {"action": "reinstate", "reason": "Resolved", "confirm": True})
    assert r.status_code == 200
    assert shop.create_payment().status_code == 201  # the same key works again


def test_deactivating_a_merchant_revokes_its_keys(admin, shop):
    r = post(admin, f"/internal/merchants/{shop.merchant.public_id}/status",
             {**SUSPEND, "action": "deactivate"})
    assert r.status_code == 200 and r.json()["status"] == "deactivated"
    assert not ApiKey.objects.active().filter(merchant=shop.merchant).exists()
    assert shop.create_payment().status_code == 401
    entry = AuditEvent.objects.get(action="merchant.deactivated")
    assert entry.details["revoked_api_keys"] == [shop.api_key.public_id]


# --- FR-ADM-07: amount limits ---------------------------------------------------------------

def test_admin_amount_limit_rejects_before_screening(admin, shop, other_shop):
    r = post(admin, "/internal/limits", {"max_amount_cents": 20_000_000})
    assert r.status_code == 400  # cannot raise the hard ceiling
    r = post(admin, "/internal/limits", {"max_amount_cents": 50_000})
    assert r.status_code == 200 and r.json()["effective"]["max_amount_cents"] == 50_000
    r = shop.create_payment(valid_body(amount=50_001))
    assert r.status_code == 422 and r.json()["error"]["code"] == "amount_above_limit"
    assert shop.create_payment(valid_body(amount=50_000)).status_code == 201
    entry = AuditEvent.objects.get(action="limits.changed")
    assert entry.details == {"old": {"max_amount_cents": None},
                             "new": {"max_amount_cents": 50_000}}

    # The merchant's own limit (set or removed by an administrator).
    r = post(admin, f"/internal/merchants/{other_shop.merchant.public_id}/limit",
             {"max_amount_cents": 1_000})
    assert r.status_code == 200 and r.json()["max_amount_cents"] == 1_000
    r = other_shop.create_payment(valid_body(amount=1_001))
    assert r.json()["error"]["code"] == "amount_above_merchant_limit"
    post(admin, f"/internal/merchants/{other_shop.merchant.public_id}/limit",
         {"max_amount_cents": None})
    assert other_shop.create_payment(valid_body(amount=1_001)).status_code == 201


def test_limits_are_admin_only(analyst):
    assert analyst.get("/internal/limits").status_code == 403
    assert post(analyst, "/internal/limits", {"max_amount_cents": 100}).status_code == 403


# --- FR-ADM-12: rate limits per key and IP --------------------------------------------------

def test_admin_rate_limit_per_key_rejects_with_retry_time_and_alerts(admin, shop, settings):
    settings.GATEWAY_RULES = {**settings.GATEWAY_RULES, "RATE_LIMIT_ALERT_VIOLATIONS": 3}
    r = post(admin, "/internal/limits", {"api_key_requests_per_minute": 2})
    assert r.status_code == 200
    url = "/v1/payments/pay_" + "B" * 24
    assert shop.get(url).status_code == 404 and shop.get(url).status_code == 404
    for _ in range(3):
        limited = shop.get(url)
        assert limited.status_code == 429 and int(limited["Retry-After"]) >= 1
    assert AuditEvent.objects.filter(action="security.rate_limited").count() == 1
    alert = SecurityAlert.objects.get(kind="rate_limit_exceeded")
    assert alert.source == f"api_key:{shop.api_key.public_id}"


def test_rate_limit_per_ip_covers_every_key(admin, shop, other_shop):
    post(admin, "/internal/limits", {"ip_requests_per_minute": 3})
    url = "/v1/payments/pay_" + "C" * 24
    assert shop.get(url).status_code == 404
    assert other_shop.get(url).status_code == 404
    assert shop.get(url).status_code == 404
    assert other_shop.get(url).status_code == 429  # same IP address
    assert post(admin, "/internal/limits", {"ip_requests_per_minute": 0}).status_code == 400


def test_totp_helper_still_signs_in(staff_client):
    client = staff_client("administrator")
    assert client.get("/internal/me").json()["role"] == "administrator"
    assert current_totp(client.account)
    assert Merchant.objects.count() == 0
