"""Integrity hashes for payment records and the audit hash chain (FR-ADM-09, NFR-INT-02).

    payment_digest(payment) -> str        stamped on every Payment.save()
    seal_pending()          -> int        worker: chain new audit entries (AuditSeal)
    check_payments()        -> dict       recompute every payment's hash
    check_audit_chain()     -> dict       walk the chain: edited, deleted, inserted, reordered
    run_check(started_by)   -> MaintenanceRun   both checks; alert administrators on problems

Both use HMAC-SHA256 with a key derived from the field master key (a Compose secret), so
someone who can change rows in the database but cannot read the secrets cannot make a
changed row match again. The payment hash covers the fields that decide money and status;
the customer's email and account link are left out so the 12-month clean-up (NFR-PRI-01)
can remove them without breaking the hash. An administrator with the secrets and database
access could rebuild everything; that is outside the threat model (URS Section 3.2).
"""
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditSeal
from apps.audit.models import record as audit
from apps.payments.models import Payment
from apps.security.models import AlertKind, MaintenanceRun, Severity

GENESIS = "0" * 64
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
BATCH = 2000
FINDINGS_KEPT = 100  # findings stored on the run; the counts are always complete

PAYMENT_FIELDS = (
    "public_id", "reference", "merchant_id", "order_reference", "amount", "currency",
    "status", "captured_amount", "card_token", "card_brand", "card_last4",
    "screening_decision", "outcome_reason", "created_at", "submitted_at", "authorised_at",
    "captured_at", "cancelled_at",
)


def _key(label: str) -> bytes:
    from apps.security.keyring import master_key

    return hmac.new(master_key("field"), f"securepay-integrity:{label}".encode(),
                    hashlib.sha256).digest()


def _micros(value: datetime | None):
    return None if value is None else (value - EPOCH) // timedelta(microseconds=1)


def _canonical(values: list) -> bytes:
    return json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode()


def payment_digest(payment: Payment) -> str:
    values = []
    for name in PAYMENT_FIELDS:
        value = getattr(payment, name)
        values.append(_micros(value) if isinstance(value, datetime) else value)
    return hmac.new(_key("payment"), _canonical(values), hashlib.sha256).hexdigest()


def audit_digest(event: AuditEvent, previous_hash: str) -> str:
    values = [previous_hash, event.id, _micros(event.occurred_at), event.actor_type,
              event.actor_id, event.merchant_id, event.action, event.target_type,
              event.target_id, event.request_id, event.correlation_id, event.details]
    return hmac.new(_key("audit"), _canonical(values), hashlib.sha256).hexdigest()


# --- audit chain --------------------------------------------------------------------------

SEAL_LOCK = 7_302_401  # pg advisory lock: one sealer at a time


def seal_pending(limit: int = 5000) -> int:
    """Chain audit entries older than AUDIT_SEAL_GRACE_SECONDS, in ID order.

    The grace period lets a slow transaction commit an entry with a lower ID before a higher
    one is sealed. An entry that appears below the chain head later is reported as inserted.
    """
    from django.db import connection

    cutoff = timezone.now() - timedelta(seconds=settings.GATEWAY_RULES["AUDIT_SEAL_GRACE_SECONDS"])
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [SEAL_LOCK])
        head = AuditSeal.objects.order_by("-position").first()
        position = head.position if head else 0
        previous = head.entry_hash if head else GENESIS
        events = list(AuditEvent.objects.filter(id__gt=head.event_id if head else 0,
                                                occurred_at__lt=cutoff).order_by("id")[:limit])
        seals = []
        for event in events:
            position += 1
            digest = audit_digest(event, previous)
            seals.append(AuditSeal(position=position, event_id=event.id,
                                   previous_hash=previous, entry_hash=digest))
            previous = digest
        AuditSeal.objects.bulk_create(seals)
    return len(seals)


