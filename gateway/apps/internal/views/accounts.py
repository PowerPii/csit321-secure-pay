"""Signed-out account pages: forgot / reset password (FR-ACC-07 to FR-ACC-09) and business
registration with email verification (FR-MER-01, FR-MER-02; wireframe D7).

Like the sign-in steps, these need the CSRF cookie (GET /internal/me sets it) and are limited
per IP address; the two forms that send email have their own, lower limit.
"""
from typing import ClassVar

from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle

from apps.accounts import reset
from apps.common.errors import invalid
from apps.internal.views.auth import _SignInStep
from apps.merchants import registration


def _body(request) -> dict:
    return request.data if isinstance(request.data, dict) else {}


class _EmailSendingStep(_SignInStep):
    throttle_classes: ClassVar = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "account_email"


class PasswordResetRequestView(_EmailSendingStep):
    """POST {email} -> 202 with the same message whether or not the email has an account."""

    def post(self, request):
        email = _body(request).get("email")
        if not isinstance(email, str) or not email.strip() or "@" not in email:
            raise invalid("missing_field", "Enter your email address.", param="email")
        reset.request_reset(request._request, email[:254])
        return Response({"message": reset.requested_message()},
                        status=status.HTTP_202_ACCEPTED)


class PasswordResetCheckView(_SignInStep):
    """POST {token} -> {email, mfa_required}, or 400 link_invalid. Does not use the link."""

    def post(self, request):
        return Response(reset.check_link(_body(request).get("token")))


class PasswordResetConfirmView(_SignInStep):
    """POST {token, password, code?} -> 200 once the password is changed."""

    def post(self, request):
        body = _body(request)
        account = reset.reset_password(request._request, body.get("token"),
                                       body.get("password"), body.get("code"))
        return Response({"email": account.email, "message": "Your password has been changed. "
                         "Sign in with the new password."})


class RegisterView(_EmailSendingStep):
    """POST the D7 form -> 202 {message}. 400 names the field to correct; 409 for a UEN that
    is already registered."""

    def post(self, request):
        message = registration.register(request._request, _body(request))
        return Response({"message": message}, status=status.HTTP_202_ACCEPTED)


class RegisterVerifyView(_SignInStep):
    """POST {token} -> the pending merchant (the D7 "Registration received" state)."""

    def post(self, request):
        merchant = registration.verify_email(request._request, _body(request).get("token"))
        return Response({"merchant": {"id": merchant.public_id, "name": merchant.name,
                                      "status": merchant.status},
                         "email": merchant.contact_email})
