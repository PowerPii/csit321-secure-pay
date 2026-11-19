"""Public status page data (www.securepaysg.me/status, served as GET /status.json).

    record_sample(now=None) -> StatusSample | None   worker job, at most every 5 minutes
    build_status(now=None) -> dict                   today's state, 90 days, incidents

Each sample says, for every part of the service, whether it answered. Downtime is worked
out from the samples alone, so the page needs no one to post incidents by hand:

  a part that failed      down from the first failing sample until the next passing one
  a gap in the samples    the worker (which records them) was not running; the other parts
                          are unknown for that time and do not count either way

Times on the page are shown in Singapore time (settings.DASHBOARD_TIME_ZONE).
"""
import logging
import math
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from django.conf import settings
from django.utils import timezone

from apps.common.timefmt import rfc3339

from .measures import build_measures
from .models import StatusSample

logger = logging.getLogger(__name__)

SAMPLE_EVERY = timedelta(minutes=5)
HISTORY_DAYS = 90
INCIDENT_DAYS = 14
MAX_INCIDENTS = 25
# Samples further apart than this mean the worker was not running (a deploy or a restart
# takes a minute or two, well under this).
GAP = timedelta(minutes=15)
# The web process cannot reach the card network or the shop itself, so for those two the
# page shows the newest sample, if it is at least this recent.
FRESH = timedelta(minutes=12)
PROBE_TIMEOUT = httpx.Timeout(3.0, connect=2.0)

# (id, name, what it covers): the order on the page.
COMPONENTS = [
    ("api", "Payments API and checkout",
     "The merchant API, the hosted payment page, customer accounts and the staff dashboard."),
    ("database", "Database and card vault",
     "Where payments are recorded and test card numbers are kept, encrypted."),
    ("worker", "Webhooks, emails and checks",
     ("The background worker: webhooks to merchants, receipt emails, reconciliation and "
      "scheduled checks.")),
    ("network", "Card network (simulator)",
     "The simulated card network that approves or declines test payments."),
    ("shop", "Demo shop",
     "Volt & Co., the demo store that pays through SecurePay."),
]
IDS = [cid for cid, _, _ in COMPONENTS]
NAMES = {cid: name for cid, name, _ in COMPONENTS}
INCIDENT_TITLES = {
    "api": "Payments API and checkout not answering",
    "database": "Database not answering",
    "worker": "Background worker stopped: webhooks, emails and reconciliation waited",
    "network": "Card network simulator not answering: payments could not be sent",
    "shop": "Demo shop not answering",
}


# --- Recording (worker) ---------------------------------------------------------------------

def _answers(url: str, verify) -> bool:
    try:
        response = httpx.get(url, timeout=PROBE_TIMEOUT, verify=verify, follow_redirects=False,
                             headers={"User-Agent": "SecurePay-Status/1.0"})
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def databases_ok() -> bool:
    from apps.common.views import readiness_problems

    problems = readiness_problems()
    return "database" not in problems and "vault" not in problems


def check_now() -> dict:
    """Ask every part once. The probe URLs come from settings only, never from a request."""
    results = {"database": databases_ok(), "worker": True}
    if settings.STATUS_GATEWAY_URL:
        results["api"] = _answers(f"{settings.STATUS_GATEWAY_URL}/healthz", True)
    results["network"] = _answers(f"{settings.SIMULATOR_URL.rstrip('/')}/healthz",
                                  settings.SIMULATOR_CA_BUNDLE or True)
    if settings.STATUS_SHOP_URL:
        results["shop"] = _answers(f"{settings.STATUS_SHOP_URL}/healthz", True)
    return {cid: results[cid] for cid in IDS if cid in results}


_next_check = 0.0


def record_sample(now: datetime | None = None) -> StatusSample | None:
    """Record a sample if the last one is five minutes old; drop samples past the history."""
    global _next_check
    if now is None:
        if time.monotonic() < _next_check:
            return None  # the worker loop runs every second; skip the query in between
        now = timezone.now()
    latest = StatusSample.objects.order_by("-taken_at").values_list("taken_at", flat=True).first()
    if latest is not None and now - latest < SAMPLE_EVERY - timedelta(seconds=5):
        _next_check = time.monotonic() + (SAMPLE_EVERY - (now - latest)).total_seconds()
        return None
    sample = StatusSample.objects.create(taken_at=now, results=check_now())
    StatusSample.objects.filter(taken_at__lt=now - timedelta(days=HISTORY_DAYS + 1)).delete()
    _next_check = time.monotonic() + SAMPLE_EVERY.total_seconds() - 5
    return sample


# --- Reading (GET /status.json) --------------------------------------------------------------

def downtimes(rows: list[tuple[datetime, dict]], now: datetime) -> dict[str, list]:
    """{component: [(start, end or None while ongoing)]} from samples in time order."""
    down: dict[str, list] = {cid: [] for cid in IDS}
    open_: dict[str, datetime] = {}
    prev = None
    for taken_at, results in rows:
        if prev is not None and taken_at - prev > GAP:
            down["worker"].append((prev + SAMPLE_EVERY, taken_at))
            for cid, start in open_.items():  # unknown from here: close at the last sample
                down[cid].append((start, prev + SAMPLE_EVERY))
            open_.clear()
        for cid in IDS:
            if cid not in results:
                continue
            if not results[cid] and cid not in open_:
                open_[cid] = taken_at
            elif results[cid] and cid in open_:
                down[cid].append((open_.pop(cid), taken_at))
        prev = taken_at
    if prev is not None:
        stale = now - prev > GAP
        if stale:
            down["worker"].append((prev + SAMPLE_EVERY, None))
        for cid, start in open_.items():
            down[cid].append((start, prev + SAMPLE_EVERY if stale else None))
    return down


