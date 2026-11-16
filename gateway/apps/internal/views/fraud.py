"""Fraud alerts and fraud reports (FR-FRD-08, FR-FRD-10; UC-50, UC-52; Could requirements).

Alerts: one per flagged payment (apps.risk.alerts). Each analyst or administrator has their own
read state, so the unread count is personal. The dashboard polls `alerts/unread` every 5 s.

Reports: counts of screened and flagged payments for a chosen period, by decision, risk level
(model score band), finding and top reason, with a day or week trend, and the same report as
CSV. Every generation and export is recorded in the audit log (UC-52 postcondition).
"""
import csv
import io
from collections import Counter
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncWeek
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import invalid, not_found
from apps.common.timefmt import rfc3339
from apps.internal.access import ANALYST_OR_ADMIN, StaffAPIView
from apps.internal.models import ReviewCase
from apps.internal.views.payments import _date, _int, local_zone
from apps.internal.views.reviews import FLAGGED, _decision_filter, case_row
from apps.merchants.models import Merchant
from apps.risk.models import FraudAlert, FraudAlertRead, ScreeningEvent, ScreeningOutcome

# --- alerts (UC-50) -------------------------------------------------------------------------


def _alerts():
    return FraudAlert.objects.select_related(
        "screening__payment__merchant", "screening__review__assigned_to__user",
        "screening__review__reviewed_by")


def alert_row(alert: FraudAlert, read: bool) -> dict:
    return {"id": alert.public_id, "created_at": rfc3339(alert.created_at), "read": read,
            "case": case_row(alert.screening)}


class AlertListView(StaffAPIView):
    """GET ?show=unread|all&page=&page_size= : newest first."""

    roles = ANALYST_OR_ADMIN

    def get(self, request):
        params = request.query_params
        show = params.get("show") or "all"
        if show not in ("unread", "all"):
            raise invalid("invalid_field", "'show' must be unread or all.", param="show")
        read_ids = set(FraudAlertRead.objects.filter(staff=self.staff)
                       .values_list("alert_id", flat=True))
        alerts = _alerts()
        unread_count = alerts.exclude(pk__in=read_ids).count()
        if show == "unread":
            alerts = alerts.exclude(pk__in=read_ids)
        page = _int(params.get("page"), "page", 1, 1, 100_000)
        size = _int(params.get("page_size"), "page_size", 25, 1, 100)
        count = alerts.count()
        rows = alerts.order_by("-created_at", "-id")[(page - 1) * size: page * size]
        return Response({"object": "list", "count": count, "page": page, "page_size": size,
                         "unread": unread_count,
                         "data": [alert_row(a, a.pk in read_ids) for a in rows]})


class AlertUnreadView(StaffAPIView):
    """GET : the badge in the sidebar. Cheap enough to poll every few seconds."""

    roles = ANALYST_OR_ADMIN

    def get(self, request):
        unread = FraudAlert.objects.exclude(reads__staff=self.staff)
        latest = unread.order_by("-created_at").values_list("created_at", flat=True).first()
        return Response({"unread": unread.count(), "latest_at": rfc3339(latest)})


class AlertReadView(StaffAPIView):
    """POST : mark one alert read (the analyst opened it)."""

    roles = ANALYST_OR_ADMIN

    def post(self, request, alert_id: str):
        alert = _alerts().filter(public_id=alert_id).first()
        if alert is None:
            raise not_found()
        FraudAlertRead.objects.get_or_create(alert=alert, staff=self.staff)
        return Response(alert_row(alert, True))


class AlertReadAllView(StaffAPIView):
    """POST : mark every alert read for the signed-in staff member."""

    roles = ANALYST_OR_ADMIN

    def post(self, request):
        unread = FraudAlert.objects.exclude(reads__staff=self.staff).values_list("pk", flat=True)
        reads = [FraudAlertRead(alert_id=pk, staff=self.staff) for pk in unread]
        FraudAlertRead.objects.bulk_create(reads, ignore_conflicts=True)
        return Response({"marked": len(reads), "unread": 0})


# --- reports (UC-52) ------------------------------------------------------------------------

DEFAULT_DAYS = 30
MAX_DAYS = 366
TOP_REASONS = 10
# Risk level of a flagged payment from its model score. Rule-only flags can score low.
RISK_LEVELS = (("high", "High (0.90 and above)", 0.9, None),
               ("elevated", "Elevated (0.70 to 0.89)", 0.7, 0.9),
               ("medium", "Medium (0.50 to 0.69)", 0.5, 0.7),
               ("low", "Low (below 0.50)", None, 0.5))
FINDINGS = ("confirmed_fraud", "false_positive", "inconclusive")


