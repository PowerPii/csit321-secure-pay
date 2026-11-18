"""Integrity, key rotation, self-checks, clean-up and the payment timeline: FR-ADM-09,
FR-ADM-14, FR-ADM-15, FR-TXN-16, NFR-INT-02, NFR-ENC-03, NFR-PRI-01, NFR-PRI-02."""
import logging
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditSeal
from apps.audit.models import record as audit
from apps.common import crypto
from apps.common.logmask import MaskPersonalData, mask_text
from apps.events.models import OutboundEmail
from apps.payments.models import Payment
from apps.payments.states import PaymentStatus
from apps.security import integrity, keyring, maintenance, retention, selfchecks
from apps.security.models import AlertKind, DataKey, MaintenanceRun, SecurityAlert
from apps.security.tests import fresh_code
from apps.vault import service as vault
from apps.vault.models import StoredCard
from conftest import valid_body

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


def post(client, path, body=None):
    return client.post(path, body or {}, content_type="application/json")


@pytest.fixture
def admin(staff_client):
    return staff_client("administrator")


@pytest.fixture
def no_grace(settings):
    settings.GATEWAY_RULES = {**settings.GATEWAY_RULES, "AUDIT_SEAL_GRACE_SECONDS": 0}


def make_payment(shop, **overrides) -> Payment:
    r = shop.create_payment(valid_body(**overrides))
    assert r.status_code == 201, r.content
    return Payment.objects.get(public_id=r.json()["id"])


class tampering:
    """Change audit rows directly in the database, as someone with SQL access would."""

    def __enter__(self):
        with connection.cursor() as cur:
            cur.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_auditevent_append_only")
            cur.execute("ALTER TABLE audit_auditseal DISABLE TRIGGER audit_auditseal_append_only")
        return connection.cursor()

    def __exit__(self, *exc):
        with connection.cursor() as cur:
            cur.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_auditevent_append_only")
            cur.execute("ALTER TABLE audit_auditseal ENABLE TRIGGER audit_auditseal_append_only")


# --- FR-ADM-14 / NFR-ENC-03: key rotation -------------------------------------------------

def test_rotation_keeps_every_existing_value_readable():
    legacy_card = vault._encrypt_legacy(b"card-before-keyring", "tok_a")
    legacy_field = crypto.encrypt_legacy("secret-before-keyring")
    before_card = vault._encrypt(b"card-under-key-1", "tok_b")
    before_field = crypto.encrypt("secret-under-key-1")
    first = DataKey.objects.get(purpose="vault", status="active")

    new, old = keyring.rotate("vault", "stf_test")
    keyring.rotate("field", "stf_test")
    assert old.key_id == first.key_id and new.key_id != first.key_id
    old.refresh_from_db()
    assert old.status == "decrypt_only" and old.retired_by == "stf_test"
    after_card = vault._encrypt(b"card-under-key-2", "tok_c")
    assert keyring.key_id_of(after_card) == new.key_id  # new data uses the new key

    keyring.forget_all()  # as a fresh process would: every key unwrapped from the database
    assert vault._decrypt(legacy_card, "tok_a") == b"card-before-keyring"
    assert vault._decrypt(before_card, "tok_b") == b"card-under-key-1"
    assert vault._decrypt(after_card, "tok_c") == b"card-under-key-2"
    assert crypto.decrypt(legacy_field) == "secret-before-keyring"
    assert crypto.decrypt(before_field) == "secret-under-key-1"


def test_card_tokenised_before_a_rotation_is_still_taken(shop):
    summary = vault.tokenise("4242424242424242", 12, 2030, "123",
                             expires_at=timezone.now() + timedelta(hours=1))
    keyring.rotate("vault", "stf_test")
    keyring.forget_all()
    assert vault.take(summary.token).number == "4242424242424242"
    assert shop.merchant.signing_secret  # field-encrypted secret still opens


def test_data_keys_are_stored_wrapped_never_in_the_clear():
    crypto.encrypt("x")
    key = DataKey.objects.get(purpose="field")
    raw = keyring.key_bytes(key.key_id)
    assert len(raw) == 32
    import base64
    assert raw not in base64.b64decode(key.wrapped_key)


