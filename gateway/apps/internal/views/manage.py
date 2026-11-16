"""Administrator account management and limits (FR-ADM-02 to FR-ADM-05, FR-ADM-07,
FR-ADM-12; UC-34, UC-35, UC-37, UC-44).

Staff accounts:
* GET  staff?q= : search by name or email.
* POST staff/{id}/status {action: suspend|deactivate|reinstate, reason, confirm: true}
  Suspending or deactivating makes the account inactive and ends its sessions. Refused for
  your own account (FR-ADM-03) and for the last active administrator (FR-ADM-05).
  Deactivation is permanent; a suspended account can be reinstated.
* POST staff/{id}/role {role, merchant_id?} : applies from the account's next request
  (the role is read on every request). Refused if it would remove the last administrator.
  Non-administrators get 403 and the attempt is logged (UC-35).

Merchants:
* POST merchants/{id}/status {action: suspend|deactivate|reinstate, reason, confirm: true}
  Suspending stops the API keys working and signs its operators out, keeping all history.
  Deactivating also revokes the keys and is permanent.
* POST merchants/{id}/limit {max_amount_cents | null} : the merchant's own limit.

Gateway limits:
* GET / POST limits {max_amount_cents, api_key_requests_per_minute, ip_requests_per_minute}
  The amount limit can only be lowered below the hard ceiling in GATEWAY_RULES.

Every change is audited with the old and new values, and the reason where there is one.
"""
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.response import Response

from apps.accounts.models import Role, StaffAccount
from apps.accounts.sessions import end_sessions
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.internal.access import ADMIN, StaffAPIView
from apps.internal.views.admin import merchant_to_dict
from apps.merchants.models import Merchant
from apps.security import limits as gateway_limits
from apps.security.models import GatewayLimits

ACTIONS = ("suspend", "deactivate", "reinstate")
PAST = {"suspend": "suspended", "deactivate": "deactivated", "reinstate": "reinstated"}


def staff_row(account: StaffAccount) -> dict:
    merchant = account.merchant
    return {
        "id": account.public_id,
        "name": account.display_name,
        "email": account.email,
        "role": account.role,
        "role_label": account.get_role_display(),
        "merchant": {"id": merchant.public_id, "name": merchant.name} if merchant else None,
        "status": account.status,
        "status_reason": account.status_reason or None,
        "status_changed_at": rfc3339(account.status_changed_at),
        "last_sign_in_at": rfc3339(account.last_sign_in_at),
        "created_at": rfc3339(account.created_at),
    }


def _body(request) -> dict:
    return request.data if isinstance(request.data, dict) else {}


def _action_and_reason(body: dict) -> tuple[str, str]:
    action = body.get("action")
    if action not in ACTIONS:
        raise invalid("invalid_field", "'action' must be suspend, deactivate or reinstate.",
                      param="action")
    reason = body.get("reason")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200:
        raise invalid("missing_field", "Give a reason of up to 200 characters.", param="reason")
    if body.get("confirm") is not True:
        raise invalid("confirmation_required", "Confirm the change ('confirm': true).",
                      param="confirm")
    return action, reason.strip()


def _active_admins():
    return StaffAccount.objects.filter(role=Role.ADMINISTRATOR, status=StaffAccount.Status.ACTIVE,
                                       user__is_active=True)


def _would_remove_last_admin(account: StaffAccount) -> bool:
    return (account.role == Role.ADMINISTRATOR and account.status == StaffAccount.Status.ACTIVE
            and not _active_admins().exclude(pk=account.pk).exists())


def last_admin_error() -> ApiError:
    return ApiError(409, "last_administrator", "This is the last active administrator. Make "
                    "another account an administrator first.")


class _AdminView(StaffAPIView):
    roles = ADMIN

    def _audit(self, action, *, target_type, target_id, merchant_id="", **details):
        audit(action, actor_type=AuditEvent.ActorType.STAFF, actor_id=self.staff.public_id,
              merchant_id=merchant_id, target_type=target_type, target_id=target_id,
              request_id=self.request.request_id, details=details)

    def _staff(self, staff_id: str, lock=False) -> StaffAccount:
        accounts = StaffAccount.objects.select_related("user", "merchant")
        if lock:
            accounts = accounts.select_for_update(of=("self",))
        account = accounts.filter(public_id=staff_id[:32]).first()
        if account is None:
            raise not_found()
        return account


class StaffListView(_AdminView):
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()[:120]
        accounts = StaffAccount.objects.select_related("user", "merchant")
        if q:
            accounts = accounts.filter(
                Q(user__email__icontains=q) | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q) | Q(public_id=q))
        rows = accounts.order_by("status", "user__email")[:200]
        return Response({"object": "list", "query": q or None,
                         "data": [staff_row(a) for a in rows],
                         "roles": [{"value": r.value, "label": r.label} for r in Role]})


