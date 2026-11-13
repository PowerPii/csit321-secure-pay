"""Hosted checkout API for frontend/checkout (same origin, no login).

JSON only, so a cross-site form post cannot reach it (the browser would need a CORS
preflight). Replies are never cached, and the card number is never echoed or logged.
"""
from typing import ClassVar

from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.checkout import service
from apps.common.clientip import client_ip
from apps.common.errors import invalid


class CheckoutView(APIView):
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
        data = request.data
        if not isinstance(data, dict):
            raise invalid("invalid_json", "The request body must be a JSON object.")
        return data


class SessionView(CheckoutView):
    """GET: order summary and current state (C3, and C6/C7 after a reload)."""

    def get(self, request, session_id):
        return Response(service.to_dict(service.load(session_id)))


class CardView(CheckoutView):
    """POST {number, expiry_month, expiry_year, cvc, email?}: vault the card."""

    def post(self, request, session_id):
        payment = service.load(session_id)
        payment = service.attach_card(payment, self.body(request), request.request_id)
        return Response(service.to_dict(payment))


class SubmitView(CheckoutView):
    """POST {}: pay. Answers with the result once the simulator answered or timed out."""

    def post(self, request, session_id):
        payment = service.load(session_id)
        payment = service.submit(payment, request.request_id, ip=client_ip(request))
        return Response(service.to_dict(payment))


class VerifyView(CheckoutView):
    """POST {code}: the 6-digit code from the email (C5)."""

    def post(self, request, session_id):
        payment = service.load(session_id)
        payment = service.verify(payment, self.body(request), request.request_id)
        return Response(service.to_dict(payment))


class ResendView(CheckoutView):
    """POST {}: email a new code, which replaces the old one."""

    def post(self, request, session_id):
        payment = service.load(session_id)
        payment = service.resend(payment, request.request_id)
        return Response(service.to_dict(payment))


class ResultView(CheckoutView):
    def get(self, request, session_id):
        return Response(service.to_dict(service.load(session_id)))
