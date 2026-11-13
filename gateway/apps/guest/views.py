"""Guest status API for the checkout front end (screen C9; openapi/guest-status.v1.yaml).

Same origin as the page, JSON only (a cross-site form cannot post JSON without a CORS
preflight), and the session cookie is SameSite=Strict, HttpOnly, Secure and limited to
/guest/status, so another site can neither send nor read it.
"""
from typing import ClassVar

from django.conf import settings
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.common.clientip import client_ip
from apps.common.errors import invalid
from apps.guest import service


class GuestView(APIView):
    authentication_classes: ClassVar = []
    permission_classes: ClassVar = [AllowAny]
    parser_classes: ClassVar = [JSONParser]
    throttle_classes: ClassVar = [AnonRateThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex"
        return response

    @staticmethod
    def body(request) -> dict:
        if not isinstance(request.data, dict):
            raise invalid("invalid_json", "The request body must be a JSON object.")
        return request.data

    @staticmethod
    def token(request) -> str | None:
        return request.COOKIES.get(service.COOKIE)


class CodeView(GuestView):
    def post(self, request):
        return Response(service.request_code(self.body(request), client_ip(request)),
                        status=202)


class VerifyView(GuestView):
    def post(self, request):
        payment, token = service.verify_code(self.body(request))
        response = Response(service.to_view(payment))
        response.set_cookie(
            service.COOKIE, token, path=service.COOKIE_PATH, httponly=True, secure=True,
            samesite="Strict",
            max_age=settings.GATEWAY_RULES["GUEST_STATUS_SESSION_MINUTES"] * 60)
        return response


class PaymentView(GuestView):
    def get(self, request):
        return Response(service.to_view(service.session_payment(self.token(request))))


class SignOutView(GuestView):
    def post(self, request):
        service.end_session(self.token(request))
        response = Response(status=204)
        response.delete_cookie(service.COOKIE, path=service.COOKIE_PATH, samesite="Strict")
        return response
