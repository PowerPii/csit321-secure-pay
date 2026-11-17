"""D6 fraud review queue and D6b case detail (FR-FRD-05, FR-FRD-07; analysts, administrators).

A case is a screening decision of Block or Verify; its ID is the decision record's `scr_...`
ID. Analysts assign cases, record a finding (confirmed fraud, false positive, inconclusive)
with notes, and reopen them. A finding never changes the payment (apps.internal rule).
Blocklisting from a case (FR-FRD-09) and searches by card, email or IP (FR-FRD-06) are in
apps.internal.views.blocklist.
"""
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.common.views import body_or_empty
from apps.internal.access import ANALYST_OR_ADMIN, StaffAPIView
from apps.internal.models import ReviewCase
from apps.internal.query_params import bounded_int, local_zone, parse_date
from apps.internal.serializers import mask_email, screening_to_dict, verification_state
from apps.risk.models import ScreeningEvent, ScreeningOutcome

FLAGGED = (ScreeningOutcome.BLOCK, ScreeningOutcome.VERIFY)
DECISION_KEYS = ("blocked", "verify_failed", "verify_passed", "verify_pending")
SORTS = {"score_desc": [F("score").desc(nulls_last=True), "-occurred_at"],
         "score_asc": [F("score").asc(nulls_last=True), "-occurred_at"],
         "newest": ["-occurred_at"]}
LINK_WINDOW = timedelta(hours=24)
RELATED_WINDOW = timedelta(days=30)
MAX_NOTES = 1000


def flagged_cases():
    return (ScreeningEvent.objects.filter(outcome__in=FLAGGED)
            .select_related("payment__merchant", "review__assigned_to__user"))


def decision_key(event: ScreeningEvent) -> str:
    if event.outcome == ScreeningOutcome.BLOCK:
        return "blocked"
    return f"verify_{verification_state(event.payment) or 'pending'}"


def _decision_filter(keys: list[str]) -> Q:
    query = Q(pk__in=[])
    for key in keys:
        if key == "blocked":
            query |= Q(outcome=ScreeningOutcome.BLOCK)
        elif key == "verify_failed":
            query |= Q(outcome=ScreeningOutcome.VERIFY, payment__status="blocked")
        elif key == "verify_pending":
            query |= Q(outcome=ScreeningOutcome.VERIFY,
                       payment__status="verification_required")
        else:
            query |= (Q(outcome=ScreeningOutcome.VERIFY)
                      & ~Q(payment__status__in=["blocked", "verification_required"]))
    return query


OPEN_Q = Q(review__isnull=True) | Q(review__status=ReviewCase.Status.OPEN)


def review_to_dict(case: ReviewCase | None) -> dict:
    if case is None:
        return {"status": "open", "assigned_to": None, "finding": None, "notes": "",
                "reviewed_by": None, "reviewed_at": None}
    return {
        "status": case.status,
        "assigned_to": ({"id": case.assigned_to.public_id, "name": case.assigned_to.display_name}
                        if case.assigned_to else None),
        "finding": case.finding or None,
        "notes": case.notes,
        "reviewed_by": case.reviewed_by.display_name if case.reviewed_by else None,
        "reviewed_at": rfc3339(case.reviewed_at),
    }


def _review(event: ScreeningEvent) -> ReviewCase | None:
    try:
        return event.review
    except ReviewCase.DoesNotExist:
        return None


def case_row(event: ScreeningEvent) -> dict:
    payment = event.payment
    return {
        "id": event.public_id,
        "payment": {"id": payment.public_id, "reference": payment.reference,
                    "amount": payment.amount, "currency": payment.currency,
                    "status": payment.status},
        "merchant": {"id": payment.merchant.public_id, "name": payment.merchant.name},
        "score": event.score,
        "outcome": event.outcome,
        "decision": decision_key(event),
        "reasons": list(event.reasons or []),
        "occurred_at": rfc3339(event.occurred_at),
        "review": review_to_dict(_review(event)),
    }


