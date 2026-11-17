"""Analyst search of payment history and the block list (FR-FRD-06, FR-FRD-09; UC-48, UC-51).

* GET fraud/search?by=card|email|ip&value=&page= : screened attempts that share a card, an
  email address or an IP address, newest first. For a card, `value` is the card fingerprint
  or a payment (pay_... or SP-...) whose card to look for; an IP search also takes a payment.
  The email and IP are hashed the same way screening keys them, so nothing readable is
  stored; each search is audit-logged with the hash, never the value (FR-FRD-06).
* GET blocklist?show=active|removed|all&kind= : the entries, masked.
* POST blocklist {kind: card|ip, case_id | payment_id | ip, reason} : block later attempts
  with that card or IP. Earlier outcomes do not change; customers see the general "payment
  not completed" message (FR-FRD-09). Analysts and administrators.
* POST blocklist/{id}/remove {reason} : administrators only. The entry is kept, switched off.
"""
import ipaddress
import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.common.views import body_or_empty
from apps.internal.access import ADMIN, ANALYST_OR_ADMIN, StaffAPIView
from apps.internal.query_params import bounded_int
from apps.internal.views.reviews import FLAGGED
from apps.payments.models import Payment
from apps.risk import hashing
from apps.risk.models import RiskListEntry, ScreeningEvent, ScreeningOutcome

# A card fingerprint is an HMAC-SHA256 in hex (apps/vault/fingerprint.py): exactly 64 digits.
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
# Something typed like a card number (13 to 19 digits, maybe with spaces or dashes). Refused
# before anything else so it is never echoed back, used as a key or written to the audit log.
CARD_NUMBER = re.compile(r"^[0-9][0-9 -]{11,24}[0-9]$")
FIELD = {"card": "card_fingerprint", "email": "email_hash", "ip": "ip_hash"}


def _payment(value: str) -> Payment | None:
    value = value.strip()
    if value.startswith("pay_"):
        return Payment.objects.filter(public_id=value[:32]).first()
    if value.upper().startswith("SP-"):
        return Payment.objects.filter(reference=value.upper()[:20]).first()
    return None


def _event_for_payment(value: str) -> ScreeningEvent | None:
    payment = _payment(value)
    return ScreeningEvent.objects.filter(payment=payment).first() if payment else None


def mask_ip(ip: str) -> str:
    address = ipaddress.ip_address(ip)
    if address.version == 4:
        return ".".join(ip.split(".")[:3]) + ".•"
    return address.exploded.rsplit(":", 4)[0] + ":•"


def card_display(payment: Payment | None) -> str:
    if payment is None or not payment.card_last4:
        return "Card"
    return f"{(payment.card_brand or 'card').title()} •••• {payment.card_last4}"


def search_key(by: str, value: str) -> tuple[str, str]:
    """(hash to match, what to show). Raises a 400 for a value that cannot be searched."""
    value = (value or "").strip()
    if not value:
        raise invalid("missing_field", "Enter what to search for.", param="value")
    if CARD_NUMBER.match(value) and 13 <= len(re.sub(r"[ -]", "", value)) <= 19:
        raise invalid("card_number_not_accepted", "Card numbers are never searched or stored. "
                      "Enter the card fingerprint, or a payment ID or reference.", param="value")
    if by in ("card", "ip"):
        event = _event_for_payment(value)
        if event is not None:
            key = getattr(event, FIELD[by])
            if not key:
                raise invalid("invalid_field", f"That payment has no {by} on record.",
                              param="value")
            shown = card_display(event.payment) if by == "card" else "IP of " + \
                event.payment.reference
            return key, shown
    if by == "card":
        if not FINGERPRINT.match(value.lower()):
            raise invalid("invalid_field", "Enter a card fingerprint or a payment ID or "
                          "reference.", param="value")
        return value.lower(), f"Card {value.lower()[:8]}…"
    if by == "email":
        if "@" not in value or len(value) > 254:
            raise invalid("invalid_field", "Enter an email address.", param="value")
        local, _, domain = value.lower().partition("@")
        return hashing.email_hash(value), f"{local[:1]}•••@{domain}"
    if by == "ip":
        try:
            ip = str(ipaddress.ip_address(value))
        except ValueError:
            raise invalid("invalid_field", "Enter an IP address or a payment ID or reference.",
                          param="value") from None
        return hashing.ip_hash(ip), mask_ip(ip)
    raise invalid("invalid_field", "'by' must be card, email or ip.", param="by")


def attempt_row(event: ScreeningEvent) -> dict:
    payment = event.payment
    return {
        "case_id": event.public_id if event.outcome in FLAGGED else None,
        "payment": {"id": payment.public_id, "reference": payment.reference,
                    "status": payment.status},
        "merchant": {"id": payment.merchant.public_id, "name": payment.merchant.name},
        "amount": event.amount,
        "card": card_display(payment) if payment.card_last4 else None,
        "outcome": event.outcome,
        "score": event.score,
        "reasons": list(event.reasons or []),
        "occurred_at": rfc3339(event.occurred_at),
    }