def _overlap(intervals, start: datetime, end: datetime, now: datetime) -> float:
    total = 0.0
    for s, e in intervals:
        seconds = (min(e or now, end) - max(s, start)).total_seconds()
        total += max(0.0, seconds)
    return total


def _uptime(cid, down, start, end, now) -> float | None:
    """Percent of [start, end) the part was up, of the time it was measured."""
    length = (end - start).total_seconds()
    if length <= 0:
        return None
    measured = length if cid == "worker" else length - _overlap(down["worker"], start, end, now)
    if measured <= 0:
        return None
    up = 1 - _overlap(down[cid], start, end, now) / measured
    return math.floor(max(0.0, min(1.0, up)) * 10000) / 100  # never round 99.999 up to 100


def _current(cid, latest, now, problems) -> str:
    if cid == "api":
        return "operational"  # this reply is the gateway answering
    if cid == "database":
        return "outage" if {"database", "vault"} & set(problems) else "operational"
    if cid == "worker":
        return "outage" if "worker" in problems else "operational"
    if latest is None or now - latest[0] > FRESH or cid not in latest[1]:
        return "unknown"
    return "operational" if latest[1][cid] else "outage"


def overall(states: dict[str, str]) -> str:
    if "outage" in (states["api"], states["database"]):
        return "major_outage"
    if "outage" in states.values():
        return "partial_outage"
    return "operational"


def notice() -> str:
    return (settings.STATUS_NOTICE or "").strip()[:300]


def build_status(now: datetime | None = None) -> dict:
    from apps.common.views import readiness_problems

    now = now or timezone.now()
    tz = ZoneInfo(settings.DASHBOARD_TIME_ZONE)
    today = now.astimezone(tz).date()
    days = [today - timedelta(days=n) for n in range(HISTORY_DAYS - 1, -1, -1)]
    history_start = datetime.combine(days[0], datetime.min.time(), tz)

    first = StatusSample.objects.order_by("taken_at").values_list("taken_at", flat=True).first()
    # One sample before the window as well, so a gap or failure that spans its start counts.
    rows = list(StatusSample.objects.filter(taken_at__gte=history_start - GAP)
                .order_by("taken_at").values_list("taken_at", "results"))
    down = downtimes(rows, now)
    latest = rows[-1] if rows else None
    checked = {cid for _, results in rows for cid in results}
    problems = readiness_problems()

    components = []
    states = {}
    for cid, name, description in COMPONENTS:
        state = states[cid] = _current(cid, latest, now, problems)
        if cid not in checked or first is None:
            daily = [{"date": d.isoformat(), "uptime": None} for d in days]
            total = None
        else:
            daily = []
            for d in days:
                start = max(datetime.combine(d, datetime.min.time(), tz), first)
                end = min(datetime.combine(d + timedelta(days=1), datetime.min.time(), tz), now)
                daily.append({"date": d.isoformat(), "uptime": _uptime(cid, down, start, end, now)})
            total = _uptime(cid, down, max(history_start, first), now, now)
        components.append({"id": cid, "name": name, "description": description,
                           "status": state, "uptime": total, "days": daily})

    since = now - timedelta(days=INCIDENT_DAYS)
    incidents = []
    for cid in IDS:
        for start, end in down[cid]:
            if end is not None and end < since:
                continue
            incidents.append({
                "component": cid,
                "title": INCIDENT_TITLES[cid],
                "started_at": rfc3339(start),
                "ended_at": rfc3339(end),
                "minutes": max(1, math.ceil(((end or now) - start).total_seconds() / 60)),
            })
    incidents.sort(key=lambda i: i["started_at"], reverse=True)

    return {
        "status": overall(states),
        "updated_at": rfc3339(now),
        "notice": notice(),
        "time_zone": settings.DASHBOARD_TIME_ZONE,
        "check_every_minutes": int(SAMPLE_EVERY.total_seconds() // 60),
        "history_days": HISTORY_DAYS,
        "incident_days": INCIDENT_DAYS,
        "measured_since": rfc3339(first),
        "components": components,
        "incidents": incidents[:MAX_INCIDENTS],
        # What shoppers and merchants experienced, with each population and window
        # (apps.status.measures, docs/RELIABILITY-MEASURES.md).
        "measures": build_measures(now),
    }


def database_down_status(now: datetime | None = None) -> dict:
    """What the page shows when the database cannot be read at all."""
    now = now or timezone.now()
    states = {cid: "unknown" for cid in IDS}
    states.update(api="operational", database="outage")
    return {
        "status": "major_outage",
        "updated_at": rfc3339(now),
        "notice": notice(),
        "time_zone": settings.DASHBOARD_TIME_ZONE,
        "check_every_minutes": int(SAMPLE_EVERY.total_seconds() // 60),
        "history_days": HISTORY_DAYS,
        "incident_days": INCIDENT_DAYS,
        "measured_since": None,
        "components": [{"id": cid, "name": name, "description": description,
                        "status": states[cid], "uptime": None, "days": []}
                       for cid, name, description in COMPONENTS],
        "incidents": [],
        "measures": None,
    }
