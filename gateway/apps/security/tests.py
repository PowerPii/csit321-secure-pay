"""API key rotation and revocation (FR-MER-04, FR-MER-05), cross-merchant access logging
(FR-MER-09) and security alerts (FR-ADM-08, NFR-PER-03)."""
import pytest
from django.core import mail as django_mail
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.models import AuditEvent
from apps.events.emails import send_due
from apps.merchants.models import ApiKey
from apps.payments.models import Payment
from apps.security.models import SecurityAlert
from conftest import STAFF_PASSWORD, current_totp, make_staff_user, valid_body

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


def post(client, path, body=None):
    return client.post(path, body or {}, content_type="application/json")


def fresh_code(account):
    """The current code again: django-otp refuses a code it has already accepted."""
    device = TOTPDevice.objects.get(user=account.user, confirmed=True)
    device.last_t = -1
    device.save(update_fields=["last_t"])
    return current_totp(account, device)


@pytest.fixture
def operator(staff_client, shop):
    return staff_client("merchant_operator", merchant=shop.merchant)


@pytest.fixture
def admin(staff_client):
    return staff_client("administrator")


# --- FR-MER-04: rotate ----------------------------------------------------------------------

def test_rotate_needs_the_code_and_the_old_key_stops_working(operator, shop):
    assert shop.get("/v1/payments/pay_nothing").status_code == 404  # old key works
    r = post(operator, "/internal/merchant/api-key/rotate", {"code": "000000"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "code_incorrect"
    assert ApiKey.objects.active().get(merchant=shop.merchant).pk == shop.api_key.pk

    r = post(operator, "/internal/merchant/api-key/rotate", {"code": fresh_code(operator.account)})
    assert r.status_code == 200, r.content
    data = r.json()
    new_key, new_secret = data["credentials"]["api_key"], data["credentials"]["signing_secret"]
    assert new_key.startswith("sp_test_") and new_secret.startswith("whsec_")
    assert new_secret != shop.secret
    assert data["api_key"]["hint"] != shop.api_key.hint + "…"
    assert [k["id"] for k in data["revoked_keys"]] == [shop.api_key.public_id]

    # The old key is refused from now on; the new one works.
    assert shop.create_payment().status_code == 401
    shop.credentials(HTTP_AUTHORIZATION=f"Bearer {new_key}")
    assert shop.create_payment().status_code == 201
    entry = AuditEvent.objects.get(action="api_key.rotated")
    assert entry.details["old_api_key_id"] == shop.api_key.public_id and entry.details["mfa"]
    assert new_key not in str(entry.details) and new_secret not in str(entry.details)


def test_wrong_codes_count_towards_the_lockout_and_sign_the_operator_out(operator, shop):
    for _ in range(4):
        r = post(operator, "/internal/merchant/api-key/rotate", {"code": "123456"})
        assert r.status_code == 403
    r = post(operator, "/internal/merchant/api-key/rotate", {"code": "123456"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_locked"
    assert operator.get("/internal/me").status_code == 401  # signed out
    assert ApiKey.objects.active().get(merchant=shop.merchant).pk == shop.api_key.pk
    alert = SecurityAlert.objects.get(kind="staff_locked")
    assert alert.source == operator.account.public_id and alert.severity == "medium"


def test_rotate_without_a_key_is_refused(operator, shop):
    ApiKey.objects.filter(pk=shop.api_key.pk).update(revoked_at="2026-11-16T00:00:00Z")
    r = post(operator, "/internal/merchant/api-key/rotate", {"code": fresh_code(operator.account)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_active_api_key"


def test_only_operators_rotate_their_own_key(admin, staff_client):
    analyst = staff_client("fraud_analyst")
    for client in (admin, analyst):
        assert post(client, "/internal/merchant/api-key/rotate", {"code": "1"}).status_code == 403


# --- FR-MER-05: revoke with the last-key warning --------------------------------------------

def test_revoking_the_only_key_warns_first_then_revokes(operator, shop):
    r = post(operator, "/internal/merchant/api-key/revoke", {"code": fresh_code(operator.account)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_active_key"
    assert "generate a new key" in r.json()["error"]["message"]
    assert ApiKey.objects.active().filter(merchant=shop.merchant).count() == 1

    r = post(operator, "/internal/merchant/api-key/revoke",
             {"code": fresh_code(operator.account), "confirm_last_key": True})
    assert r.status_code == 200, r.content
    assert r.json()["api_key"] is None and r.json()["can_generate_key"] is True
    assert shop.create_payment().status_code == 401
    assert AuditEvent.objects.get(action="api_key.revoked").details["last_key"] is True

    # A new key can be generated afterwards (FR-MER-03 flow).
    r = post(operator, "/internal/merchant/api-key")
    assert r.status_code == 201
    shop.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['credentials']['api_key']}")
    assert shop.create_payment().status_code == 201


def test_revoke_with_a_wrong_code_changes_nothing(operator, shop):
    r = post(operator, "/internal/merchant/api-key/revoke",
             {"code": "999999", "confirm_last_key": True})
    assert r.status_code == 403
    assert shop.create_payment().status_code == 201


# --- FR-MER-09: cross-merchant access -------------------------------------------------------

def test_api_key_probing_another_merchants_payments_is_logged_and_alerted(
        shop, other_shop, settings):
    theirs = other_shop.create_payment().json()["id"]
    django_mail.outbox.clear()
    for _ in range(2):
        assert shop.get(f"/v1/payments/{theirs}").status_code == 404
    assert AuditEvent.objects.filter(action="security.cross_merchant_access").count() == 2
    assert not SecurityAlert.objects.exists()

    # A not-found ID that nobody owns is not an attempt on another merchant.
    assert shop.get("/v1/payments/pay_doesnotexist").status_code == 404
    assert AuditEvent.objects.filter(action="security.cross_merchant_access").count() == 2

    r = shop.post(f"/v1/payments/{theirs}/capture", {}, format="json",
                  headers={"Idempotency-Key": "probe-0001"})
    assert r.status_code == 404
    alert = SecurityAlert.objects.get(kind="cross_merchant_access")
    assert alert.source == shop.api_key.public_id and alert.severity == "high"
    assert alert.merchant_id == shop.merchant.public_id and alert.count == 1

    # Repeats are grouped into the same alert, and administrators are emailed once.
    shop.get(f"/v1/payments/{theirs}/refunds")
    alert.refresh_from_db()
    assert alert.count == 2 and SecurityAlert.objects.count() == 1
    entry = AuditEvent.objects.filter(action="security.cross_merchant_access").last()
    assert entry.details["owner_merchant_id"] == other_shop.merchant.public_id
    assert entry.target_id == theirs and entry.actor_type == "merchant_api"


def test_operator_probing_another_merchants_payment_is_logged(operator, other_shop, admin):
    theirs = other_shop.create_payment().json()["id"]
    for _ in range(3):
        assert operator.get(f"/internal/payments/{theirs}").status_code == 404
    alert = SecurityAlert.objects.get(kind="cross_merchant_access")
    assert alert.source == operator.account.public_id
    # An administrator reading any merchant's payment is allowed, not an attempt.
    assert admin.get(f"/internal/payments/{theirs}").status_code == 200
    assert AuditEvent.objects.filter(action="security.cross_merchant_access",
                                     actor_id=admin.account.public_id).count() == 0


# --- FR-ADM-08: alerts on the dashboard and by email ----------------------------------------

def test_alert_is_emailed_to_administrators_once_and_resolved_with_a_note(
        admin, shop, other_shop, client):
    make_staff_user("ops@securepay.sg", "administrator")
    theirs = other_shop.create_payment().json()["id"]
    django_mail.outbox.clear()
    for _ in range(5):
        shop.get(f"/v1/payments/{theirs}")
    send_due()
    subjects = [m.subject for m in django_mail.outbox]
    assert subjects.count("SecurePay: security alert: repeated cross-merchant access") == 2
    assert {m.to[0] for m in django_mail.outbox} >= {admin.account.email, "ops@securepay.sg"}

    count = admin.get("/internal/security/alerts/open-count").json()
    assert count["open"] == 1
    listed = admin.get("/internal/security/alerts").json()
    alert = listed["data"][0]
    assert alert["count"] == 3 and alert["kind_label"] == "Repeated cross-merchant access"
    detail = admin.get(f"/internal/security/alerts/{alert['id']}").json()
    actions = {e["action"] for e in detail["related_audit"]}
    assert "security.cross_merchant_access" in actions

    assert post(admin, f"/internal/security/alerts/{alert['id']}/resolve").status_code == 400
    r = post(admin, f"/internal/security/alerts/{alert['id']}/resolve",
             {"note": "Integration test script with a stale ID list; merchant told."})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert admin.get("/internal/security/alerts/open-count").json()["open"] == 0
    assert AuditEvent.objects.filter(action="security_alert.resolved").exists()
    again = post(admin, f"/internal/security/alerts/{alert['id']}/resolve", {"note": "x"})
    assert again.status_code == 409

    # After resolution, a new attempt burst opens a new alert.
    for _ in range(3):
        shop.get(f"/v1/payments/{theirs}")
    assert SecurityAlert.objects.filter(status="open").count() == 1


def test_only_administrators_see_security_alerts(staff_client, shop):
    for role, merchant in (("fraud_analyst", None), ("merchant_operator", shop.merchant)):
        client = staff_client(role, merchant=merchant)
        assert client.get("/internal/security/alerts").status_code == 403
        assert client.get("/internal/security/alerts/open-count").status_code == 403


def test_staff_lockout_at_sign_in_raises_an_alert(client, db):
    account = make_staff_user("analyst@securepay.sg", "fraud_analyst")
    for _ in range(5):
        client.post("/internal/auth/login", {"email": account.email, "password": "wrong" * 3},
                    content_type="application/json")
    alert = SecurityAlert.objects.get(kind="staff_locked")
    assert alert.source == account.public_id and "password" in alert.summary
    assert account.email not in alert.summary
    assert client.post("/internal/auth/login", {"email": account.email,
                                                "password": STAFF_PASSWORD},
                       content_type="application/json").status_code == 401


def test_payments_still_work_for_the_owner(shop):
    pid = shop.create_payment(valid_body()).json()["id"]
    assert shop.get(f"/v1/payments/{pid}").status_code == 200
    assert Payment.objects.filter(public_id=pid).exists()
    assert not AuditEvent.objects.filter(action="security.cross_merchant_access").exists()
