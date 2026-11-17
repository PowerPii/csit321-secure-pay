"""One-time backup codes for staff two-step verification (FR-ACC-14, D2).

A staff member who loses the phone with the authenticator app can still sign in with one of
these codes instead of the 6-digit TOTP code. The codes are made when the authenticator is
first set up and can be made again from the dashboard (which withdraws the old set).

* Each code is 10 characters from an alphabet without look-alike characters (about 49 bits),
  shown as `abcde-fghjk`. Case, spaces and the hyphen do not matter when it is typed.
* The plain code is shown once. The database keeps an HMAC-SHA256 of it (keyed from the
  Django SECRET_KEY and bound to the user), so a copy of the database alone is not enough
  to recover or test codes.
* A code works once. A wrong code counts towards the same lockout as a wrong password or
  TOTP code (STAFF_LOCKOUT_FAILURES), so codes cannot be guessed online.
"""
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.accounts.models import BackupCode

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/i/l
LENGTH = 10
_SALT = "securepay.accounts.backup-code"


def count() -> int:
    return settings.GATEWAY_RULES["STAFF_BACKUP_CODES"]


def normalise(code: str) -> str:
    return "".join(ch for ch in (code or "").lower() if ch not in " -\t")


def _digest(user_id: int, code: str) -> str:
    return salted_hmac(_SALT, f"{user_id}:{code}", algorithm="sha256").hexdigest()


def _new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return f"{raw[:5]}-{raw[5:]}"


def generate(user) -> list[str]:
    """A fresh set of codes for `user`; every earlier code stops working. Returns the plain
    codes, which are never stored and cannot be shown again."""
    codes = []
    while len(codes) < count():
        code = _new_code()
        if code not in codes:
            codes.append(code)
    with transaction.atomic():
        BackupCode.objects.filter(user=user).delete()
        BackupCode.objects.bulk_create(
            BackupCode(user=user, digest=_digest(user.pk, normalise(c))) for c in codes)
    return codes


def remaining(user) -> int:
    return BackupCode.objects.filter(user=user, used_at__isnull=True).count()


def status(user) -> dict:
    first = BackupCode.objects.filter(user=user).order_by("created_at").first()
    return {"remaining": remaining(user), "total": count(),
            "generated_at": first.created_at if first else None}


def use(user, code: str) -> bool:
    """Spend one code. True if it was a valid unused code of this user (now used)."""
    code = normalise(code)
    if len(code) != LENGTH or any(ch not in ALPHABET for ch in code):
        return False
    digest = _digest(user.pk, code)
    with transaction.atomic():
        candidates = (BackupCode.objects.select_for_update()
                      .filter(user=user, used_at__isnull=True))
        for row in candidates:
            if constant_time_compare(row.digest, digest):
                row.used_at = timezone.now()
                row.save(update_fields=["used_at"])
                return True
    return False