class HistorySearchView(StaffAPIView):
    roles = ANALYST_OR_ADMIN

    def get(self, request):
        params = request.query_params
        by = params.get("by") or ""
        if by not in FIELD:
            raise invalid("invalid_field", "'by' must be card, email or ip.", param="by")
        key, shown = search_key(by, params.get("value", "")[:300])
        events = (ScreeningEvent.objects.filter(**{FIELD[by]: key})
                  .select_related("payment__merchant"))
        page = bounded_int(params.get("page"), "page", 1, 1, 10_000)
        size = bounded_int(params.get("page_size"), "page_size", 25, 1, 100)
        count = events.count()
        summary = {
            "attempts": count,
            "merchants": events.values("merchant").distinct().count(),
            "blocked": events.filter(outcome__in=[ScreeningOutcome.BLOCK,
                                                  ScreeningOutcome.NOT_SCREENED]).count(),
            "flagged": events.filter(outcome__in=FLAGGED).count(),
        }
        listed = RiskListEntry.objects.filter(kind=by, value_hash=key, active=True).first()
        rows = events.order_by("-occurred_at", "-id")[(page - 1) * size: page * size]
        audit("fraud.history_searched", actor_type=AuditEvent.ActorType.STAFF,
              actor_id=self.staff.public_id, target_type=by, target_id=key[:32],
              request_id=request.request_id, details={"by": by, "results": count})
        return Response({"object": "list", "by": by, "searched": shown, "count": count,
                         "page": page, "page_size": size, "summary": summary,
                         "blocklisted": entry_to_dict(listed) if listed else None,
                         "data": [attempt_row(e) for e in rows]})


def entry_to_dict(entry: RiskListEntry) -> dict:
    return {
        "id": entry.pk, "kind": entry.kind, "action": entry.action,
        "display": entry.display or f"{entry.kind} {entry.value_hash[:8]}…",
        "reason": entry.label, "active": entry.active, "added_by": entry.added_by or None,
        "source_case": entry.source_case or None, "created_at": rfc3339(entry.created_at),
        "removed_by": entry.removed_by or None, "removed_at": rfc3339(entry.removed_at),
        "removal_reason": entry.removal_reason or None,
    }


def _reason(body: dict, param="reason") -> str:
    reason = body.get(param)
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 100:
        raise invalid("missing_field", "Give a reason of up to 100 characters.", param=param)
    return reason.strip()


class BlocklistView(StaffAPIView):
    roles = ANALYST_OR_ADMIN

    def get(self, request):
        params = request.query_params
        show = params.get("show") or "active"
        entries = RiskListEntry.objects.filter(action=RiskListEntry.Action.BLOCK)
        if show == "active":
            entries = entries.filter(active=True)
        elif show == "removed":
            entries = entries.filter(active=False)
        elif show != "all":
            raise invalid("invalid_field", "'show' must be active, removed or all.",
                          param="show")
        if params.get("kind") in FIELD:
            entries = entries.filter(kind=params["kind"])
        rows = entries.order_by("-created_at", "-id")[:500]
        return Response({"object": "list", "data": [entry_to_dict(e) for e in rows],
                         "can_remove": self.staff.is_admin})

    def post(self, request):
        body = body_or_empty(request)
        kind = body.get("kind")
        if kind not in ("card", "ip"):
            raise invalid("invalid_field", "Only cards and IP addresses can be blocklisted "
                          "here.", param="kind")
        reason = _reason(body)
        source_case, display, key = "", "", ""
        ref = body.get("case_id") or body.get("payment_id")
        if isinstance(ref, str) and ref:
            if ref.startswith("scr_"):
                event = (ScreeningEvent.objects.select_related("payment")
                         .filter(public_id=ref[:32]).first())
            else:
                event = _event_for_payment(ref)
            if event is None:
                raise not_found()
            key = getattr(event, FIELD[kind])
            source_case = event.public_id
            display = (card_display(event.payment) if kind == "card"
                       else f"IP of {event.payment.reference}")
            if not key:
                raise invalid("invalid_field", f"That payment has no {kind} on record.",
                              param="kind")
        elif kind == "ip" and isinstance(body.get("ip"), str):
            key, display = search_key("ip", body["ip"])
        elif kind == "card" and isinstance(body.get("card_fingerprint"), str):
            key, display = search_key("card", body["card_fingerprint"])
        else:
            raise invalid("missing_field", "Say which case or payment to take the card or IP "
                          "from, or give the IP address.", param="case_id")
        with transaction.atomic():
            entry = (RiskListEntry.objects.select_for_update()
                     .filter(kind=kind, value_hash=key).first())
            if entry is not None and entry.active and entry.action == RiskListEntry.Action.BLOCK:
                raise ApiError(409, "already_blocklisted", "This is already on the block list.",
                               extra={"entry": entry_to_dict(entry)})
            if entry is None:
                entry = RiskListEntry(kind=kind, value_hash=key)
            entry.action, entry.label, entry.active = RiskListEntry.Action.BLOCK, reason, True
            entry.added_by, entry.source_case, entry.display = (self.staff.public_id,
                                                                source_case, display)
            entry.removed_by, entry.removed_at, entry.removal_reason = "", None, ""
            entry.save()
            audit("blocklist.added", actor_type=AuditEvent.ActorType.STAFF,
                  actor_id=self.staff.public_id, target_type="risk_list_entry",
                  target_id=str(entry.pk), request_id=request.request_id,
                  details={"kind": kind, "reason": reason, "source_case": source_case or None})
        return Response(entry_to_dict(entry), status=status.HTTP_201_CREATED)


class BlocklistRemoveView(StaffAPIView):
    roles = ADMIN

    def post(self, request, entry_id: int):
        reason = _reason(body_or_empty(request))
        with transaction.atomic():
            entry = RiskListEntry.objects.select_for_update().filter(
                Q(pk=entry_id), Q(active=True)).first()
            if entry is None:
                raise not_found()
            entry.active = False
            entry.removed_by, entry.removed_at = self.staff.public_id, timezone.now()
            entry.removal_reason = reason
            entry.save(update_fields=["active", "removed_by", "removed_at", "removal_reason"])
            audit("blocklist.removed", actor_type=AuditEvent.ActorType.STAFF,
                  actor_id=self.staff.public_id, target_type="risk_list_entry",
                  target_id=str(entry.pk), request_id=request.request_id,
                  details={"kind": entry.kind, "reason": reason})
        return Response(entry_to_dict(entry))
