"""Fraud insights: the charts page for analysts and administrators (extends FR-FRD-10, UC-52).

One read-only summary of the screening decision records for the last 24 hours, 7 days or
30 days, built for the charts on the dashboard's "Fraud insights" page:

    outcomes    allowed / sent for a code (step-up) / blocked / not screened, per hour or day
    decided_by  which stage made each call: lists and rules, the model, or nobody (allowed)
    top_rules   the reasons screening recorded most often, split by block and step-up
    top_factors the model features that most often pushed a flagged payment's score up (among
                its top three TreeSHAP contributions, apps.risk.explain), with an example
    scores      the model's score for recent payments (dots over time) and a histogram
    thresholds  the active policy's step-up and block lines, with how they were chosen

Like the fraud report, it reads only ScreeningEvent rows (the decision records) and is
recorded in the audit log each time it is generated. No card, email or IP values leave it.
"""
from collections import Counter
from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import invalid
from apps.common.timefmt import rfc3339
from apps.internal.access import ANALYST_OR_ADMIN, StaffAPIView
from apps.internal.query_params import local_zone
from apps.merchants.models import Merchant
from apps.risk.models import ScreeningEvent, ScreeningOutcome
from apps.risk.pipeline import DEFAULT_POLICY
from apps.risk.scoring import active_model

RANGES = {"24h": ("hour", 24), "7d": ("day", 7), "30d": ("day", 30)}
TOP_RULES = 8
TOP_FACTORS_PER_PAYMENT = 3
MAX_POINTS = 500
BIN_WIDTH = 0.02
BINS = 50  # 0.00-0.02, ..., 0.98-1.00
MODEL_REASONS = ("model_score_high", "model_score_medium")
OUTCOMES = (("allowed", ScreeningOutcome.ALLOW), ("verify", ScreeningOutcome.VERIFY),
            ("blocked", ScreeningOutcome.BLOCK), ("not_screened", ScreeningOutcome.NOT_SCREENED))
OUTCOME_KEY = {value: key for key, value in OUTCOMES}

# How each policy's lines were chosen, from the model's evaluation write-up
# (research/evaluation/hgb-fs02-2026-11-13.md). Policies not listed get no note.
POLICY_NOTES = {
    "policy-hgb-fs02-2026-11-13": (
        "Set so that 2% of genuine payments are asked for a code (false-positive rate)",
        "Set so that 0.1% of genuine payments are blocked (false-positive rate)"),
    "policy-0.1": ("Fixed starting value (no trained model)",
                   "Fixed starting value (no trained model)"),
}


class Window:
    def __init__(self, key: str):
        if key not in RANGES:
            raise invalid("invalid_field", "'range' must be 24h, 7d or 30d.", param="range")
        self.key = key
        self.interval, count = RANGES[key]
        self.zone = local_zone()
        now = timezone.now().astimezone(self.zone)
        if self.interval == "hour":
            last = now.replace(minute=0, second=0, microsecond=0)
            self.starts = [last - timedelta(hours=count - 1 - i) for i in range(count)]
            self.lower = self.starts[0]
            self.upper = last + timedelta(hours=1)
        else:
            today = now.date()
            days = [today - timedelta(days=count - 1 - i) for i in range(count)]
            self.starts = days
            self.lower = datetime.combine(days[0], time.min, self.zone)
            self.upper = datetime.combine(today + timedelta(days=1), time.min, self.zone)

    def label(self, start) -> str:
        return start.isoformat()

    def bucket_of(self, value):
        if self.interval == "hour":
            return value.astimezone(self.zone).replace(minute=0, second=0, microsecond=0)
        return value.astimezone(self.zone).date() if isinstance(value, datetime) else value


def _outcomes(events, window: Window) -> list[dict]:
    trunc = (TruncHour if window.interval == "hour" else TruncDate)("occurred_at",
                                                                    tzinfo=window.zone)
    rows = events.annotate(bucket=trunc).values("bucket").annotate(**{
        key: Count("id", filter=Q(outcome=value)) for key, value in OUTCOMES})
    by_bucket = {window.bucket_of(row["bucket"]): row for row in rows}
    out = []
    for start in window.starts:
        row = by_bucket.get(start, {})
        out.append({"start": window.label(start),
                    **{key: row.get(key, 0) for key, _ in OUTCOMES}})
    return out


def _thresholds() -> dict:
    model = active_model()
    policy = model.policy or DEFAULT_POLICY
    verify_note, block_note = POLICY_NOTES.get(policy.version, ("", ""))
    return {"model_version": model.version, "policy_version": policy.version,
            "stub_model": model.version == "stub-0",
            "verify": policy.verify_threshold, "block": policy.block_threshold,
            "verify_note": verify_note, "block_note": block_note}


