"""API key authentication and merchant status (API-CONTRACT.md section 2)."""
import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.events.signing import verify
from apps.merchants.models import ApiKey, Merchant, digest_api_key

pytestmark = pytest.mark.django_db


def test_only_a_digest_of_the_key_is_stored(shop):
    stored = ApiKey.objects.get(pk=shop.api_key.pk)
    assert stored.digest == digest_api_key(shop.key)
    assert shop.key not in {stored.digest, stored.hint}
    assert shop.key.startswith("sp_test_") and len(shop.key) == 48


def test_signing_secret_is_stored_encrypted(shop):
    stored = Merchant.objects.get(pk=shop.merchant.pk)
    assert shop.secret.startswith("whsec_")
    assert shop.secret not in stored.signing_secret_encrypted
    assert stored.signing_secret == shop.secret


def test_one_active_key_per_merchant(shop):
    with pytest.raises(IntegrityError), transaction.atomic():
        ApiKey.issue(shop.merchant)


@pytest.mark.parametrize("header", [
    None, "Bearer", "Basic abc", "Bearer sp_test_short",
    "Bearer sp_test_" + "A" * 40,  # well-formed but unknown
])
def test_missing_or_unknown_key_is_401_and_unsigned(client, db, header, error_schema):
    headers = {"Authorization": header} if header else {}
    response = client.get("/v1/payments/pay_" + "A" * 24, headers=headers)
    assert response.status_code == 401
    body = response.json()
    error_schema.validate(body)
    assert body["error"]["code"] == "api_key_invalid"
    assert body["error"]["request_id"] == response["SecurePay-Request-Id"]
    assert "SecurePay-Signature" not in response
    assert response["WWW-Authenticate"].startswith("Bearer")


def test_revoked_key_is_401(shop):
    ApiKey.objects.filter(pk=shop.api_key.pk).update(revoked_at=timezone.now())
    assert shop.get("/v1/payments/pay_" + "A" * 24).status_code == 401


@pytest.mark.parametrize("status", ["pending", "rejected", "suspended"])
def test_inactive_merchant_is_403_and_signed(make_merchant, status, error_schema):
    shop = make_merchant(status=status)
    response = shop.create_payment()
    assert response.status_code == 403
    error_schema.validate(response.json())
    assert response.json()["error"]["code"] == "merchant_not_active"
    assert verify(response.content, response["SecurePay-Signature"], shop.secret)


def test_rate_limit_is_per_key(shop, other_shop, settings):
    settings.GATEWAY_RULES = {**settings.GATEWAY_RULES, "API_RATE_LIMIT_PER_MINUTE": 3}
    url = "/v1/payments/pay_" + "A" * 24
    for _ in range(3):
        assert shop.get(url).status_code == 404
    limited = shop.get(url)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert int(limited["Retry-After"]) >= 1
    assert other_shop.get(url).status_code == 404  # other keys are not affected


# --- demo_check (demo-day polish) -----------------------------------------------------------

def test_demo_check_renames_with_an_audit_event_and_reports(make_merchant, settings):
    from io import StringIO

    from django.core.management import call_command

    from apps.audit.models import AuditEvent

    settings.RISK_MODEL_VERSION = ""
    shop = make_merchant(webhook_url="https://shop.example/webhooks/securepay",
                         webhook_url_approved=True).merchant
    out = StringIO()
    call_command("demo_check", merchant=shop.public_id, rename="Volt & Co.", stdout=out)
    shop.refresh_from_db()
    assert shop.name == "Volt & Co."
    event = AuditEvent.objects.get(action="merchant.renamed")
    assert event.details == {"from": "Demo Shop", "to": "Volt & Co."}
    text = out.getvalue()
    assert "PASS  Merchant 'Volt & Co.' is active" in text and "0 failed" in text


def test_demo_check_fails_without_webhook(make_merchant, settings):
    from io import StringIO

    import pytest
    from django.core.management import call_command

    settings.RISK_MODEL_VERSION = ""
    shop = make_merchant().merchant
    out = StringIO()
    with pytest.raises(SystemExit):
        call_command("demo_check", merchant=shop.public_id, stdout=out)
    assert "FAIL  Webhook URL missing" in out.getvalue()


def test_demo_check_finds_the_merchant_by_name(make_merchant, settings):
    from io import StringIO

    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.RISK_MODEL_VERSION = ""
    with pytest.raises(CommandError, match="No merchant named"):
        call_command("demo_check", stdout=StringIO())
    make_merchant(name="Volt & Co.", webhook_url="https://shop.example/webhooks/securepay",
                  webhook_url_approved=True)
    out = StringIO()
    call_command("demo_check", stdout=out)
    assert "PASS  Merchant 'Volt & Co.' is active" in out.getvalue()
    make_merchant(name="Volt & Co.")
    with pytest.raises(CommandError, match="More than one"):
        call_command("demo_check", stdout=StringIO())


