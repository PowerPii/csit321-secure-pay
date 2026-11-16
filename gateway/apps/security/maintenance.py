"""Scheduling of the integrity check, self-checks and clean-up (run by the worker).

    seal_audit()   every pass: chain new audit entries
    run_due()      every pass: start each kind whose interval has passed since its last run

Intervals are in GATEWAY_RULES (INTEGRITY_CHECK_HOURS, SELF_CHECK_HOURS,
RETENTION_RUN_HOURS). A Postgres advisory lock keeps two workers from running the same kind
at once. A run that raises is recorded as an `error` run, so it waits for the next interval
instead of retrying every second.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.security.models import MaintenanceRun

logger = logging.getLogger(__name__)

LOCKS = {MaintenanceRun.Kind.INTEGRITY: 7_302_411, MaintenanceRun.Kind.SELF_CHECK: 7_302_412,
         MaintenanceRun.Kind.RETENTION: 7_302_413}


def interval(kind: str) -> timedelta:
    rules = settings.GATEWAY_RULES
    hours = {MaintenanceRun.Kind.INTEGRITY: rules["INTEGRITY_CHECK_HOURS"],
             MaintenanceRun.Kind.SELF_CHECK: rules["SELF_CHECK_HOURS"],
             MaintenanceRun.Kind.RETENTION: rules["RETENTION_RUN_HOURS"]}[kind]
    return timedelta(hours=hours)


def runner(kind: str):
    from apps.security import integrity, retention, selfchecks

    return {MaintenanceRun.Kind.INTEGRITY: integrity.run_check,
            MaintenanceRun.Kind.SELF_CHECK: selfchecks.run,
            MaintenanceRun.Kind.RETENTION: retention.run}[kind]


def is_due(kind: str, now=None) -> bool:
    last = MaintenanceRun.objects.filter(kind=kind).first()
    return last is None or last.started_at <= (now or timezone.now()) - interval(kind)


def start(kind: str, started_by: str = "") -> MaintenanceRun | None:
    """Run one kind now under its lock. None if another process is running it."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCKS[kind]])
        if not cursor.fetchone()[0]:
            return None
    started = timezone.now()
    try:
        return runner(kind)(started_by=started_by)
    except Exception as exc:
        logger.exception("Maintenance run %s failed", kind)
        return MaintenanceRun.objects.create(
            kind=kind, outcome=MaintenanceRun.Outcome.ERROR, started_at=started,
            finished_at=timezone.now(), started_by=started_by,
            summary={"error": type(exc).__name__})
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCKS[kind]])


def run_due() -> list[MaintenanceRun]:
    return [run for kind in MaintenanceRun.Kind.values if is_due(kind)
            if (run := start(kind)) is not None]


def seal_audit() -> int:
    from apps.security.integrity import seal_pending

    return seal_pending()