class Period:
    def __init__(self, params):
        zone = local_zone()
        today = timezone.now().astimezone(zone).date()
        self.to = _date(params["to"], "to") if params.get("to") else today
        self.start = (_date(params["from"], "from") if params.get("from")
                      else self.to - timedelta(days=DEFAULT_DAYS - 1))
        if self.start > self.to:
            raise invalid("invalid_period",
                          "Choose a valid date range: 'from' must be on or before 'to'.",
                          param="from")
        if (self.to - self.start).days + 1 > MAX_DAYS:
            raise invalid("invalid_period", f"Choose a period of at most {MAX_DAYS} days.",
                          param="from")
        self.interval = params.get("interval") or (
            "week" if (self.to - self.start).days >= 62 else "day")
        if self.interval not in ("day", "week"):
            raise invalid("invalid_field", "'interval' must be day or week.", param="interval")
        self.zone = zone
        self.lower = datetime.combine(self.start, time.min, zone)
        self.upper = datetime.combine(self.to + timedelta(days=1), time.min, zone)

    def buckets(self) -> list[date]:
        if self.interval == "day":
            first, step = self.start, timedelta(days=1)
        else:  # ISO weeks start on Monday, like Postgres date_trunc('week')
            first, step = self.start - timedelta(days=self.start.weekday()), timedelta(days=7)
        out, day = [], first
        while day <= self.to:
            out.append(day)
            day += step
        return out


def build_report(params) -> dict:
    period = Period(params)
    events = ScreeningEvent.objects.filter(occurred_at__gte=period.lower,
                                           occurred_at__lt=period.upper)
    in_period = events
    merchant = None
    if params.get("merchant"):
        merchant = Merchant.objects.filter(public_id=params["merchant"]).first()
        if merchant is None:
            raise invalid("invalid_field", "Unknown merchant.", param="merchant")
        events = events.filter(merchant=merchant)

    flagged_q = Q(outcome__in=FLAGGED)
    totals = events.aggregate(
        screened=Count("id"),
        allowed=Count("id", filter=Q(outcome=ScreeningOutcome.ALLOW)),
        verify=Count("id", filter=Q(outcome=ScreeningOutcome.VERIFY)),
        blocked=Count("id", filter=Q(outcome=ScreeningOutcome.BLOCK)),
        not_screened=Count("id", filter=Q(outcome=ScreeningOutcome.NOT_SCREENED)),
        flagged_amount=Sum("amount", filter=flagged_q),
        blocked_amount=Sum("amount", filter=Q(outcome=ScreeningOutcome.BLOCK)))
    totals["flagged"] = totals["verify"] + totals["blocked"]
    totals["flagged_amount"] = totals["flagged_amount"] or 0
    totals["blocked_amount"] = totals["blocked_amount"] or 0
    totals["flag_rate"] = (round(totals["flagged"] / totals["screened"], 4)
                           if totals["screened"] else 0.0)

    flagged = events.filter(flagged_q)
    decisions = flagged.aggregate(**{
        key: Count("id", filter=_decision_filter([key]))
        for key in ("blocked", "verify_failed", "verify_passed", "verify_pending")})

    risk = []
    for key, label, low, high in RISK_LEVELS:
        band = Q()
        if low is not None:
            band &= Q(score__gte=low)
        if high is not None:
            band &= Q(score__lt=high)
        risk.append({"level": key, "label": label,
                     "count": flagged.filter(band, score__isnull=False).count()})
    risk.append({"level": "none", "label": "No model score",
                 "count": flagged.filter(score__isnull=True).count()})

    closed = Q(review__status=ReviewCase.Status.CLOSED)
    findings = flagged.aggregate(**{
        f: Count("id", filter=closed & Q(review__finding=f)) for f in FINDINGS})
    findings["unreviewed"] = totals["flagged"] - sum(findings.values())

    reasons = Counter()
    for row in flagged.values_list("reasons", flat=True).iterator():
        reasons.update(row or [])
    top_reasons = [{"reason": r, "count": n} for r, n in reasons.most_common(TOP_REASONS)]

    trunc = (TruncDate if period.interval == "day" else TruncWeek)("occurred_at",
                                                                   tzinfo=period.zone)
    rows = (events.annotate(bucket=trunc).values("bucket").annotate(
        screened=Count("id"), flagged=Count("id", filter=flagged_q),
        blocked=Count("id", filter=Q(outcome=ScreeningOutcome.BLOCK)),
        confirmed_fraud=Count("id", filter=flagged_q & closed
                              & Q(review__finding="confirmed_fraud"))))
    by_bucket = {}
    for row in rows:
        bucket = row["bucket"]
        if isinstance(bucket, datetime):
            bucket = bucket.astimezone(period.zone).date()
        by_bucket[bucket] = row
    trend = []
    for start in period.buckets():
        row = by_bucket.get(start, {})
        trend.append({"start": start.isoformat(), "screened": row.get("screened", 0),
                      "flagged": row.get("flagged", 0), "blocked": row.get("blocked", 0),
                      "confirmed_fraud": row.get("confirmed_fraud", 0)})

    return {
        "object": "fraud_report",
        "generated_at": rfc3339(timezone.now()),
        "period": {"from": period.start.isoformat(), "to": period.to.isoformat(),
                   "interval": period.interval, "time_zone": str(period.zone)},
        "merchant": {"id": merchant.public_id, "name": merchant.name} if merchant else None,
        # Choices for the merchant filter: those with screened payments in the period.
        "merchants": [{"id": m.public_id, "name": m.name} for m in Merchant.objects.filter(
            pk__in=in_period.values("merchant")).order_by("name")],
        "totals": totals,
        "decisions": decisions,
        "risk_levels": risk,
        "findings": findings,
        "top_reasons": top_reasons,
        "trend": trend,
    }