# --- seed_demo (demo sprint 15) ----------------------------------------------------------------

def test_seed_demo_sets_up_a_fresh_stack_once(db):
    import re
    from io import StringIO

    from django.contrib.auth import authenticate
    from django.core.management import call_command

    from apps.accounts.models import Role, StaffAccount
    from apps.audit.models import AuditEvent
    from apps.risk.models import RiskListEntry

    out = StringIO()
    call_command("seed_demo", webhook_url="https://shop.localhost/webhooks/securepay",
                 stdout=out)
    text = out.getvalue()
    shop = Merchant.objects.get(name="Volt & Co.")
    assert shop.status == Merchant.Status.ACTIVE and shop.webhook_url_approved
    key = re.search(r"API key:\s+(\S+)", text).group(1)
    assert ApiKey.objects.get(merchant=shop).digest == digest_api_key(key)
    assert re.search(r"Signing secret:\s+(\S+)", text).group(1) == shop.signing_secret
    assert f"Demo merchant ID: {shop.public_id}" in text

    staff = {a.user.email: a for a in StaffAccount.objects.select_related("user")}
    assert staff["ops@demoshop.sg"].role == Role.MERCHANT_OPERATOR
    assert staff["ops@demoshop.sg"].merchant == shop
    assert staff["admin@securepay.sg"].merchant is None
    password = re.search(r"Temporary password for analyst@securepay.sg: (\S+)", text).group(1)
    assert authenticate(username="analyst@securepay.sg", password=password) is not None
    assert RiskListEntry.objects.count() == 3
    assert AuditEvent.objects.filter(action="staff.created").count() == 3

    again = StringIO()
    call_command("seed_demo", stdout=again)
    assert Merchant.objects.count() == 1 and ApiKey.objects.count() == 1
    assert StaffAccount.objects.count() == 3
    assert "API key:" not in again.getvalue() and "Temporary password" not in again.getvalue()
    assert "already exists" in again.getvalue()


def test_seed_demo_needs_a_webhook_url_for_a_new_merchant(db):
    from io import StringIO

    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="--webhook-url"):
        call_command("seed_demo", stdout=StringIO())
    assert not Merchant.objects.exists()


# --- change_domain (sprint 12: server and domain move) --------------------------------------

def test_change_domain_moves_matching_webhook_urls_with_an_audit_event(make_merchant):
    from io import StringIO

    from django.core.management import call_command

    from apps.audit.models import AuditEvent

    old = "35-213-144-96.sslip.io"
    shop = make_merchant(webhook_url=f"https://shop.{old}/webhooks/securepay?v=1",
                         webhook_url_approved=True).merchant
    other = make_merchant(name="Other Shop",
                          webhook_url="https://shop.other-example.sg/hook").merchant
    out = StringIO()
    call_command("change_domain", old=old, new="SecurePay-Demo.me.", stdout=out)
    shop.refresh_from_db()
    other.refresh_from_db()
    assert shop.webhook_url == "https://shop.securepay-demo.me/webhooks/securepay?v=1"
    assert shop.webhook_url_approved is True
    assert other.webhook_url == "https://shop.other-example.sg/hook"
    event = AuditEvent.objects.get(action="merchant.webhook_url_moved")
    assert event.merchant_id == shop.public_id
    assert event.details["to"] == shop.webhook_url
    assert "Moved 1 webhook URL(s)" in out.getvalue()


def test_change_domain_dry_run_and_lookalike_hosts_change_nothing(make_merchant):
    from io import StringIO

    from django.core.management import call_command

    from apps.audit.models import AuditEvent

    shop = make_merchant(webhook_url="https://shop.example.sg/hook").merchant
    lookalike = make_merchant(name="Lookalike",
                              webhook_url="https://notexample.sg/hook").merchant
    out = StringIO()
    call_command("change_domain", old="example.sg", new="example.me", dry_run=True, stdout=out)
    shop.refresh_from_db()
    assert shop.webhook_url == "https://shop.example.sg/hook"
    assert "Would move 1 webhook URL(s)" in out.getvalue()
    call_command("change_domain", old="example.sg", new="example.me", stdout=StringIO())
    lookalike.refresh_from_db()
    assert lookalike.webhook_url == "https://notexample.sg/hook"
    assert AuditEvent.objects.filter(action="merchant.webhook_url_moved").count() == 1


def test_change_domain_rejects_urls_instead_of_domains(db):
    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("change_domain", old="https://shop.example.sg", new="example.me")
