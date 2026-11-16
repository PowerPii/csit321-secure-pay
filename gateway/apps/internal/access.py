"""Session authentication and role checks for the staff API (FR-ACC-14, FR-ACC-16).

A request counts as signed in only after both steps: Django's session login and the TOTP
check (django-otp's `is_verified()`). Roles and merchant ownership are checked here on the
server for every request, whatever the dashboard shows or hides.
"""
from typing import ClassVar

from rest_framework import authentication, exceptions, permissions
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffAccount
from apps.common.errors import ApiError, not_found
from apps.payments.models import Payment
from apps.payments.settlement import Actor


class StaffSessionAuthentication(authentication.SessionAuthentication):
    """Django session + CSRF on every unsafe request. Returns (user, StaffAccount)."""

    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if not user or not user.is_active or not user.is_authenticated:
            return None
        if not (hasattr(user, "is_verified") and user.is_verified()):
            return None  # password only: the TOTP step is still missing
        account = StaffAccount.objects.select_related("merchant").filter(user=user).first()
        if account is None or account.status != StaffAccount.Status.ACTIVE:
            return None
        if account.merchant is not None and account.merchant.status in MERCHANT_OFF:
            return None  # FR-ADM-02: a suspended merchant's operators are signed out
        self.enforce_csrf(request)
        return user, account

    def authenticate_header(self, request):
        return "Session"


MERCHANT_OFF = ("suspended", "deactivated", "rejected")


class IsStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.auth, StaffAccount):
            raise exceptions.NotAuthenticated()
        roles = getattr(view, "roles", None)
        if roles and request.auth.role not in roles:
            raise exceptions.PermissionDenied(
                "Your role cannot use this page.", code="role_not_allowed")
        return True


def not_signed_in() -> ApiError:
    return ApiError(401, "not_signed_in", "Sign in to the dashboard.")


class StaffAPIView(APIView):
    """Base for /internal/*. `roles` limits a view to some roles (None = every role)."""

    authentication_classes: ClassVar = [StaffSessionAuthentication]
    permission_classes: ClassVar = [IsStaff]
    throttle_classes: ClassVar = []
    roles: tuple[str, ...] | None = None

    def permission_denied(self, request, message=None, code=None):
        if request.authenticators and not request.successful_authenticator:
            raise not_signed_in()
        super().permission_denied(request, message, code)

    def handle_exception(self, exc):
        if isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
            if isinstance(exc, exceptions.AuthenticationFailed) and "CSRF" in str(exc.detail):
                exc = ApiError(403, "csrf_failed", "Reload the page and try again.")
            else:
                exc = not_signed_in()
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        account = getattr(request, "_auth", None)
        if (response.status_code == 404 and isinstance(account, StaffAccount)
                and account.is_operator):
            # FR-MER-09: an operator asking for another merchant's payment gets 404 (FR-MER-08);
            # the attempt is logged and repeated attempts alert administrators.
            from apps.audit.models import AuditEvent
            from apps.security.crossmerchant import log_if_cross_merchant

            log_if_cross_merchant(request, kwargs, account.merchant,
                                  AuditEvent.ActorType.STAFF, account.public_id)
        return response

    @property
    def staff(self) -> StaffAccount:
        return self.request.auth

    def actor(self) -> Actor:
        from apps.audit.models import AuditEvent

        return Actor(AuditEvent.ActorType.STAFF, self.staff.public_id,
                     getattr(self.request, "request_id", ""))


OPERATOR = (Role.MERCHANT_OPERATOR,)
ANALYST_OR_ADMIN = (Role.FRAUD_ANALYST, Role.ADMINISTRATOR)
ADMIN = (Role.ADMINISTRATOR,)


def visible_payments(staff: StaffAccount):
    """Merchant operators see their own merchant's payments; analysts and administrators
    see every merchant's, read-only (FR-MER-08, FR-ADM-06)."""
    payments = Payment.objects.select_related("merchant")
    if staff.is_operator:
        return payments.filter(merchant_id=staff.merchant_id)
    return payments


def get_payment(staff: StaffAccount, payment_id: str) -> Payment:
    """Another merchant's payment answers 404, exactly like one that does not exist."""
    payment = visible_payments(staff).filter(public_id=payment_id).first()
    if payment is None:
        raise not_found()
    return payment