def test_key_report_flags_an_active_key_older_than_90_days():
    report = keyring.report()
    assert {r["purpose"] for r in report} == {"vault", "field"}
    assert not any(r["overdue"] for r in report)
    DataKey.objects.filter(purpose="vault").update(created_at=timezone.now() - timedelta(days=91))
    vault_row = next(r for r in keyring.report() if r["purpose"] == "vault")
    assert vault_row["overdue"] and vault_row["age_days"] == 91


def test_rotate_endpoint_needs_the_authenticator_code(admin, staff_client):
    r = post(admin, "/internal/security/keys/rotate", {"purpose": "vault", "code": "000000"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "code_incorrect"
    assert not AuditEvent.objects.filter(action="security.key_rotated").exists()

    before = keyring.active_key_id("vault")
    r = post(admin, "/internal/security/keys/rotate",
             {"purpose": "vault", "code": fresh_code(admin.account)})
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["rotated"]["previous_key"] == before
    statuses = {k["id"]: k["status"] for k in body["keys"]}
    assert statuses[before] == "decrypt_only" and statuses[body["rotated"]["new_key"]] == "active"
    entry = AuditEvent.objects.get(action="security.key_rotated")
    assert entry.actor_id == admin.account.public_id and entry.details["previous_key"] == before

    analyst = staff_client("fraud_analyst")
    assert post(analyst, "/internal/security/keys/rotate", {"purpose": "vault"}).status_code == 403


# --- FR-ADM-09: payment integrity hashes --------------------------------------------------

def test_payment_hash_is_kept_current_and_a_direct_change_is_flagged(shop):
    payment = make_payment(shop)
    assert payment.integrity_hash == integrity.payment_digest(payment)
    payment.status = "blocked"
    payment.save(update_fields=["status"])
    payment.refresh_from_db()
    assert payment.integrity_hash == integrity.payment_digest(payment)
    assert integrity.check_payments()["problems"] == 0

    Payment.objects.filter(pk=payment.pk).update(amount=99)  # behind the application's back
    result = integrity.check_payments()
    assert result["problems"] == 1
    assert result["findings"] == [{"payment_id": payment.public_id, "reference": payment.reference}]


def test_payments_from_before_the_hash_are_baselined_not_flagged(shop):
    payment = make_payment(shop)
    Payment.objects.filter(pk=payment.pk).update(integrity_hash="")
    result = integrity.check_payments()
    assert (result["baselined"], result["problems"]) == (1, 0)
    payment.refresh_from_db()
    assert payment.integrity_hash == integrity.payment_digest(payment)


def test_integrity_run_raises_one_high_alert_on_a_mismatch(shop, no_grace):
    payment = make_payment(shop)
    Payment.objects.filter(pk=payment.pk).update(captured_amount=50)
    run = integrity.run_check()
    assert run.outcome == "problems" and run.summary["payments"]["problems"] == 1
    alert = SecurityAlert.objects.get(kind=AlertKind.INTEGRITY_MISMATCH)
    assert alert.severity == "high" and alert.details["run_id"] == run.public_id


# --- NFR-INT-02: the audit hash chain -----------------------------------------------------

def test_ten_entries_edited_deleted_or_reordered_are_all_detected(no_grace):
    events = [audit("test.event", actor_type="system", target_id=f"t{i}",
                    details={"n": i}) for i in range(30)]
    assert integrity.seal_pending() == 30
    assert integrity.check_audit_chain()["problems"] == 0

    edited, deleted, moved = events[3:7], events[10:13], events[20:23]
    with tampering() as cur:
        for e in edited:
            cur.execute("UPDATE audit_auditevent SET details = '{\"n\": -1}' WHERE id = %s", [e.id])
        for e in deleted:
            cur.execute("DELETE FROM audit_auditevent WHERE id = %s", [e.id])
        for e in moved:  # reordered: moved to before the first entry
            cur.execute("UPDATE audit_auditevent SET occurred_at = occurred_at - interval '1 day'"
                        " WHERE id = %s", [e.id])
    result = integrity.check_audit_chain()
    flagged = {f["event_id"] for f in result["findings"] if "event_id" in f}
    assert flagged == {e.id for e in edited + deleted + moved}
    assert result["counts"]["edited"] == 7 and result["counts"]["deleted"] == 3


def test_removing_a_seal_or_adding_an_entry_below_the_head_breaks_the_chain(no_grace):
    events = [audit("test.event", actor_type="system", target_id=f"t{i}") for i in range(5)]
    integrity.seal_pending()
    with tampering() as cur:
        cur.execute("DELETE FROM audit_auditseal WHERE event_id = %s", [events[2].id])
    result = integrity.check_audit_chain()
    assert result["counts"]["chain_broken"] == 1 and result["counts"]["inserted"] == 1


def test_audit_rows_and_seals_cannot_be_changed_through_the_application(no_grace):
    audit("test.event", actor_type="system")
    integrity.seal_pending()
    with pytest.raises(PermissionError):
        AuditSeal.objects.all().delete()


def test_entries_are_sealed_only_after_the_grace_period():
    audit("test.event", actor_type="system")
    assert integrity.seal_pending() == 0  # 120 s grace by default
    assert integrity.check_audit_chain()["unsealed_recent"] >= 1


# --- FR-TXN-16: correlation ID and timeline -----------------------------------------------

def test_audit_entries_carry_the_payment_correlation_id():
    e = audit("payment.created", actor_type="system", target_type="payment", target_id="pay_x")
    r = audit("refund.created", actor_type="system", target_type="refund", target_id="ref_y",
              details={"payment_id": "pay_x"})
    other = audit("staff.created", actor_type="system", target_type="staff", target_id="stf_z")
    assert (e.correlation_id, r.correlation_id, other.correlation_id) == ("pay_x", "pay_x", "")


def test_payment_detail_shows_one_timeline_under_one_correlation_id(admin, shop):
    payment = make_payment(shop)
    OutboundEmail.objects.create(public_id="eml_test", kind=OutboundEmail.Kind.values[0],
                                 payment=payment, to="jane@example.com", subject="Receipt",
                                 next_attempt_at=timezone.now())
    body = admin.get(f"/internal/payments/{payment.public_id}").json()
    assert body["correlation_id"] == payment.public_id
    kinds = [row["kind"] for row in body["trail"]]
    assert kinds[0] == "payment" and "audit" in kinds and "email" in kinds
    assert {row["correlation_id"] for row in body["trail"]} == {payment.public_id}
    assert "jane@example.com" not in str(body["trail"])


# --- FR-ADM-15 / NFR-PRI-02: self-checks ---------------------------------------------------

def test_self_checks_report_each_practice(no_grace):
    run = selfchecks.run()
    results = {c["id"]: c for c in run.summary["checks"]}
    assert set(results) == {"https", "no_card_data_after_submission", "masking",
                            "encryption_at_rest", "key_age", "staff_mfa", "audit_trail"}
    assert all(c["status"] in ("passed", "failed", "not_checked") and c["practice"]
               for c in results.values())
    assert results["key_age"]["status"] == "passed"
    assert results["encryption_at_rest"]["status"] == "passed"
    assert results["audit_trail"]["status"] == "not_checked"  # no integrity run yet
    integrity.run_check()
    results = {c["id"]: c for c in selfchecks.run().summary["checks"]}
    assert results["audit_trail"]["status"] == "passed"


def test_card_kept_after_submission_and_an_old_key_fail_their_checks(shop):
    payment = make_payment(shop)
    summary = vault.tokenise("4242424242424242", 12, 2030, "123",
                             expires_at=timezone.now() + timedelta(hours=1))
    Payment.objects.filter(pk=payment.pk).update(card_token=summary.token,
                                                 submitted_at=timezone.now())
    keyring.active_key_id("field")
    DataKey.objects.filter(purpose="field").update(created_at=timezone.now() - timedelta(days=95))
    run = selfchecks.run()
    results = {c["id"]: c["status"] for c in run.summary["checks"]}
    assert results["no_card_data_after_submission"] == "failed"
    assert results["key_age"] == "failed"
    assert run.outcome == "problems"
    kinds = set(SecurityAlert.objects.values_list("kind", flat=True))
    assert {AlertKind.KEY_AGE, AlertKind.SELF_CHECK_FAILED} <= kinds
    StoredCard.objects.using("vault").all().delete()


def test_card_held_for_a_verification_code_does_not_fail_the_check(shop):
    """The card stays in the vault while the customer has the code page open (FR-CHK-18)."""
    payment = make_payment(shop)
    summary = vault.tokenise("4242424242424242", 12, 2030, "123",
                             expires_at=timezone.now() + timedelta(hours=1))
    Payment.objects.filter(pk=payment.pk).update(
        card_token=summary.token, submitted_at=timezone.now(),
        status=PaymentStatus.VERIFICATION_REQUIRED,
        checkout_expires_at=timezone.now() + timedelta(minutes=30))
    assert selfchecks.no_card_data_after_submission()[0] == "passed"
    Payment.objects.filter(pk=payment.pk).update(  # session over, card still there: fails
        checkout_expires_at=timezone.now() - timedelta(minutes=1))
    assert selfchecks.no_card_data_after_submission()[0] == "failed"
    StoredCard.objects.using("vault").all().delete()


def test_staff_without_mfa_who_signed_in_fails_the_check():
    from conftest import make_staff_user

    account = make_staff_user("nomfa@securepay.sg", "administrator", with_device=False)
    assert selfchecks.staff_mfa()[0] == "passed"  # never signed in: must enrol first
    account.last_sign_in_at = timezone.now()
    account.save(update_fields=["last_sign_in_at"])
    assert selfchecks.staff_mfa()[0] == "failed"


# --- NFR-PRI-01: retention and masking ----------------------------------------------------

def test_clean_up_anonymises_records_older_than_12_months(shop, no_grace):
    old, recent = make_payment(shop), make_payment(shop)
    for p in (old, recent):
        Payment.objects.filter(pk=p.pk).update(customer_email="jane@example.com")
    Payment.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=400))
    old.refresh_from_db()
    Payment.objects.filter(pk=old.pk).update(integrity_hash=integrity.payment_digest(old))
    email = OutboundEmail.objects.create(public_id="eml_old", kind=OutboundEmail.Kind.values[0],
                                         payment=old, to="jane@example.com", subject="Receipt",
                                         next_attempt_at=timezone.now())
    OutboundEmail.objects.filter(pk=email.pk).update(created_at=timezone.now() - timedelta(days=400))

    run = retention.run()
    assert run.summary["counts"]["payments_anonymised"] == 1
    assert run.summary["counts"]["emails_deleted"] == 1
    old.refresh_from_db()
    recent.refresh_from_db()
    assert old.customer_email == "" and recent.customer_email == "jane@example.com"
    assert integrity.check_payments()["problems"] == 0  # the clean-up never breaks the hash
    assert AuditEvent.objects.filter(action="security.retention_cleanup").exists()


