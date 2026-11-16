"""Dashboard overview: today at a glance and the last 14 days (demo-day polish).

Read-only counts over the payments the caller may see (visible_payments): a merchant
operator gets their own merchant's numbers, analysts and administrators every merchant's.
Days are Singapore calendar days (DASHBOARD_TIME_ZONE). Amounts are SGD cents.
"""
from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.response import Response

from apps.internal.access import StaffAPIView, visible_payments
from apps.internal.serializers import payment_row
from apps.internal.views.payments import local_zone
from apps.payments.states import PaymentStatus as S

DAYS = 14
# A payment the bank approved, whatever happened after (captured, refunded or voided).
APPROVED = [S.AUTHORISED, S.CAPTURED]
SUBMITTED = [S.AUTHORISED, S.CAPTURED, S.DECLINED, S.BLOCKED, S.CANCELLED]


def build_overview(staff) -> dict:
    zone = local_zone()
    now = timezone.now().astimezone(zone)
    today = datetime.combine(now.date(), time.min, zone)
    start = today - timedelta(days=DAYS - 1)
    payments = visible_payments(staff)
    approved_now = Q(status__in=APPROVED) | Q(status=S.CANCELLED, authorised_at__isnull=False)

    todays = payments.filter(created_at__gte=today)
    t = todays.aggregate(
        payments=Count("id", filter=Q(submitted_at__isnull=False)),
        approved=Count("id", filter=approved_now),
        declined=Count("id", filter=Q(status=S.DECLINED)),
        blocked=Count("id", filter=Q(status=S.BLOCKED)),
        verified=Count("id", filter=Q(screening_decision="verify")),
        volume=Sum("amount", filter=Q(status__in=APPROVED)),
    )
    decided = t["approved"] + t["declined"] + t["blocked"]

    rows = (payments.filter(created_at__gte=start, submitted_at__isnull=False)
            .annotate(day=TruncDate("created_at", tzinfo=zone)).values("day")
            .annotate(approved=Count("id", filter=approved_now),
                      declined=Count("id", filter=Q(status=S.DECLINED)),
                      blocked=Count("id", filter=Q(status=S.BLOCKED)),
                      volume=Sum("amount", filter=Q(status__in=APPROVED))))
    by_day = {r["day"]: r for r in rows}
    daily = []
    for i in range(DAYS):
        day = (start + timedelta(days=i)).date()
        r = by_day.get(day, {})
        daily.append({"date": day.isoformat(), "approved": r.get("approved", 0),
                      "declined": r.get("declined", 0), "blocked": r.get("blocked", 0),
                      "volume": r.get("volume") or 0})

    week = payments.filter(created_at__gte=today - timedelta(days=6)).exclude(
        screening_decision="")
    mix = dict(week.values_list("screening_decision").annotate(n=Count("id")))
    recent = payments.filter(submitted_at__isnull=False).order_by("-created_at", "-id")[:6]

    return {
        "object": "overview",
        "time_zone": str(zone),
        "today": {
            "payments": t["payments"],
            "approved": t["approved"],
            "declined": t["declined"],
            "blocked": t["blocked"],
            "verification_asked": t["verified"],
            "approved_volume": t["volume"] or 0,
            "approval_rate": round(t["approved"] / decided, 4) if decided else None,
        },
        "daily": daily,
        "screening_7d": {k: mix.get(k, 0) for k in ("allow", "verify", "block",
                                                     "not_screened")},
        "recent": [payment_row(p) for p in recent],
    }


class OverviewView(StaffAPIView):
    """GET /internal/overview"""

    def get(self, request):
        return Response(build_overview(self.staff))