class ReviewListView(StaffAPIView):
    """GET ?tab=open|mine|closed&decision=blocked,verify_failed&min_score=&merchant=&from=
    &to=&sort=score_desc|score_asc|newest&page=&page_size="""

    roles = ANALYST_OR_ADMIN

    def get(self, request):
        params = request.query_params
        cases = flagged_cases()
        mine = Q(review__assigned_to=self.staff, review__status=ReviewCase.Status.OPEN)
        counts = cases.aggregate(
            open=Count("id", filter=OPEN_Q), mine=Count("id", filter=mine),
            closed=Count("id", filter=Q(review__status=ReviewCase.Status.CLOSED)))

        tab = params.get("tab") or "open"
        if tab not in ("open", "mine", "closed", "all"):
            raise invalid("invalid_field", f"Unknown tab '{tab}'.", param="tab")
        if tab == "open":
            cases = cases.filter(OPEN_Q)
        elif tab == "mine":
            cases = cases.filter(mine)
        elif tab == "closed":
            cases = cases.filter(review__status=ReviewCase.Status.CLOSED)

        keys = [k for k in (params.get("decision") or "").split(",") if k]
        for key in keys:
            if key not in DECISION_KEYS:
                raise invalid("invalid_field", f"Unknown decision '{key}'.", param="decision")
        if keys:
            cases = cases.filter(_decision_filter(keys))
        if params.get("min_score"):
            try:
                cases = cases.filter(score__gte=float(params["min_score"]))
            except ValueError:
                raise invalid("invalid_field", "'min_score' must be a number from 0 to 1.",
                              param="min_score") from None
        if params.get("merchant"):
            cases = cases.filter(merchant__public_id=params["merchant"])
        zone = local_zone()
        if params.get("from"):
            cases = cases.filter(occurred_at__gte=datetime.combine(
                parse_date(params["from"], "from"), time.min, zone))
        if params.get("to"):
            cases = cases.filter(occurred_at__lt=datetime.combine(
                parse_date(params["to"], "to") + timedelta(days=1), time.min, zone))

        sort = params.get("sort") or "score_desc"
        if sort not in SORTS:
            raise invalid("invalid_field", f"Unknown sort '{sort}'.", param="sort")
        page = bounded_int(params.get("page"), "page", 1, 1, 100_000)
        size = bounded_int(params.get("page_size"), "page_size", 25, 1, 100)
        count = cases.count()
        rows = cases.order_by(*SORTS[sort])[(page - 1) * size: page * size]
        return Response({"object": "list", "count": count, "page": page, "page_size": size,
                         "counts": counts, "data": [case_row(e) for e in rows]})


def linked_activity(event: ScreeningEvent) -> dict:
    """UC-48: other attempts sharing the card, email or IP within 24 h either side."""
    window = Q(occurred_at__gte=event.occurred_at - LINK_WINDOW,
               occurred_at__lte=event.occurred_at + LINK_WINDOW)
    others = ScreeningEvent.objects.exclude(pk=event.pk).filter(window)

    def count(field):
        value = getattr(event, field)
        if not value:
            return None
        return others.filter(**{field: value}).aggregate(
            attempts=Count("id"), merchants=Count("merchant", distinct=True),
            blocked=Count("id", filter=Q(outcome__in=[ScreeningOutcome.BLOCK,
                                                      ScreeningOutcome.NOT_SCREENED])))

    return {"window_hours": 24, "card": count("card_fingerprint"),
            "email": count("email_hash"), "ip": count("ip_hash")}