def check_audit_chain() -> dict:
    findings: list[dict] = []
    counts = {"edited": 0, "deleted": 0, "inserted": 0, "reordered": 0, "chain_broken": 0}

    def flag(problem: str, **where):
        counts[problem] += 1
        if len(findings) < FINDINGS_KEPT:
            findings.append({"problem": problem, **where})

    previous_hash, expected, last_event_id, checked = GENESIS, 1, 0, 0
    after = 0
    while True:
        seals = list(AuditSeal.objects.filter(position__gt=after).order_by("position")[:BATCH])
        if not seals:
            break
        events = AuditEvent.objects.in_bulk([s.event_id for s in seals])
        for seal in seals:
            if seal.position != expected or seal.previous_hash != previous_hash:
                flag("chain_broken", position=seal.position)
            if seal.event_id <= last_event_id:
                flag("reordered", position=seal.position, event_id=seal.event_id)
            event = events.get(seal.event_id)
            if event is None:
                flag("deleted", position=seal.position, event_id=seal.event_id)
            elif audit_digest(event, seal.previous_hash) != seal.entry_hash:
                flag("edited", position=seal.position, event_id=seal.event_id)
            previous_hash, expected = seal.entry_hash, seal.position + 1
            last_event_id = max(last_event_id, seal.event_id)
            checked += 1
        after = seals[-1].position
    # An entry below the chain head without a seal was added afterwards (or moved there).
    inserted = (AuditEvent.objects.filter(id__lt=last_event_id)
                .filter(~Exists(AuditSeal.objects.filter(event_id=OuterRef("id"))))
                .values_list("id", flat=True))
    for event_id in inserted:
        flag("inserted", event_id=event_id)
    unsealed = AuditEvent.objects.filter(id__gt=last_event_id).count()
    return {"checked": checked, "unsealed_recent": unsealed, "problems": sum(counts.values()),
            "counts": counts, "findings": findings}


# --- payments -----------------------------------------------------------------------------


def check_payments() -> dict:
    """Recompute each payment's hash. A payment with no hash yet (made before this check
    existed) is stamped now and counted as `baselined`, not as a mismatch."""
    checked, baselined, mismatched, findings = 0, 0, 0, []
    rows = Payment.objects.only("id", "integrity_hash", *[
        f for f in PAYMENT_FIELDS if f != "merchant_id"] + ["merchant"]).order_by("id")
    last = 0
    while True:
        batch = list(rows.filter(id__gt=last)[:BATCH])
        if not batch:
            break
        for payment in batch:
            checked += 1
            digest = payment_digest(payment)
            if not payment.integrity_hash:
                Payment.objects.filter(pk=payment.pk, integrity_hash="").update(
                    integrity_hash=digest)
                baselined += 1
            elif not hmac.compare_digest(digest, payment.integrity_hash):
                mismatched += 1
                if len(findings) < FINDINGS_KEPT:
                    findings.append({"payment_id": payment.public_id,
                                     "reference": payment.reference})
        last = batch[-1].id
    return {"checked": checked, "baselined": baselined, "problems": mismatched,
            "findings": findings}


def run_check(started_by: str = "") -> MaintenanceRun:
    from apps.security.alerts import raise_alert

    started = timezone.now()
    sealed = seal_pending()
    payments = check_payments()
    chain = check_audit_chain()
    problems = payments["problems"] + chain["problems"]
    run = MaintenanceRun.objects.create(
        kind=MaintenanceRun.Kind.INTEGRITY, started_at=started, finished_at=timezone.now(),
        started_by=started_by,
        outcome=MaintenanceRun.Outcome.PROBLEMS if problems else MaintenanceRun.Outcome.PASSED,
        summary={"sealed_now": sealed, "payments": payments, "audit": chain})
    audit("security.integrity_checked", actor_type=(AuditEvent.ActorType.STAFF if started_by
                                                    else AuditEvent.ActorType.SYSTEM),
          actor_id=started_by, target_type="maintenance_run", target_id=run.public_id,
          details={"payments_checked": payments["checked"],
                   "payment_mismatches": payments["problems"],
                   "audit_checked": chain["checked"], "audit_problems": chain["problems"]})
    if problems:
        raise_alert(
            AlertKind.INTEGRITY_MISMATCH, severity=Severity.HIGH, source="integrity-check",
            summary=(f"The integrity check found {payments['problems']} changed payment "
                     f"record(s) and {chain['problems']} audit trail problem(s)."),
            details={"run_id": run.public_id, "payment_mismatches": payments["problems"],
                     "audit_problems": chain["counts"]})
    return run