def _audit_report(view, action: str, report: dict) -> None:
    merchant = report["merchant"]
    audit(action, actor_type=AuditEvent.ActorType.STAFF, actor_id=view.staff.public_id,
          merchant_id=merchant["id"] if merchant else "", target_type="report",
          target_id="fraud", request_id=view.request.request_id,
          details={**report["period"], "merchant": merchant["id"] if merchant else None,
                   "flagged": report["totals"]["flagged"]})


class FraudReportView(StaffAPIView):
    """GET ?from=YYYY-MM-DD&to=YYYY-MM-DD&merchant=mer_...&interval=day|week"""

    roles = ANALYST_OR_ADMIN

    def get(self, request):
        report = build_report(request.query_params)
        _audit_report(self, "fraud_report.generated", report)
        return Response(report)


def _cell(value):
    """Keep spreadsheet programs from running a cell as a formula (CSV injection)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def report_csv(report: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)

    def row(*cells):
        w.writerow([_cell(c) for c in cells])

    t, p = report["totals"], report["period"]
    row("SecurePay fraud report")
    row("From", p["from"])
    row("To", p["to"])
    row("Time zone", p["time_zone"])
    row("Merchant", report["merchant"]["name"] if report["merchant"] else "All merchants")
    row("Generated at", report["generated_at"])
    row()
    row("Summary", "Count")
    for key, label in (("screened", "Screened payments"), ("allowed", "Allowed"),
                       ("flagged", "Flagged (block or verify)"), ("blocked", "Blocked"),
                       ("verify", "Sent for verification"),
                       ("not_screened", "Not screened (screening unavailable)")):
        row(label, t[key])
    row("Flag rate", f"{t['flag_rate'] * 100:.2f}%")
    row("Flagged amount (SGD)", f"{t['flagged_amount'] / 100:.2f}")
    row("Blocked amount (SGD)", f"{t['blocked_amount'] / 100:.2f}")
    row()
    row("Decision", "Count")
    for key, label in (("blocked", "Blocked"), ("verify_failed", "Verify failed"),
                       ("verify_passed", "Verify passed"), ("verify_pending", "Verify pending")):
        row(label, report["decisions"][key])
    row()
    row("Risk level", "Count")
    for level in report["risk_levels"]:
        row(level["label"], level["count"])
    row()
    row("Finding", "Count")
    for key, label in (("confirmed_fraud", "Confirmed fraud"),
                       ("false_positive", "False positive"),
                       ("inconclusive", "Inconclusive"), ("unreviewed", "Not reviewed yet")):
        row(label, report["findings"][key])
    row()
    row("Top reason", "Count")
    for item in report["top_reasons"]:
        row(item["reason"], item["count"])
    row()
    row(f"{p['interval'].capitalize()} starting", "Screened", "Flagged", "Blocked",
        "Confirmed fraud")
    for item in report["trend"]:
        row(item["start"], item["screened"], item["flagged"], item["blocked"],
            item["confirmed_fraud"])
    return out.getvalue()


class FraudReportExportView(StaffAPIView):
    """GET with the same parameters: the report as a CSV download."""

    roles = ANALYST_OR_ADMIN

    def get(self, request):
        report = build_report(request.query_params)
        _audit_report(self, "fraud_report.exported", report)
        p = report["period"]
        response = HttpResponse(report_csv(report), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="fraud-report-{p["from"]}-to-{p["to"]}.csv"')
        response["Cache-Control"] = "no-store"
        return response