def related_attempts(event: ScreeningEvent, limit: int = 25) -> list[dict]:
    match = Q(pk__in=[])
    for field in ("card_fingerprint", "email_hash", "ip_hash"):
        if getattr(event, field):
            match |= Q(**{field: getattr(event, field)})
    rows = (ScreeningEvent.objects.exclude(pk=event.pk).filter(match)
            .filter(occurred_at__gte=event.occurred_at - RELATED_WINDOW,
                    occurred_at__lte=event.occurred_at + RELATED_WINDOW)
            .select_related("payment__merchant").order_by("-occurred_at")[:limit])
    out = []
    for other in rows:
        shared = [name for name, field in (("card", "card_fingerprint"),
                                           ("email", "email_hash"), ("ip", "ip_hash"))
                  if getattr(event, field) and getattr(other, field) == getattr(event, field)]
        out.append({
            "case_id": other.public_id if other.outcome in FLAGGED else None,
            "payment": {"id": other.payment.public_id, "reference": other.payment.reference,
                        "status": other.payment.status},
            "merchant": other.payment.merchant.name,
            "amount": other.amount,
            "outcome": other.outcome,
            "score": other.score,
            "shared": shared,
            "occurred_at": rfc3339(other.occurred_at),
        })
    return out


def case_detail(event: ScreeningEvent) -> dict:
    payment = event.payment
    data = case_row(event)
    data["payment"].update({
        "order_reference": payment.order_reference,
        "card": ({"brand": payment.card_brand or "unknown", "last4": payment.card_last4}
                 if payment.card_last4 else None),
        "customer": mask_email(payment.customer_email),
        "outcome_reason": payment.outcome_reason or None,
        "created_at": rfc3339(payment.created_at),
    })
    data.update({
        "screening": screening_to_dict(event),
        "linked_activity": linked_activity(event),
        "related": related_attempts(event),
    })
    return data


def get_case(case_id: str) -> ScreeningEvent:
    event = flagged_cases().filter(public_id=case_id).first()
    if event is None:
        raise not_found()
    return event


class ReviewDetailView(StaffAPIView):
    """GET the case. POST {action: assign | unassign | save | reopen, finding, notes}."""

    roles = ANALYST_OR_ADMIN

    def get(self, request, case_id: str):
        return Response(case_detail(get_case(case_id)))

    def post(self, request, case_id: str):
        body = body_or_empty(request)
        action = body.get("action")
        if action not in ("assign", "unassign", "save", "reopen"):
            raise invalid("invalid_field", "'action' must be assign, unassign, save or reopen.",
                          param="action")
        event = get_case(case_id)
        details = {"case_id": event.public_id}
        with transaction.atomic():
            case, _ = ReviewCase.objects.select_for_update().get_or_create(screening=event)
            if action == "assign":
                case.assigned_to = self.staff
            elif action == "unassign":
                case.assigned_to = None
            elif action == "reopen":
                if case.status != ReviewCase.Status.CLOSED:
                    raise ApiError(409, "case_not_closed", "This case is already open.")
                case.status = ReviewCase.Status.OPEN
            else:
                finding = body.get("finding")
                if finding not in ReviewCase.Finding.values:
                    raise invalid("invalid_field", "Choose a finding: confirmed_fraud, "
                                  "false_positive or inconclusive.", param="finding")
                notes = body.get("notes") or ""
                if not isinstance(notes, str) or len(notes) > MAX_NOTES:
                    raise invalid("invalid_field", f"Notes must be at most {MAX_NOTES} "
                                  "characters.", param="notes")
                case.finding, case.notes = finding, notes.strip()
                case.status = ReviewCase.Status.CLOSED
                case.reviewed_by, case.reviewed_at = self.staff, timezone.now()
                if case.assigned_to is None:
                    case.assigned_to = self.staff
                details.update(finding=finding, false_positive=finding == "false_positive")
            case.save()
            audit({"assign": "review.assigned", "unassign": "review.unassigned",
                   "save": "review.finding_recorded", "reopen": "review.reopened"}[action],
                  actor_type=AuditEvent.ActorType.STAFF, actor_id=self.staff.public_id,
                  merchant_id=event.payment.merchant.public_id, target_type="payment",
                  target_id=event.payment.public_id, request_id=request.request_id,
                  details=details)
        event = get_case(case_id)
        return Response(case_detail(event))