def build_insights(params) -> dict:
    window = Window(params.get("range") or "7d")
    in_window = ScreeningEvent.objects.filter(occurred_at__gte=window.lower,
                                              occurred_at__lt=window.upper)
    events = in_window
    merchant = None
    if params.get("merchant"):
        merchant = Merchant.objects.filter(public_id=params["merchant"]).first()
        if merchant is None:
            raise invalid("invalid_field", "Unknown merchant.", param="merchant")
        events = events.filter(merchant=merchant)

    totals = events.aggregate(screened=Count("id"), **{
        key: Count("id", filter=Q(outcome=value)) for key, value in OUTCOMES})

    # One pass over the decision records for the reasons, the stage and the histogram.
    decided_by = Counter()
    by_reason: dict[str, Counter] = {}
    bins = [Counter() for _ in range(BINS)]
    scored = 0
    by_factor: dict[str, Counter] = {}
    factor_example: dict[str, str] = {}
    for outcome, score, reasons, why in events.values_list(
            "outcome", "score", "reasons", "explanation").iterator():
        key = OUTCOME_KEY.get(outcome, "not_screened")
        reasons = reasons or []
        if key in ("verify", "blocked"):
            raising = [f for f in (why or {}).get("factors", [])
                       if f.get("source") == "model" and f.get("direction") == "raises"]
            for factor in raising[:TOP_FACTORS_PER_PAYMENT]:
                by_factor.setdefault(factor["feature"], Counter())[key] += 1
                factor_example.setdefault(factor["feature"], factor.get("text", ""))
        if key == "not_screened":
            decided_by["unavailable"] += 1
        elif key == "allowed":
            decided_by["allowed"] += 1
        elif any(r in MODEL_REASONS for r in reasons):
            decided_by["model"] += 1
        else:
            decided_by["rules"] += 1
        if key in ("verify", "blocked"):
            for reason in set(reasons):
                by_reason.setdefault(reason, Counter())[key] += 1
        if score is not None and key != "not_screened":
            scored += 1
            bins[min(BINS - 1, max(0, int(score / BIN_WIDTH)))][key] += 1

    top = sorted(by_reason.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:TOP_RULES]
    recent = list(events.filter(score__isnull=False).exclude(
        outcome=ScreeningOutcome.NOT_SCREENED).order_by("-occurred_at", "-id").values_list(
        "public_id", "occurred_at", "score", "outcome", "model_version")[:MAX_POINTS])
    recent.reverse()
    flagged = (ScreeningOutcome.VERIFY, ScreeningOutcome.BLOCK)

    return {
        "object": "fraud_insights",
        "generated_at": rfc3339(timezone.now()),
        "range": window.key,
        "interval": window.interval,
        "from": rfc3339(window.lower),
        "to": rfc3339(window.upper),
        "time_zone": str(window.zone),
        "merchant": {"id": merchant.public_id, "name": merchant.name} if merchant else None,
        "merchants": [{"id": m.public_id, "name": m.name} for m in Merchant.objects.filter(
            pk__in=in_window.values("merchant")).order_by("name")],
        "totals": totals,
        "outcomes": _outcomes(events, window),
        "decided_by": {k: decided_by.get(k, 0)
                       for k in ("rules", "model", "allowed", "unavailable")},
        "top_rules": [{"reason": r, "blocked": c.get("blocked", 0), "verify": c.get("verify", 0),
                       "total": sum(c.values())} for r, c in top],
        "top_factors": [{"feature": f, "example": factor_example.get(f, ""),
                         "blocked": c.get("blocked", 0), "verify": c.get("verify", 0),
                         "total": sum(c.values())}
                        for f, c in sorted(by_factor.items(),
                                           key=lambda kv: (-sum(kv[1].values()), kv[0]))
                        [:TOP_RULES]],
        "scores": {
            "scored": scored,
            "points": [{"at": rfc3339(at), "score": round(score, 4),
                        "outcome": OUTCOME_KEY.get(outcome, outcome),
                        "case_id": public_id if outcome in flagged else None}
                       for public_id, at, score, outcome, _ in recent],
            "points_limit": MAX_POINTS,
            "model_versions": sorted({v for *_, v in recent if v}),
            "histogram": [{"low": round(i * BIN_WIDTH, 2), "high": round((i + 1) * BIN_WIDTH, 2),
                           "allowed": b.get("allowed", 0), "verify": b.get("verify", 0),
                           "blocked": b.get("blocked", 0)} for i, b in enumerate(bins)],
        },
        "thresholds": _thresholds(),
    }


class FraudInsightsView(StaffAPIView):
    """GET ?range=24h|7d|30d&merchant=mer_..."""

    roles = ANALYST_OR_ADMIN

    def get(self, request):
        data = build_insights(request.query_params)
        merchant = data["merchant"]
        audit("fraud_insights.generated", actor_type=AuditEvent.ActorType.STAFF,
              actor_id=self.staff.public_id, merchant_id=merchant["id"] if merchant else "",
              target_type="report", target_id="fraud_insights", request_id=request.request_id,
              details={"range": data["range"], "merchant": merchant["id"] if merchant else None,
                       "screened": data["totals"]["screened"]})
        return Response(data)
