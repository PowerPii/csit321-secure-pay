"""D1 sign-in, D2 two-step verification, sign-out and the current staff member."""
from typing import ClassVar

from django.conf import settings
from django.contrib.auth import get_user, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authentication import CSRFCheck
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts import signin
from apps.accounts.models import StaffAccount
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid
from apps.internal.access import StaffAPIView


def _enforce_csrf(request):
    """CSRF on the sign-in steps too, although nobody is signed in yet (login CSRF)."""
    def dummy_get_response(request):  # pragma: no cover - never called
        return None

    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise ApiError(403, "csrf_failed", "Reload the page and try again.")


def staff_to_dict(account: StaffAccount) -> dict:
    merchant = account.merchant
    return {
        "id": account.public_id,
        "email": account.email,
        "name": account.display_name,
        "role": account.role,
        "role_label": account.get_role_display(),
        "merchant": ({"id": merchant.public_id, "name": merchant.name,
                      "status": merchant.status}
                     if merchant else None),
        # FR-ACC-10: the dashboard warns at idle_warning_minutes, signs out at idle_minutes.
        "idle_minutes": settings.SESSION_COOKIE_AGE // 60,
        "idle_warning_minutes": settings.GATEWAY_RULES["IDLE_WARNING_MINUTES"],
    }


class _SignInStep(APIView):
    authentication_classes: ClassVar = []
    permission_classes: ClassVar = [AllowAny]
    throttle_classes: ClassVar = [AnonRateThrottle]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        _enforce_csrf(request._request)


class LoginView(_SignInStep):
    """POST {email, password}: step 1. 200 {next: "totp", setup: null | {qr...}}."""

    def post(self, request):
        email, password = request.data.get("email"), request.data.get("password")
        if not isinstance(email, str) or not email.strip():
            raise invalid("missing_field", "Enter your email address.", param="email")
        if not isinstance(password, str) or not password:
            raise invalid("missing_field", "Enter your password.", param="password")
        return Response(signin.check_password(request._request, email[:254], password[:256]))


class TotpView(_SignInStep):
    """GET: who is half signed in (for the D2 page). POST {code}: step 2, signs in."""

    def get(self, request):
        account = signin.pending_account(request._request)
        return Response({"email": account.email,
                         "setup_required": signin.confirmed_device(account) is None})

    def post(self, request):
        code = request.data.get("code")
        if not isinstance(code, str):
            raise invalid("missing_field", "Enter the 6-digit code.", param="code")
        account = signin.check_code(request._request, code)
        return Response(staff_to_dict(account))


class LogoutView(APIView):
    authentication_classes: ClassVar = []
    permission_classes: ClassVar = [AllowAny]

    def post(self, request):
        _enforce_csrf(request._request)
        user = get_user(request._request)  # DRF's request.user is anonymous here
        account = (StaffAccount.objects.filter(user=user).first()
                   if user.is_authenticated else None)
        logout(request._request)
        if account is not None:
            audit("staff.signed_out", actor_type=AuditEvent.ActorType.STAFF,
                  actor_id=account.public_id, target_type="staff",
                  target_id=account.public_id, request_id=getattr(request, "request_id", ""))
        return Response(status=204)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(StaffAPIView):
    """The signed-in staff member. Also sets the CSRF cookie, so the dashboard calls it first
    (a 401 still sets the cookie)."""

    def get(self, request):
        return Response(staff_to_dict(self.staff))