def test_emails_and_phone_numbers_are_masked_in_logs_and_audit_details(caplog):
    assert mask_text("sent to jane.doe@example.com") == "sent to j•••@example.com"
    assert mask_text("call +65 9123 4567") == "call ••••••••67"
    assert mask_text("at 2026-11-16 12:30:45 for pay_ABC123") == "at 2026-11-16 12:30:45 for pay_ABC123"
    entry = audit("test.event", actor_type="system", details={"to": "jane@example.com", "n": 5})
    assert entry.details == {"to": "j•••@example.com", "n": 5}

    logger = logging.getLogger("test.masking")
    logger.addFilter(MaskPersonalData())
    with caplog.at_level(logging.INFO, logger="test.masking"):
        logger.info("Email to %s failed", "jane@example.com")
    assert "jane@example.com" not in caplog.text and "j•••@example.com" in caplog.text


# --- scheduling and the admin page ---------------------------------------------------------

def test_worker_runs_each_kind_once_per_interval(no_grace):
    runs = maintenance.run_due()
    assert sorted(r.kind for r in runs) == ["integrity", "retention", "self_check"]
    assert maintenance.run_due() == []
    MaintenanceRun.objects.filter(kind="integrity").update(
        started_at=timezone.now() - timedelta(hours=7))
    assert [r.kind for r in maintenance.run_due()] == ["integrity"]


def test_admin_page_runs_checks_on_demand(admin, staff_client, no_grace):
    r = admin.get("/internal/integrity")
    assert r.status_code == 200 and r.json()["runs"]["integrity"] is None
    assert len(r.json()["keys"]) == 2
    r = post(admin, "/internal/integrity/run", {"kind": "integrity"})
    assert r.status_code == 200, r.content
    run = r.json()["run"]
    assert run["outcome"] == "passed" and run["started_by"] == admin.account.public_id
    assert admin.get(f"/internal/integrity/runs/{run['id']}").json()["summary"]["audit"]
    assert admin.get("/internal/integrity/runs?kind=integrity").json()["count"] == 1
    assert post(admin, "/internal/integrity/run", {"kind": "nope"}).status_code == 400
    assert staff_client("fraud_analyst").get("/internal/integrity").status_code == 403
