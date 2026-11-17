"""One-time backup codes for staff two-step verification (FR-ACC-14, D2)."""
import pytest
from django.core import mail
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts import backup_codes
from apps.accounts.models import BackupCode, StaffAccount
from apps.audit.models import AuditEvent
from conftest import current_totp, make_staff_user

from .tests import PASSWORD, csrf_client, login, totp

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


@pytest.fixture
def admin():
    return make_staff_user("admin@securepay.sg", "administrator", password=PASSWORD)


def backup(client, code):
    return client.post("/internal/auth/backup-code", {"code": code},
                       content_type="application/json")


def fresh_totp(account):
    """The current code again (django-otp refuses a code twice in the same 30 s step)."""
    TOTPDevice.objects.filter(user=account.user).update(last_t=-1)
    return current_totp(account)


def signed_in(account):
    client = csrf_client()
    login(client, account.email)
    assert totp(client, fresh_totp(account)).status_code == 200
    client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
    return client


def test_first_setup_returns_ten_codes_once_and_stores_only_digests():
    account = make_staff_user("new@securepay.sg", "fraud_analyst", password=PASSWORD,
                              with_device=False)
    client = csrf_client()
    login(client, "new@securepay.sg")
    device = TOTPDevice.objects.get(user=account.user, confirmed=False)
    r = totp(client, current_totp(account, device))
    assert r.status_code == 200, r.content
    codes = r.json()["backup_codes"]
    assert len(codes) == 10 == len(set(codes))
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    assert r.json()["backup_codes_left"] == 10
    stored = set(BackupCode.objects.filter(user=account.user).values_list("digest", flat=True))
    assert len(stored) == 10
    assert not any(c in d or c.replace("-", "") in d for c in codes for d in stored)
    event = AuditEvent.objects.get(action="staff.backup_codes_generated")
    assert event.details == {"count": 10, "reason": "setup"}
    assert "backup_codes" not in str(event.details.values())


def test_a_normal_sign_in_does_not_show_codes(admin):
    client = csrf_client()
    login(client, admin.email)
    r = totp(client, current_totp(admin))
    assert r.status_code == 200 and "backup_codes" not in r.json()


def test_backup_code_signs_in_once_and_emails_the_holder(admin):
    codes = backup_codes.generate(admin.user)
    client = csrf_client()
    login(client, admin.email)
    assert client.get("/internal/me").status_code == 401
    r = backup(client, codes[3].upper().replace("-", " "))  # case and spacing do not matter
    assert r.status_code == 200, r.content
    assert r.json()["backup_codes_left"] == 9
    assert client.get("/internal/me").status_code == 200
    event = AuditEvent.objects.get(action="staff.signed_in", actor_id=admin.public_id)
    assert event.details == {"mfa_setup": False, "method": "backup_code",
                             "backup_codes_left": 9}
    assert len(mail.outbox) == 1 and "backup code was used" in mail.outbox[0].subject
    assert "9 backup codes left" in mail.outbox[0].body

    # The same code does not work a second time.
    again = csrf_client()
    login(again, admin.email)
    r = backup(again, codes[3])
    assert r.status_code == 401 and r.json()["error"]["code"] == "code_incorrect"
    assert again.get("/internal/me").status_code == 401


def test_backup_code_needs_the_password_step_first(admin):
    codes = backup_codes.generate(admin.user)
    client = csrf_client()
    r = backup(client, codes[0])
    assert r.status_code == 401 and r.json()["error"]["code"] == "sign_in_required"
    assert BackupCode.objects.filter(used_at__isnull=False).count() == 0


def test_another_staff_members_code_does_not_work(admin):
    other = make_staff_user("other@securepay.sg", "fraud_analyst", password=PASSWORD)
    codes = backup_codes.generate(other.user)
    backup_codes.generate(admin.user)
    client = csrf_client()
    login(client, admin.email)
    assert backup(client, codes[0]).status_code == 401


def test_wrong_backup_codes_count_towards_the_lockout(admin):
    backup_codes.generate(admin.user)
    client = csrf_client()
    for _ in range(2):
        assert login(client, admin.email, "wrong password!").status_code == 401
    assert login(client, admin.email).status_code == 200
    assert totp(client, "000000").status_code == 401
    assert backup(client, "aaaaa-aaaaa").status_code == 401
    r = backup(client, "not a code")
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_locked"
    # Locked: the password step is refused, so no code can be tried.
    assert login(client, admin.email).json()["error"]["code"] == "account_locked"
    assert StaffAccount.objects.get(pk=admin.pk).is_locked()
    assert BackupCode.objects.filter(user=admin.user, used_at__isnull=False).count() == 0
    assert AuditEvent.objects.filter(action="staff.sign_in_failed",
                                     details__stage="backup_code").count() == 2


def test_no_backup_code_before_the_authenticator_is_set_up():
    account = make_staff_user("new@securepay.sg", "fraud_analyst", password=PASSWORD,
                              with_device=False)
    client = csrf_client()
    login(client, account.email)
    r = backup(client, "abcde-fghjk")
    assert r.status_code == 409 and r.json()["error"]["code"] == "setup_required"


def test_regenerate_needs_the_authenticator_code_and_replaces_the_old_set(admin):
    old = backup_codes.generate(admin.user)
    client = signed_in(admin)
    status = client.get("/internal/me/backup-codes").json()
    assert status["remaining"] == 10 and status["total"] == 10 and status["generated_at"]

    r = client.post("/internal/me/backup-codes", {"code": "000000"},
                    content_type="application/json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "code_incorrect"
    assert backup_codes.remaining(admin.user) == 10

    r = client.post("/internal/me/backup-codes", {"code": fresh_totp(admin)},
                    content_type="application/json")
    assert r.status_code == 200, r.content
    new = r.json()["codes"]
    assert len(new) == 10 and not set(new) & set(old)
    assert AuditEvent.objects.filter(action="staff.backup_codes_generated",
                                     details__reason="regenerated").count() == 1
    # Old codes are gone; new ones work.
    other = csrf_client()
    login(other, admin.email)
    assert backup(other, old[0]).status_code == 401
    assert backup(other, new[0]).status_code == 200


def test_backup_codes_page_needs_a_full_sign_in(admin):
    client = csrf_client()
    assert client.get("/internal/me/backup-codes").status_code == 401
    login(client, admin.email)  # password only
    assert client.get("/internal/me/backup-codes").status_code == 401


def test_me_reports_how_many_codes_are_left(admin):
    client = signed_in(admin)
    assert client.get("/internal/me").json()["backup_codes_left"] == 0  # account from before
    backup_codes.generate(admin.user)
    assert client.get("/internal/me").json()["backup_codes_left"] == 10


def test_normalise_and_malformed_codes():
    assert backup_codes.normalise(" ABCDE-fghjk ") == "abcdefghjk"
    user = make_staff_user("x@securepay.sg", "fraud_analyst", password=PASSWORD).user
    backup_codes.generate(user)
    assert backup_codes.use(user, "") is False
    assert backup_codes.use(user, "0000000000") is False  # 0 is not in the alphabet
    assert backup_codes.use(user, "a" * 64) is False


def test_reset_command_brings_back_first_time_setup(admin):
    from django.core.management import call_command

    backup_codes.generate(admin.user)
    call_command("reset_staff_mfa", "ADMIN@securepay.sg")
    assert not TOTPDevice.objects.filter(user=admin.user).exists()
    assert backup_codes.remaining(admin.user) == 0
    assert AuditEvent.objects.filter(action="staff.mfa_reset", target_id=admin.public_id).exists()
    client = csrf_client()
    assert login(client, admin.email).json()["setup"] is not None