class StaffStatusView(_AdminView):
    def post(self, request, staff_id: str):
        action, reason = _action_and_reason(_body(request))
        with transaction.atomic():
            # Lock every administrator row so two admins cannot suspend each other at once
            # and leave none (FR-ADM-05).
            list(_active_admins().select_for_update(of=("self",)).values_list("pk", flat=True))
            account = self._staff(staff_id, lock=True)
            if account.pk == self.staff.pk:
                raise ApiError(409, "cannot_change_own_account", "You cannot suspend or "
                               "deactivate your own account.")  # FR-ADM-03
            old = account.status
            if account.status == StaffAccount.Status.DEACTIVATED:
                raise ApiError(409, "account_deactivated", "This account is deactivated "
                               "permanently and cannot be changed.")
            if action == "reinstate":
                if old != StaffAccount.Status.SUSPENDED:
                    raise ApiError(409, "account_not_suspended", "Only a suspended account "
                                   "can be reinstated.")
                new = StaffAccount.Status.ACTIVE
            else:
                if action == "suspend" and old == StaffAccount.Status.SUSPENDED:
                    raise ApiError(409, "account_suspended", "This account is already "
                                   "suspended.")
                if _would_remove_last_admin(account):
                    raise last_admin_error()
                new = (StaffAccount.Status.SUSPENDED if action == "suspend"
                       else StaffAccount.Status.DEACTIVATED)
            account.status, account.status_reason = new, reason
            account.status_changed_at = timezone.now()
            account.failed_attempts, account.locked_until = 0, None
            account.save(update_fields=["status", "status_reason", "status_changed_at",
                                        "failed_attempts", "locked_until"])
            user = account.user
            user.is_active = new == StaffAccount.Status.ACTIVE
            user.save(update_fields=["is_active"])
            ended = 0 if user.is_active else end_sessions(user)
            self._audit(f"staff.{PAST[action]}",
                        target_type="staff", target_id=account.public_id,
                        merchant_id=account.merchant.public_id if account.merchant else "",
                        old_status=old, new_status=new, reason=reason, sessions_ended=ended)
        return Response(staff_row(account))


class StaffRoleView(_AdminView):
    def check_permissions(self, request):
        try:
            super().check_permissions(request)
        except exceptions.PermissionDenied:
            account = getattr(request, "_auth", None)
            if isinstance(account, StaffAccount):  # signed in, not an administrator (UC-35)
                self._log_denied(request, account)
            raise

    def _log_denied(self, request, account):
        audit("staff.role_change_denied", actor_type=AuditEvent.ActorType.STAFF,
              actor_id=account.public_id, target_type="staff",
              target_id=str(self.kwargs.get("staff_id", ""))[:32],
              request_id=getattr(request, "request_id", ""),
              details={"actor_role": account.role})

    def post(self, request, staff_id: str):
        body = _body(request)
        role = body.get("role")
        if role not in Role.values:
            raise invalid("invalid_field", "Choose merchant_operator, fraud_analyst or "
                          "administrator.", param="role")
        with transaction.atomic():
            list(_active_admins().select_for_update(of=("self",)).values_list("pk", flat=True))
            account = self._staff(staff_id, lock=True)
            if account.status == StaffAccount.Status.DEACTIVATED:
                raise ApiError(409, "account_deactivated", "A deactivated account keeps its "
                               "last role.")
            merchant = None
            if role == Role.MERCHANT_OPERATOR:
                merchant_id = body.get("merchant_id") or (
                    account.merchant.public_id if account.merchant else None)
                merchant = (Merchant.objects.filter(public_id=str(merchant_id)[:32]).first()
                            if merchant_id else None)
                if merchant is None:
                    raise invalid("missing_field", "A merchant operator needs a merchant.",
                                  param="merchant_id")
            if account.role == role and account.merchant_id == (merchant.pk if merchant else None):
                return Response(staff_row(account))
            if role != Role.ADMINISTRATOR and _would_remove_last_admin(account):
                raise last_admin_error()  # FR-ADM-05
            old_role = account.role
            old_merchant = account.merchant.public_id if account.merchant else None
            account.role, account.merchant = role, merchant
            account.save(update_fields=["role", "merchant"])
            self._audit("staff.role_changed", target_type="staff", target_id=account.public_id,
                        merchant_id=merchant.public_id if merchant else "",
                        old_role=old_role, new_role=role, old_merchant_id=old_merchant,
                        new_merchant_id=merchant.public_id if merchant else None)
        return Response(staff_row(account))


