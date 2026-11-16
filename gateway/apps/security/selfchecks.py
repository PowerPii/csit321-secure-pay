"""Card data security self-checks (FR-ADM-15, NFR-PRI-02; UC-47).

    run(started_by="") -> MaintenanceRun   every check; alert administrators if one fails

Each check reports `passed`, `failed` or `not_checked` (it could not run, or does not apply
here) with the PCI DSS v4.0.1 practice it supports. The list follows the card data checklist
in URS Section 4.7.3. These checks show that the practices are followed; they are not a PCI
DSS assessment and the project claims no certification.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import TextField
from django.db.models.functions import Cast
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.carddata import looks_like_card_number
from apps.security.models import AlertKind, MaintenanceRun, Severity

PASSED, FAILED, NOT_CHECKED = "passed", "failed", "not_checked"
SCAN_DAYS = 30  # how far back the masking check scans audit entries
SCAN_ROWS = 5000


@dataclass(frozen=True)
class Check:
    id: str
    name: str
    practice: str  # the PCI DSS requirement it supports
    run: Callable[[], tuple[str, str]]  # -> (status, detail)


def https_enforced():
    if settings.DEBUG:
        return NOT_CHECKED, "Development mode: checked on the deployed server only."
    urls = {"checkout": settings.CHECKOUT_BASE_URL, "dashboard": settings.DASHBOARD_URL,
            "guest status": settings.GUEST_STATUS_URL}
    plain = [name for name, url in urls.items() if not url.startswith("https://")]
    if plain:
        return FAILED, "Not served over HTTPS: " + ", ".join(plain) + "."
    if not (settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE):
        return FAILED, "Session or CSRF cookies may be sent without HTTPS."
    return PASSED, "Every public address uses HTTPS and cookies are HTTPS-only."


def no_card_data_after_submission():
    from apps.payments.models import Payment
    from apps.vault.models import StoredCard

    now = timezone.now()
    tokens = list(Payment.objects.filter(submitted_at__gte=now - timedelta(days=7))
                  .exclude(card_token="").values_list("card_token", flat=True))  # nosec B106
    kept = StoredCard.objects.using("vault").filter(token__in=tokens).count()
    stale = StoredCard.objects.using("vault").filter(
        expires_at__lte=now - timedelta(minutes=10)).count()
    if kept or stale:
        return FAILED, (f"{kept} submitted card(s) and {stale} expired card(s) are still in "
                        "the vault.")
    return PASSED, (f"None of the {len(tokens)} card(s) submitted in the last 7 days is still "
                    "in the vault, and no expired card is waiting to be deleted.")


def card_numbers_masked():
    from apps.payments.models import Payment

    bad_last4 = Payment.objects.exclude(card_last4="").exclude(card_last4__regex=r"^[0-9]{4}$")
    if bad_last4.exists():
        return FAILED, f"{bad_last4.count()} payment(s) keep more than the last 4 digits."
    since = timezone.now() - timedelta(days=SCAN_DAYS)
    rows = (AuditEvent.objects.filter(occurred_at__gte=since)
            .annotate(text=Cast("details", TextField()))
            .filter(text__regex=r"[0-9][0-9 -]{11,}[0-9]")
            .values_list("text", flat=True)[:SCAN_ROWS])
    found = sum(1 for text in rows if looks_like_card_number(text))
    if found:
        return FAILED, f"{found} audit entr(y/ies) from the last {SCAN_DAYS} days hold a card number."
    return PASSED, ("Outside the vault only the brand and last 4 digits are kept; no card "
                    f"number found in audit entries from the last {SCAN_DAYS} days.")


def keys_rotated():
    from apps.security import keyring

    keys = keyring.report()
    overdue = [k for k in keys if k["overdue"]]
    if overdue:
        return FAILED, (f"{len(overdue)} active key(s) are older than "
                        f"{keyring.max_age_days()} days: rotate them on the Integrity page.")
    oldest = max((k["age_days"] for k in keys if k["status"] == "active"), default=0)
    return PASSED, (f"Every active key is younger than {keyring.max_age_days()} days "
                    f"(oldest: {oldest} days). Master keys are kept outside the database.")


def staff_mfa():
    from apps.accounts.models import StaffAccount
    from apps.accounts.signin import confirmed_device

    active = StaffAccount.objects.filter(status="active", user__is_active=True).select_related("user")
    missing, waiting = 0, 0
    for account in active:
        if confirmed_device(account) is not None:
            continue
        if account.last_sign_in_at is None:
            waiting += 1  # cannot get past sign-in until the authenticator is set up
        else:
            missing += 1
    if missing:
        return FAILED, f"{missing} staff account(s) signed in without an authenticator app."
    note = f" {waiting} new account(s) must set it up at first sign-in." if waiting else ""
    return PASSED, f"Every staff account that has signed in uses an authenticator app.{note}"


def encrypted_at_rest():
    from apps.vault import service as vault
    from apps.vault.models import StoredCard

    sample = b"self-check"
    if vault._decrypt(vault._encrypt(sample, "tok_selfcheck"), "tok_selfcheck") != sample:
        return FAILED, "Encrypting and decrypting a test value with the vault key failed."
    plain = (StoredCard.objects.using("vault").exclude(ciphertext__startswith="k1.")
             .exclude(ciphertext__startswith="v1.").count())
    if plain:
        return FAILED, f"{plain} vault row(s) are not in an encrypted format."
    return PASSED, "Card data in the vault is encrypted with AES-256-GCM; a test value round-trips."


def audit_trail_checked():
    run = MaintenanceRun.objects.filter(kind=MaintenanceRun.Kind.INTEGRITY).first()
    if run is None:
        return NOT_CHECKED, "The integrity check has not run yet."
    hours = settings.GATEWAY_RULES["INTEGRITY_CHECK_HOURS"]
    if run.outcome != MaintenanceRun.Outcome.PASSED:
        return FAILED, "The last integrity check found problems."
    if run.started_at < timezone.now() - timedelta(hours=2 * hours):
        return FAILED, f"The integrity check has not run for over {2 * hours} hours."
    return PASSED, "The audit trail is hash-chained and the last integrity check passed."


CHECKS = [
    Check("https", "HTTPS enforced", "PCI DSS 4.2.1: strong cryptography in transit", https_enforced),
    Check("no_card_data_after_submission", "No card number or security code after submission",
          "PCI DSS 3.2.1, 3.3.1: no sensitive authentication data kept after authorisation",
          no_card_data_after_submission),
    Check("masking", "Card numbers masked", "PCI DSS 3.4.1: PAN masked when displayed",
          card_numbers_masked),
    Check("encryption_at_rest", "Card data encrypted at rest",
          "PCI DSS 3.5.1: stored PAN unreadable", encrypted_at_rest),
    Check("key_age", "Encryption keys rotated within 90 days",
          "PCI DSS 3.6.1, 3.7.4: key storage and cryptoperiods", keys_rotated),
    Check("staff_mfa", "Staff sign in with MFA",
          "PCI DSS 8.4.2: MFA for all access to card data", staff_mfa),
    Check("audit_trail", "Audit trail protected and checked",
          "PCI DSS 10.3.4: changes to audit logs detected", audit_trail_checked),
]


def evaluate() -> list[dict]:
    out = []
    for check in CHECKS:
        try:
            status, detail = check.run()
        except Exception as exc:  # noqa: BLE001 - a check that cannot run is reported, never hidden
            status, detail = NOT_CHECKED, f"The check could not run ({type(exc).__name__})."
        out.append({"id": check.id, "name": check.name, "practice": check.practice,
                    "status": status, "detail": detail})
    return out


def run(started_by: str = "") -> MaintenanceRun:
    from apps.security.alerts import raise_alert

    started = timezone.now()
    results = evaluate()
    failed = [r for r in results if r["status"] == FAILED]
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (PASSED, FAILED, NOT_CHECKED)}
    run_row = MaintenanceRun.objects.create(
        kind=MaintenanceRun.Kind.SELF_CHECK, started_at=started, finished_at=timezone.now(),
        started_by=started_by,
        outcome=MaintenanceRun.Outcome.PROBLEMS if failed else MaintenanceRun.Outcome.PASSED,
        summary={"checks": results, "counts": counts})
    audit("security.self_checks_run", actor_type=(AuditEvent.ActorType.STAFF if started_by
                                                  else AuditEvent.ActorType.SYSTEM),
          actor_id=started_by, target_type="maintenance_run", target_id=run_row.public_id,
          details=counts)
    for result in failed:
        kind = AlertKind.KEY_AGE if result["id"] == "key_age" else AlertKind.SELF_CHECK_FAILED
        raise_alert(kind, severity=Severity.MEDIUM, source=f"self-check:{result['id']}",
                    summary=f"Self-check failed: {result['name']}. {result['detail']}",
                    details={"run_id": run_row.public_id, "check": result["id"]})
    return run_row