class MerchantStatusView(_AdminView):
    def post(self, request, merchant_id: str):
        action, reason = _action_and_reason(_body(request))
        with transaction.atomic():
            merchant = Merchant.objects.select_for_update().filter(
                public_id=merchant_id[:32]).first()
            if merchant is None:
                raise not_found()
            old = merchant.status
            if old == Merchant.Status.DEACTIVATED:
                raise ApiError(409, "merchant_deactivated", "This merchant is deactivated "
                               "permanently.")
            if action == "reinstate":
                if old != Merchant.Status.SUSPENDED:
                    raise ApiError(409, "merchant_not_suspended", "Only a suspended merchant "
                                   "can be reinstated.")
                new = Merchant.Status.ACTIVE
            else:
                if old not in (Merchant.Status.ACTIVE, Merchant.Status.SUSPENDED) or (
                        action == "suspend" and old == Merchant.Status.SUSPENDED):
                    raise ApiError(409, "merchant_not_active", f"A {old} merchant cannot be "
                                   f"{PAST[action]}.")
                new = (Merchant.Status.SUSPENDED if action == "suspend"
                       else Merchant.Status.DEACTIVATED)
            merchant.status, merchant.status_reason = new, reason
            merchant.save(update_fields=["status", "status_reason", "updated_at"])
            revoked = []
            if new == Merchant.Status.DEACTIVATED:
                now = timezone.now()
                revoked = list(merchant.api_keys.filter(revoked_at__isnull=True)
                               .values_list("public_id", flat=True))
                merchant.api_keys.filter(revoked_at__isnull=True).update(revoked_at=now)
            ended = 0
            if new != Merchant.Status.ACTIVE:
                for operator in StaffAccount.objects.select_related("user").filter(
                        merchant=merchant):
                    ended += end_sessions(operator.user)
            self._audit(f"merchant.{PAST[action]}",
                        target_type="merchant", target_id=merchant.public_id,
                        merchant_id=merchant.public_id, old_status=old, new_status=new,
                        reason=reason, revoked_api_keys=revoked, sessions_ended=ended)
        return Response(merchant_to_dict(
            Merchant.objects.prefetch_related("api_keys").get(pk=merchant.pk)))


def _limit(value, param, low, high, allow_null=True):
    if value is None and allow_null:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise invalid("invalid_field", f"'{param}' must be a whole number from {low} to "
                      f"{high}.", param=param)
    return value


class MerchantLimitView(_AdminView):
    def post(self, request, merchant_id: str):
        body = _body(request)
        if "max_amount_cents" not in body:
            raise invalid("missing_field", "Send max_amount_cents (null removes the limit).",
                          param="max_amount_cents")
        rules = settings.GATEWAY_RULES
        value = _limit(body.get("max_amount_cents"), "max_amount_cents",
                       rules["MIN_AMOUNT_CENTS"], rules["MAX_AMOUNT_CENTS"])
        with transaction.atomic():
            merchant = Merchant.objects.select_for_update().filter(
                public_id=merchant_id[:32]).first()
            if merchant is None:
                raise not_found()
            old = merchant.max_amount_cents
            merchant.max_amount_cents = value
            merchant.save(update_fields=["max_amount_cents", "updated_at"])
            self._audit("merchant.limit_changed", target_type="merchant",
                        target_id=merchant.public_id, merchant_id=merchant.public_id,
                        old_max_amount_cents=old, new_max_amount_cents=value)
        return Response(merchant_to_dict(
            Merchant.objects.prefetch_related("api_keys").get(pk=merchant.pk)))


def limits_dict() -> dict:
    rules = settings.GATEWAY_RULES
    row = GatewayLimits.objects.filter(pk=1).first()
    return {
        "effective": gateway_limits.load().as_dict(),
        "defaults": gateway_limits.defaults().as_dict(),
        "bounds": {"max_amount_cents": [rules["MIN_AMOUNT_CENTS"], rules["MAX_AMOUNT_CENTS"]],
                   "requests_per_minute": [1, 10_000]},
        "updated_at": rfc3339(row.updated_at) if row else None,
        "updated_by": row.updated_by or None if row else None,
    }


class LimitsView(_AdminView):
    FIELDS = ("max_amount_cents", "api_key_requests_per_minute", "ip_requests_per_minute")

    def get(self, request):
        return Response(limits_dict())

    def post(self, request):
        body = _body(request)
        rules = settings.GATEWAY_RULES
        changes = {}
        for field in self.FIELDS:
            if field not in body:
                continue
            if field == "max_amount_cents":
                changes[field] = _limit(body[field], field, rules["MIN_AMOUNT_CENTS"],
                                        rules["MAX_AMOUNT_CENTS"])
            else:
                changes[field] = _limit(body[field], field, 1, 10_000)
        if not changes:
            raise invalid("missing_field", "Send at least one limit.")
        with transaction.atomic():
            row, _ = GatewayLimits.objects.select_for_update().get_or_create(pk=1)
            old = {f: getattr(row, f) for f in changes}
            for field, value in changes.items():
                setattr(row, field, value)
            row.updated_by = self.staff.public_id
            row.save()
            self._audit("limits.changed", target_type="limits", target_id="gateway",
                        old=old, new=changes)
        gateway_limits.forget()
        return Response(limits_dict())
